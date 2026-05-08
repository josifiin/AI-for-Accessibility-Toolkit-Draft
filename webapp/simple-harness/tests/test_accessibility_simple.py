import asyncio
import json
import logging
import websockets

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple_harness_test")

class SimpleHarnessTestClient:
    def __init__(self, base_url="ws://localhost:8000/ws"):
        self.url = base_url
        self.ws = None
        self.logs = []
        self.screenshots = []
        self.summary = None

    async def connect(self):
        logger.info(f"Connecting to {self.url}...")
        self.ws = await websockets.connect(self.url)
        logger.info("Connected.")

    async def close(self):
        if self.ws:
            await self.ws.close()
            logger.info("Connection closed.")

    async def send_task(self, task):
        logger.info(f"Sending task: {task}")
        await self.ws.send(task)

    async def wait_for_done(self, timeout=60.0):
        """Listen for messages until 'done' is received."""
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                msg_raw = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                msg = json.loads(msg_raw)
                
                if msg.get("type") == "log":
                    logger.info(f"[LOG] {msg['message']}")
                    self.logs.append(msg["message"])
                elif msg.get("type") == "screenshot":
                    self.screenshots.append(msg["data"])
                elif msg.get("type") == "done":
                    self.summary = msg.get("summary")
                    logger.info(f"DONE: {self.summary}")
                    return True
                elif msg.get("type") == "error":
                    logger.error(f"ERROR: {msg['message']}")
                    return False
            except asyncio.TimeoutError:
                continue
        return False

async def run_base_test():
    client = SimpleHarnessTestClient()
    try:
        await client.connect()
        await client.send_task("Go to google.com")
        success = await client.wait_for_done()
        if success:
            print("Base test PASSED")
        else:
            print("Base test FAILED")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(run_base_test())
