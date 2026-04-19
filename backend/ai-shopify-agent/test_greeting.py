import asyncio
from app.agent.agent import SupportAgent
from app.memory.session_memory import SessionMemory

async def test_greeting():
    agent = SupportAgent()
    mem = SessionMemory()
    # Simulate first connection greeting trigger
    prompt = "greet me"
    print(f"Triggering with: {prompt}")
    
    async for audio_bytes in agent.chat_voice_stream(prompt, mem):
        if audio_bytes:
            print(f"Received {len(audio_bytes)} bytes of audio")
            break

if __name__ == "__main__":
    asyncio.run(test_greeting())
