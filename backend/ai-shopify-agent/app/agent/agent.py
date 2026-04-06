from typing import Tuple, AsyncGenerator, Optional, Callable, Awaitable
from sqlalchemy.orm import Session
import asyncio
import logging
import time

from app.agent.graph import create_tools, create_llm_with_tools, create_agent_graph
from app.agent.state import ConversationState
from app.agent.prompts import SYSTEM_PROMPT

from app.services.order_service import OrderService
from app.services.voice_service import VoiceService
from app.memory.session_memory import SessionMemory
from app.memory.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)


class SupportAgent:
    """
    Main entrypoint for the AI Agent Backend.
    Each instance owns its own isolated tools, LLM, and graph to prevent
    concurrency issues across concurrent WebSocket sessions.
    """

    def __init__(self, db_session: Optional[Session] = None):
        self.db = db_session

        self.order_service = OrderService(self.db)
        self.voice_service = VoiceService()

        if db_session:
            self.long_term_memory = LongTermMemory(self.db)
        else:
            self.long_term_memory = None

        self.tools = create_tools()

        for tool in self.tools:
            if hasattr(tool, "order_service"):
                tool.order_service = self.order_service
            if hasattr(tool, "long_term_memory") and self.long_term_memory:
                tool.long_term_memory = self.long_term_memory

        self.llm = create_llm_with_tools(self.tools)
        self.app_graph = create_agent_graph(self.tools, self.llm)

    # ------------------------------------------------------------------ #
    #  Cleanup                                                             #
    # ------------------------------------------------------------------ #

    async def aclose(self):
        """
        FIX 4: Clean up resources when agent is destroyed.
        Prevents ClientSession leak that causes "Too many open files" after ~1000 conversations.
        """
        await self.voice_service.aclose()
        # Future: close shopify_service session if it has one

    # ------------------------------------------------------------------ #
    #  Text Chat                                                           #
    # ------------------------------------------------------------------ #

    async def chat_text(
        self,
        user_message: str,
        session_memory: SessionMemory,
        customer_id: str = None,
    ) -> Tuple[str, SessionMemory]:
        """Standard text-in, text-out interface."""
        if not session_memory.get_messages():
            session_memory.set_system_prompt(SYSTEM_PROMPT)

        session_memory.add_user_message(user_message)

        state = ConversationState(
            messages=session_memory.get_messages(),
            customer_id=customer_id,
            active_order_id=None,
        )

        result_state = await self.app_graph.ainvoke(state)

        final_message = result_state["messages"][-1].content
        session_memory.add_ai_message(final_message)

        return final_message, session_memory

    # ------------------------------------------------------------------ #
    #  Voice Chat (streaming)                                              #
    # ------------------------------------------------------------------ #

    async def chat_voice_stream(
        self,
        user_message: str,
        session_memory: SessionMemory,
        customer_id: str = None,
        on_text_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Voice-in (text already transcribed), audio-out interface.
        Streams LLM tokens sentence-by-sentence into ElevenLabs TTS,
        yielding audio bytes as soon as the first sentence is ready —
        without waiting for the LLM to finish.

        Guarantees session memory is updated via try/finally even if TTS
        fails or the caller cancels mid-stream.
        """
        if not session_memory.get_messages():
            session_memory.set_system_prompt(SYSTEM_PROMPT)

        session_memory.add_user_message(user_message)

        state = ConversationState(
            messages=session_memory.get_messages(),
            customer_id=customer_id,
            active_order_id=None,
        )

        full_response = ""
        first_token_received = False
        thinking_start = asyncio.get_event_loop().time()

        async def _text_chunk_generator():
            nonlocal full_response, first_token_received
            
            async for event in self.app_graph.astream_events(state, version="v2"):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        if not first_token_received:
                            first_token_received = True
                            elapsed = asyncio.get_event_loop().time() - thinking_start
                            logger.debug(f"[LLM] First token after {elapsed*1000:.0f}ms")

                            logger.info(f"[TIMING] LLM_FIRST_TOKEN: {time.time()*1000:.3f}")
                        
                        full_response += chunk
                        logger.info(f"[TIMING] LLM_TOKEN: {chunk} {time.time()*1000:.3f}")

                        if on_text_chunk is not None:
                            await on_text_chunk(chunk)
                        yield chunk

        # try/finally guarantees add_ai_message even if TTS errors mid-stream
        # or the WebSocket client disconnects.
        completed_normally = False
        try:
            async for audio_bytes in self.voice_service.stream_audio_from_text(
                _text_chunk_generator()
            ):
                yield audio_bytes
            completed_normally = True
        finally:
            if completed_normally and full_response:
                stored_response = full_response
                session_memory.add_ai_message(stored_response)
            elif not completed_normally:
                # Cancellation/error path: avoid keeping orphan user turns
                # without a corresponding assistant response.
                session_memory.remove_last_user_message(user_message)
            # IMPORTANT: Do not close aiohttp sessions per turn.
            # VoiceService teardown happens in SupportAgent.aclose().

            if completed_normally and not first_token_received:
                logger.warning("LLM STREAMING NOT ACTIVE")
