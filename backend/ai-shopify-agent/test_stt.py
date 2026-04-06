import asyncio
import aiohttp
import base64
import json
import socket
from app.config import settings

async def test():
    print(f"Connecting with API Key: {settings.ELEVENLABS_API_KEY[:10]}...")
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        url = "wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v2_realtime&audio_format=pcm_16000&commit_strategy=manual"
        headers = {'xi-api-key': settings.ELEVENLABS_API_KEY}
        ws = await session.ws_connect(url, headers=headers)
        
        async def send():
            for i in range(5):
                chunk = b'\x00' * 3200
                await ws.send_str(json.dumps({
                    'message_type': 'input_audio_chunk',
                    'audio_base_64': base64.b64encode(chunk).decode(),
                    'commit': False,
                    'sample_rate': 16000
                }))
                await asyncio.sleep(0.1)
            # send commit
            await ws.send_str(json.dumps({
                'message_type': 'input_audio_chunk',
                'audio_base_64': '',
                'commit': True,
                'sample_rate': 16000
            }))
            print("Finished sending audio.")
            
        async def recv():
            async for m in ws:
                print('SERVER:', m.data)
                
        await asyncio.gather(send(), recv())

if __name__ == "__main__":
    asyncio.run(test())
