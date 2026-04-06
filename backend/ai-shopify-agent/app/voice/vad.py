"""
Voice Activity Detection (VAD) — Format-agnostic, production-ready.

Accepts any audio format (WebM, PCM, etc.) and uses appropriate detection method:
- PCM: Energy-based detection (amplitude threshold)
- WebM/Opus: Byte-size heuristic (compressed size indicates activity)

State machine:
  IDLE     → SPEAKING  (activity detected)
  SPEAKING → SILENCE   (activity drops)
  SILENCE  → SPEAKING  (false silence, activity resumes)
  SILENCE  → IDLE      (silence held for threshold duration → fires speech_end)
"""
import asyncio
import logging
import time
from enum import Enum, auto
from typing import Callable, Awaitable

from app.config import settings
from app.voice.audio_utils import compute_audio_activity, WEBM_MAGIC

logger = logging.getLogger(__name__)


class VADState(Enum):
    IDLE = auto()
    SPEAKING = auto()
    SILENCE = auto()


class VAD:
    """
    Stateful Voice Activity Detector for a single session.
    
    Features:
    - Format-agnostic (works with WebM, PCM, or any audio format)
    - Configurable thresholds via settings
    - Automatic speech_start/speech_end callbacks
    - Minimum duration filtering (ignores very short utterances)
    
    Usage:
        vad = VAD(
            on_speech_start=async_callback,
            on_speech_end=async_callback_with_buffer
        )
        await vad.feed(audio_chunk)  # Call for each incoming chunk
        await vad.flush()            # Call on disconnect
    """

    def __init__(
        self,
        on_speech_start: Callable[[], Awaitable[None]],
        on_speech_end: Callable[[bytes], Awaitable[None]],
    ):
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end

        self._state = VADState.IDLE
        self._speech_buffer: list[bytes] = []
        self._speech_start_ts: float = 0.0
        self._silence_task: asyncio.Task | None = None
        self._webm_header: bytes | None = None

    async def feed(self, chunk: bytes) -> None:
        """
        Process one incoming audio chunk.
        
        Automatically detects format and applies appropriate activity detection.
        Triggers callbacks when speech starts/ends.
        """
        if len(chunk) >= 4 and chunk[:4] == WEBM_MAGIC:
            self._webm_header = chunk
            logger.info(f"[VAD] Captured WebM header ({len(chunk)}b)")
            return

        is_active, metadata = compute_audio_activity(chunk)
        
        # Log activity with format-specific details (INFO level for debugging)
        if metadata["method"] == "energy":
            logger.info(
                f"[VAD] 🎵 {metadata['size']}b | "
                f"energy={metadata['energy']:.0f} | "
                f"state={self._state.name} | "
                f"active={is_active} | "
                f"threshold={settings.VAD_SPEECH_THRESHOLD}"
            )
        else:
            logger.info(
                f"[VAD] 🎵 {metadata['size']}b | "
                f"format={metadata['format']} | "
                f"state={self._state.name} | "
                f"active={is_active} | "
                f"threshold={settings.VAD_WEBM_THRESHOLD}b"
            )

        if is_active:
            self._speech_buffer.append(chunk)
            self._cancel_silence_timer()

            if self._state == VADState.IDLE:
                self._state = VADState.SPEAKING
                self._speech_start_ts = time.monotonic()
                logger.info("[VAD] ✅ speech_start_detected")
                await self._on_speech_start()

            elif self._state == VADState.SILENCE:
                self._state = VADState.SPEAKING
                logger.debug("[VAD] 🔄 silence cancelled — user resumed speaking")

            # Check hard max limit
            if self._state == VADState.SPEAKING:
                duration = time.monotonic() - self._speech_start_ts
                if duration > settings.VAD_MAX_SPEECH_DURATION:
                    logger.warning(f"[VAD] ⚠️ Max speech duration ({settings.VAD_MAX_SPEECH_DURATION}s) reached — forcing end")
                    asyncio.create_task(self.force_end())

        else:
            # Low-activity chunk
            if self._state == VADState.SPEAKING:
                self._state = VADState.SILENCE
                self._start_silence_timer()

    async def flush(self) -> None:
        """
        Force speech_end event.
        Call this when the connection closes to process any buffered audio.
        """
        self._cancel_silence_timer()
        if self._state in (VADState.SPEAKING, VADState.SILENCE):
            await self._fire_speech_end()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Internal Methods
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _start_silence_timer(self) -> None:
        """Start countdown to speech_end."""
        self._cancel_silence_timer()
        self._silence_task = asyncio.create_task(self._silence_timeout())

    def _cancel_silence_timer(self) -> None:
        """Cancel pending speech_end countdown."""
        if self._silence_task and not self._silence_task.done():
            self._silence_task.cancel()
        self._silence_task = None

    async def force_end(self) -> None:
        """Force speech_end immediately, bypassing silence timeout."""
        self._cancel_silence_timer()
        if self._state in (VADState.SPEAKING, VADState.SILENCE):
            await self._fire_speech_end()

    async def _silence_timeout(self) -> None:
        """Wait for silence duration, then fire speech_end."""
        # Adaptive VAD: Faster cutoff for short phrases, more breathing room for long monologues.
        duration = time.monotonic() - self._speech_start_ts
        silence_thresh = 0.35 if duration < 1.5 else 0.50
        
        try:
            await asyncio.sleep(silence_thresh)
            if self._state == VADState.SILENCE:
                await self._fire_speech_end()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[VAD] ❌ Error in speech_end callback: {e}", exc_info=True)
        finally:
            self._silence_task = None

    async def _fire_speech_end(self) -> None:
        """
        Trigger speech_end callback with collected audio buffer.
        Filters out very short utterances (likely noise).
        Prepends stored WebM header when the buffer lacks one.
        """
        duration = time.monotonic() - self._speech_start_ts
        audio = b"".join(self._speech_buffer)

        if len(audio) >= 4 and audio[:4] != WEBM_MAGIC and self._webm_header is not None:
            logger.info("[VAD] Buffer missing WebM header — prepending stored header")
            audio = self._webm_header + audio

        self._speech_buffer = []
        self._state = VADState.IDLE

        # Filter out very short utterances
        if duration < settings.VAD_MIN_SPEECH_DURATION or len(audio) < settings.VAD_MIN_SPEECH_BYTES:
            logger.debug(
                f"[VAD] ⚠️ Utterance too short "
                f"({duration:.2f}s, {len(audio)}b) — ignored"
            )
            return

        logger.info(
            f"[VAD] ✅ speech_end_detected — "
            f"{duration:.2f}s, {len(audio):,}b"
        )
        await self._on_speech_end(audio)
