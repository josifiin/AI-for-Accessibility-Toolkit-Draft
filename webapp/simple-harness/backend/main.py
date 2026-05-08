import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from urllib.parse import urlparse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add browser-harness to sys.path
HARNESS_DIR = str(Path(__file__).resolve().parents[3] / "webapp" / "browser-harness")
if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)

from admin import ensure_daemon
from helpers import (
    capture_screenshot, click_at_xy, goto_url, js,
    new_tab, page_info, press_key, scroll, type_text,
    wait, wait_for_load, ensure_real_tab,
)

import google.genai as genai

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = "gemini-3-flash-preview" 

# Load SKILL.md from the harness directory
SKILL_MD_PATH = Path(HARNESS_DIR) / "SKILL.md"
SKILL_MD = SKILL_MD_PATH.read_text() if SKILL_MD_PATH.exists() else ""

SYSTEM_PROMPT = f"""You are a browser agent. You control the user's Chrome browser via the available tools.

## Harness Operating Manual
{SKILL_MD}

## Your Mission
Decide what action to take next based on the screenshot.

Available actions (respond with exactly ONE JSON object):
{{"action": "run_python", "code": "new_tab('https://google.com'); type_text('hello'); press_key('Enter')", "reason": "navigating and searching in one go"}}
{{"action": "read_skill", "domain": "amazon", "skill_file": "product-search.md", "reason": "reading site-specific tips"}}
{{"action": "click", "x": 340, "y": 200, "reason": "clicking the search bar"}}
{{"action": "type", "text": "hello world", "reason": "typing search query"}}
{{"action": "press_key", "key": "Enter", "reason": "submitting the form"}}
{{"action": "scroll", "x": 600, "y": 400, "dy": -300, "reason": "scrolling down to see more"}}
{{"action": "navigate", "url": "https://example.com", "reason": "going to the target page"}}
{{"action": "wait", "seconds": 2, "reason": "waiting for page to load"}}
{{"action": "done", "summary": "task complete — here's what I found: ..."}}

Rules:
- Always respond with a single JSON object, nothing else.
- Use "reason" to explain your thinking.
- Use "run_python" for complex sequences. HELPER CHEAT SHEET:
  - new_tab(url='about:blank')
  - goto_url(url)
  - type_text(text)
  - press_key(key) -> e.g. "Enter", "Tab"
  - click_at_xy(x, y)
  - wait_for_load(timeout=15.0)
  - capture_screenshot(path='/tmp/shot.png')
  - page_info() -> returns dict with url, title, etc.
  - js(expression) -> returns result of JS execution
- Coordinates are in CSS pixels.
- MANDATORY: If you see skills listed for the current domain in the turn info, you MUST use "read_skill" to read them BEFORE taking any other action (click, type, navigate, etc.). Never guess the site mechanics if a manual exists.
- Prefer to press 'Enter' when in a search box. Only click the search button if pressing 'Enter' fails to trigger the search.
- If you are stuck in a loop clicking something that doesn't work, try a different approach (e.g. use "run_python" for a more complex sequence).
- NEVER repeat an identical failed action—if the red debug circle shows you missed, adjust your coordinates.
- CHECK FOR COMPLETION: Before every action, look at the URL and screenshot. If the task is already finished, use {{"action": "done"}}.
"""

app = FastAPI()

def get_screenshot_b64():
    path = capture_screenshot("/tmp/simple_harness_shot.png")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

async def execute_action(action: dict, websocket: WebSocket):
    act = action["action"]
    await websocket.send_json({"type": "log", "message": f"Executing: {act} - {action.get('reason', '')}"})
    
    loop = asyncio.get_event_loop()
    
    if act == "read_skill":
        def _read():
            path = Path(HARNESS_DIR) / "domain-skills" / action["domain"] / action["skill_file"]
            if path.exists():
                return path.read_text()
            return f"Skill {action['domain']}/{action['skill_file']} not found."
        skill_content = await loop.run_in_executor(None, _read)
        await websocket.send_json({"type": "log", "message": f"Learned Skill: {skill_content[:100]}..."})
        # Add to history for the agent to "remember" the skill
        action["result"] = skill_content
        return True
    elif act == "run_python":
        def _run():
            globals_dict = {
                "capture_screenshot": capture_screenshot, "click_at_xy": click_at_xy, "goto_url": goto_url, 
                "js": js, "new_tab": new_tab, "page_info": page_info, "press_key": press_key, 
                "scroll": scroll, "type_text": type_text, "wait": wait, "wait_for_load": wait_for_load,
                "ensure_daemon": ensure_daemon,
                "read_skill": lambda d, f: (Path(HARNESS_DIR) / "domain-skills" / d / f).read_text()
            }
            exec(action["code"], globals_dict)
        await loop.run_in_executor(None, _run)
        await asyncio.sleep(1.0)
    elif act == "click":
        await loop.run_in_executor(None, lambda: click_at_xy(action["x"], action["y"]))
        await asyncio.sleep(1.5)
    elif act == "type":
        await loop.run_in_executor(None, lambda: type_text(action["text"]))
        await asyncio.sleep(0.3)
    elif act == "press_key":
        await loop.run_in_executor(None, lambda: press_key(action["key"]))
        await asyncio.sleep(0.5)
    elif act == "scroll":
        await loop.run_in_executor(None, lambda: scroll(action.get("x", 600), action.get("y", 400), action.get("dy", -300)))
        await asyncio.sleep(0.5)
    elif act == "navigate":
        await loop.run_in_executor(None, lambda: goto_url(action["url"]))
        await loop.run_in_executor(None, wait_for_load)
    elif act == "wait":
        await asyncio.sleep(action.get("seconds", 1))
    elif act == "done":
        return False
    return True

@app.get("/")
async def get():
    with open(Path(__file__).parent.parent / "frontend" / "index.html") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        task = data
        await websocket.send_json({"type": "log", "message": f"Starting task: {task}"})
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ensure_daemon)
        
        # Smart Tab Selection: Reuse existing tab, but ignore our own UI
        def _get_target_tab():
            from helpers import list_tabs, switch_tab, new_tab, current_tab
            tabs = list_tabs(include_chrome=False)
            # Filter out the Simple-Harness UI itself
            valid_tabs = [t for t in tabs if "localhost:8000" not in t["url"]]
            
            if valid_tabs:
                # If current tab is valid, stay there. Otherwise switch to the first valid one.
                cur = current_tab()
                if cur and "localhost:8000" not in cur.get("url", ""):
                    return cur
                switch_tab(valid_tabs[0]["targetId"])
                return valid_tabs[0]
            else:
                # No valid tabs found, create a new one
                new_tab("about:blank")
                return current_tab()

        await loop.run_in_executor(None, _get_target_tab)
        
        # 0. Global Skill Inventory
        def _get_all_domains():
            d = Path(HARNESS_DIR) / "domain-skills"
            return sorted([p.name for p in d.iterdir() if p.is_dir()])
        all_domains = await loop.run_in_executor(None, _get_all_domains)
        
        history = []
        
        for step in range(20):
            # 1. See
            shot_b64 = get_screenshot_b64()
            info = await loop.run_in_executor(None, page_info)
            
            # Find skills for current domain
            current_domain = (urlparse(info.get("url", "")).hostname or "").removeprefix("www.").split(".")[0]
            def _get_current_skills(dom):
                d = Path(HARNESS_DIR) / "domain-skills" / dom
                return sorted([p.name for p in d.rglob("*.md")]) if d.is_dir() else []
            current_skills = await loop.run_in_executor(None, _get_current_skills, current_domain)
            
            await websocket.send_json({"type": "screenshot", "data": shot_b64})
            
            # 2. Think
            await websocket.send_json({"type": "log", "message": f"Step {step+1}: thinking..."})
            
            messages = [
                {"role": "user", "parts": [
                    {"text": f"Task: {task}"},
                    {"text": f"Current Page Info: {json.dumps(info)}"},
                    {"text": f"Available Global Domains in domain-skills/: {json.dumps(all_domains)}"},
                    {"text": f"Skills discovered for CURRENT domain ({current_domain}): {json.dumps(current_skills)}"},
                    {"text": "Current screenshot:"},
                    {"inline_data": {"mime_type": "image/png", "data": shot_b64}},
                    {"text": "History:\n" + "\n".join(f"- {h['action']}: {h['reason']} | Result: {str(h.get('result', 'Success'))[:500]}" for h in history[-15:]) if history else "None"},
                    {"text": "Next action (JSON only):"}
                ]}
            ]
            
            response = client.models.generate_content(
                model=MODEL,
                contents=messages,
                config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
            )
            
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            
            action = json.loads(text)
            history.append(action)
            
            # 3. Act
            if not await execute_action(action, websocket):
                await websocket.send_json({"type": "log", "message": f"Task complete: {action.get('summary', '')}"})
                await websocket.send_json({"type": "done", "summary": action.get("summary", "Done")})
                break
        else:
            await websocket.send_json({"type": "log", "message": "Reached max steps."})
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
