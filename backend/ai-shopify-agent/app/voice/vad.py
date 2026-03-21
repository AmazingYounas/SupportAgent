"""
Voice Activity Detection (VAD) — Energy-based, PCM Int16 aware.

Accepts raw PCM Int16 LE chunks (48kHz mono, ~20ms each from AudioWorklet).
Computes average absolute amplitude per chunk as the activity signal.

State machine:
  IDLE     → SPEAKING  (energy > SPEECH_THRESHOLD)
  SPEAKING → SILENCE   (energy < SILENCE_THRESHOLD for one chunk)
  SILENCE  → SPEAKING  (energy > SPEECH_THRESHOLD — false silence)
  SILENCE  → IDLE      (silence held for SILENCE_DURATION_S → fires speech_end)
"""
import asyncio
import logging
import struct
import time
from enum import Enum, auto
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# ── Tunable thresholds ────────────────────────────────────────────────────
# Average absolute amplitude out of 32767 (for PCM mode).
# Raise SPEECH_THRESHOLD if background noise triggers false starts.
SPEECH_THRESHOLD  = 300    # ~0.9% of full scale — triggers speech_start
SILENCE_THRESHOLD = 150    # below this = silence
SILENCE_DURATION_S = 0.65  # seconds of continuous silence before speech_end
MIN_SPEECH_DURATION_S = 0.25  # ignore utterances shorter than this
MIN_SPEECH_BYTES = 3000    # ignore buffers smaller than this (for WebM: ~3KB = ~0.3s)


class VADState(Enum):
    IDLE     = auto()
    SPEAKING = auto()
    SILENCE  = auto()


def _pcm_energy(chunk: bytes) -> float:
    """
    Compute average absolute amplitude of a raw PCM Int16 LE buffer.
    Returns a float in [0, 32767].
    Returns 0.0 for empty or malformed input.
    
    For WebM/Opus chunks (which are NOT PCM), this will return garbage values.
    The VAD falls back to byte-size heuristics in that case.
    """
    n = len(chunk) // 2  # number of Int16 samples
    if n == 0:
        return 0.0
    
    # Quick check: if this looks like WebM (starts with 0x1A 0x45 0xDF 0xA3), 
    # return a signal value that triggers byte-size fallback
    if len(chunk) >= 4 and chunk[0:4] == b'\x1a\x45\xdf\xa3':
        return -1.0  # Signal: not PCM, use byte-size heuristic
    
    try:
        # struct.unpack is faster than numpy for small chunks
        samples = struct.unpack_from(f"<{n}h", chunk)
        return sum(abs(s) for s in samples) / n
    except struct.error:
        # Not valid PCM, return signal for byte-size fallback
        return -1.0


class VAD:
    """
    Stateful VAD for a single WebSocket session.

    Designed for raw PCM Int16 LE input (AudioWorklet output).
    Also tolerates WebM/Opus chunks from MediaRecorder by falling back
    to a byte-size heuristic when the buffer is not valid PCM
    (i.e. length is odd or decoding fails).

    Usage:
        vad = VAD(on_speech_start=..., on_speech_end=...)
        await vad.feed(chunk_bytes)   # every incoming audio chunk
        await vad.flush()             # on disconnect
    """

    def __init__(
        self,
        on_speech_start: Callable[[], Awaitable[None]],
        on_speech_end:   Callable[[bytes], Awaitable[None]],
    ):
        self._on_speech_start = on_speech_start
        self._on_speech_end   = on_speech_end

        self._state            = VADState.IDLE
        self._speech_buffer:   list[bytes] = []
        self._speech_start_ts: float = 0.0
        self._silence_task:    asyncio.Task | None = None

    # ── Public API ────────────────────────────────────────────────────────

    async def feed(self, chunk: bytes) -> None:
        """Process one incoming audio chunk."""
        energy    = _pcm_energy(chunk)
        
        # Fallback for WebM/Opus: use byte-size heuristic
        # WebM chunks from MediaRecorder are typically 2-20KB for 250ms of audio
        if energy < 0:  # Signal from _pcm_energy that this is not PCM
            # Use byte-size as activity signal
            # Typical WebM chunk: 2-20KB for 250ms
            # Silence/noise: < 1KB
            is_active = len(chunk) >= 1500  # ~1.5KB threshold
            logger.info(
                f"[VAD] 🎵 feed {len(chunk)}b (WebM mode) "
                f"state={self._state.name} active={is_active} size_threshold=1500b"
            )
        else:
            # PCM mode: use energy threshold
            is_active = energy >= SPEECH_THRESHOLD
            logger.info(
                f"[VAD] 🎵 feed {len(chunk)}b energy={energy:.0f} "
                f"state={self._state.name} active={is_active} threshold={SPEECH_THRESHOLD}"
            )

        if is_active:
            self._speech_buffer.append(chunk)
            self._cancel_silence_timer()

            if self._state == VADState.IDLE:
                self._state = VADState.SPEAKING
                self._speech_start_ts = time.monotonic()
                logger.info("[VAD] speech_start_detected")
                await self._on_speech_start()

            elif self._state == VADState.SILENCE:
                self._state = VADState.SPEAKING
                logger.debug("[VAD] silence cancelled — user resumed")

        else:
            # Low-energy chunk
            if self._state == VADState.SPEAKING:
                self._state = VADState.SILENCE
                self._start_silence_timer()

    async def flush(self) -> None:
        """Force speech_end — call on client disconnect."""
        self._cancel_silence_timer()
        if self._state in (VADState.SPEAKING, VADState.SILENCE):
            await self._fire_speech_end()

    # ── Internal ──────────────────────────────────────────────────────────

    def _start_silence_timer(self) -> None:
        self._cancel_silence_timer()
        self._silence_task = asyncio.create_task(self._silence_timeout())

    def _cancel_silence_timer(self) -> None:
        if self._silence_task and not self._silence_task.done():
            self._silence_task.cancel()
        self._silence_task = None

    async def _silence_timeout(self) -> None:
        try:
            await asyncio.sleep(SILENCE_DURATION_S)
            if self._state == VADState.SILENCE:
                await self._fire_speech_end()
        except asyncio.CancelledError:
            pass

    async def _fire_speech_end(self) -> None:
        duration = time.monotonic() - self._speech_start_ts
        audio    = b"".join(self._speech_buffer)
        self._speech_buffer = []
        self._state         = VADState.IDLE

        if duration < MIN_SPEECH_DURATION_S or len(audio) < MIN_SPEECH_BYTES:
            logger.debug(
                f"[VAD] utterance too short ({duration:.2f}s, {len(audio)}b) — ignored"
            )
            return

        logger.info(f"[VAD] speech_end_detected — {duration:.2f}s, {len(audio):,}b")
        await self._on_speech_end(audio)
