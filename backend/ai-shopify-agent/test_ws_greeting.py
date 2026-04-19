import asyncio
import websockets
import json

async def test_greeting():
    uri = "ws://localhost:8000/ws/voice/duplex/test-greeting"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    if isinstance(message, str):
                        data = json.loads(message)
                        print(f"EVENT: {data.get('name') or data.get('type')} | TEXT: {data.get('text', '')}")
                        if data.get('name') == 'ai_end':
                            print("Greeting turn complete!")
                            break
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                    break
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_greeting())
