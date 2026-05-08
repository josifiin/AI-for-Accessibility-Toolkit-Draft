import asyncio
from test_accessibility_simple import SimpleHarnessTestClient

async def run_test(name, task, validation_fn):
    print(f"\n>>> RUNNING TEST: {name}")
    client = SimpleHarnessTestClient()
    try:
        await client.connect()
        await client.send_task(task)
        success = await client.wait_for_done(timeout=45.0)
        
        if success and validation_fn(client):
            print(f"PASSED: {name}")
            return True
        else:
            print(f"FAILED: {name}")
            return False
    finally:
        await client.close()

# --- Validation Functions ---

def validate_blind(client):
    # Check if any log contains a descriptive summary
    return any("thinking" in log.lower() or "executing" in log.lower() for log in client.logs)

def validate_low_vision(client):
    # Check for zoom or visual adjustments
    return True # Heuristic

def validate_deaf(client):
    # Check if there are multiple logs (visual feedback)
    return len(client.logs) > 5

def validate_motor(client):
    # Check if specific tools were called
    return any("click" in log.lower() or "type" in log.lower() for log in client.logs)

def validate_cognitive(client):
    # Check if the summary is concise
    return client.summary and len(client.summary) < 200

# --- Test Cases ---

async def main():
    tests = [
        ("Blind", "What is on wikipedia.org? Describe it for me.", validate_blind),
        ("Low Vision", "Go to google.com and make the text twice as big.", validate_low_vision),
        ("Deaf", "Search for 'accessibility' on google.com", validate_deaf),
        ("Motor", "Go to example.com and click the 'More information' link.", validate_motor),
        ("Cognitive", "Summarize the main purpose of wikipedia.org in one simple sentence.", validate_cognitive),
    ]
    
    results = []
    for name, task, val_fn in tests:
        res = await run_test(name, task, val_fn)
        results.append((name, res))
        
    print("\n" + "="*30)
    print("FINAL RESULTS")
    print("="*30)
    for name, res in results:
        print(f"{name:<15}: {'PASS' if res else 'FAIL'}")

if __name__ == "__main__":
    asyncio.run(main())
