import asyncio
from app.config import settings
from app.voice.pipeline import VoiceAgent

async def test():
    settings.ELEVENLABS_OPTIMIZE_LATENCY = 0
    agent = VoiceAgent()
    print("Done")

asyncio.run(test())
