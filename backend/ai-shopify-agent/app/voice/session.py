"""
Per-connection duplex session state.

Tracks:
  - conversation memory
  - current pipeline tasks (STT, LLM, TTS)
  - speaking state
  - interrupt coordination
"""
import asyncio
import logging
from enum import Enum, auto
from typing import Optional

from app.memory.session_memory import SessionMemory

logger = logging.getLogger(__name__)


class SpeakingState(Enum):
    IDLE = auto()
    USER_SPEAKING = auto()   # VAD detected speech, collecting audio
    AI_SPEAKING = auto()     # TTS audio is being streamed to client


class DuplexSession:
    """
    Holds all mutable state for one full-duplex WebSocket connection.
    Thread-safe via asyncio — all access from the same event loop.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.memory = SessionMemory()
        self.state = SpeakingState.IDLE

        # Set when the AI pipeline should abort immediately
        self.interrupt: asyncio.Event = asyncio.Event()

        # Active pipeline task (LLM+TTS coroutine)
        self._pipeline_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    #  Pipeline task management                                            #
    # ------------------------------------------------------------------ #

    def set_pipeline_task(self, task: asyncio.Task) -> None:
        self._pipeline_task = task

    async def cancel_pipeline(self) -> None:
        """
        Interrupt the running AI pipeline immediately.
        Sets the interrupt event so the pipeline coroutine can exit cleanly,
        then cancels the task if it doesn't stop within 500ms.
        """
        self.interrupt.set()
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._pipeline_task),
                    timeout=0.5,
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._pipeline_task = None
        self.interrupt.clear()
        logger.info(f"[Session:{self.session_id}] pipeline cancelled")

    # ------------------------------------------------------------------ #
    #  State transitions                                                   #
    # ------------------------------------------------------------------ #

    def mark_user_speaking(self) -> None:
        self.state = SpeakingState.USER_SPEAKING
        logger.debug(f"[Session:{self.session_id}] → USER_SPEAKING")

    def mark_ai_speaking(self) -> None:
        self.state = SpeakingState.AI_SPEAKING
        logger.debug(f"[Session:{self.session_id}] → AI_SPEAKING")

    def mark_idle(self) -> None:
        self.state = SpeakingState.IDLE
        logger.debug(f"[Session:{self.session_id}] → IDLE")

    @property
    def ai_is_speaking(self) -> bool:
        return self.state == SpeakingState.AI_SPEAKING
