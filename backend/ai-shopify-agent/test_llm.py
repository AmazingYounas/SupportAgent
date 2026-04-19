import asyncio
from app.agent.agent import SupportAgent
from app.memory.session_memory import SessionMemory

async def main():
    print("Initializing agent...")
    agent = SupportAgent()
    mem = SessionMemory()
    mem.add_user_message("Hello, hello, hello.")
    
    state = {
        "messages": mem.get_messages(),
        "customer_id": None,
        "active_order_id": None,
    }
    
    print("Testing astream_events...")
    async for event in agent.app_graph.astream_events(state, version="v2"):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            print(f"CHUNK: {repr(chunk.content)}")

if __name__ == "__main__":
    asyncio.run(main())
