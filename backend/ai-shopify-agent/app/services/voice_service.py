import asyncio
import aiohttp
import io
import logging
import re
import json
import base64
import time
from typing import AsyncGenerator, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)


# Smart sentence boundary detection patterns
_ABBREVIATIONS = frozenset([
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr",
    "etc", "vs", "e", "g", "i", "e", "inc", "ltd", "co"  # e.g. and i.e. split into parts
])
_SENTENCE_ENDS = frozenset(".!?")
_MAX_BUFFER_CHARS = 300


def _is_sentence_boundary(text: str, pos: int) -> bool:
    """
    FIX 5: Smart sentence boundary detection.
    Returns True only if position is a REAL sentence end, not abbreviation/decimal/URL.
    """
    if pos >= len(text) or text[pos] not in _SENTENCE_ENDS:
        return False
    
    char = text[pos]
    
    # Look ahead for ellipsis (...) - only the LAST dot is a boundary
    if char == '.':
        # Count consecutive dots
        dot_count = 1
        check_pos = pos + 1
        while check_pos < len(text) and text[check_pos] == '.':
            dot_count += 1
            check_pos += 1
        
        # If this is part of ellipsis but not the last dot, skip it
        if dot_count >= 2:
            # Check if this is the last dot in the sequence
            if pos + 1 < len(text) and text[pos + 1] == '.':
                return False  # Not the last dot yet
            # This IS the last dot in ellipsis - treat as boundary
        
        # Check for abbreviations (Dr. Mr. etc.)
        word_start = pos - 1
        while word_start >= 0 and text[word_start].isalpha():
            word_start -= 1
        word = text[word_start + 1:pos].lower()
        
        if word in _ABBREVIATIONS:
            # Exception: if it's end of text, it IS a boundary
            if pos == len(text) - 1:
                return True
            return False
        
        # Check for decimals (19.99, 3.14)
        if pos > 0 and pos + 1 < len(text):
            if text[pos - 1].isdigit() and text[pos + 1].isdigit():
                return False
        
        # Check for URLs (example.com, www.site.org)
        if pos + 1 < len(text) and text[pos + 1].isalpha():
            # Look for domain pattern
            if word_start >= 0 and text[word_start:pos + 1].count('.') >= 1:
                # Likely a URL component
                return False
    
    # Multi-punctuation: ?! or !? - only the LAST one is a boundary
    if char in '!?':
        if pos + 1 < len(text) and text[pos + 1] in '!?':
            return False  # Not the last punctuation yet
    
    # Check if followed by capital letter or whitespace (real sentence end)
    if pos + 1 < len(text):
        next_char = text[pos + 1]
        if next_char.isspace() or next_char.isupper():
            return True
        # If next char is lowercase, probably not a sentence end
        if next_char.islower():
            return False
    
    # End of text is always a boundary
    if pos == len(text) - 1:
        return True
    
    return False


class VoiceService:
    """
    ElevenLabs voice pipeline with production-grade reliability:
      - Bounded queues (FIX 1)
      - Smart sentence detection (FIX 5)
      - Task cancellation on disconnect (FIX 6)
      - Connection pool scaling (FIX 7)
      - Guaranteed cleanup (FIX 3)
    """

    def __init__(self):
        self.voice_id = settings.ELEVENLABS_VOICE_ID
        self.model_id = settings.ELEVENLABS_MODEL_ID
        self.api_key = settings.ELEVENLABS_API_KEY
        self.output_format = settings.ELEVENLABS_OUTPUT_FORMAT
        self.optimize_latency = settings.ELEVENLABS_OPTIMIZE_LATENCY

        self._stt_url = "https://api.elevenlabs.io/v1/speech-to-text"
        self._tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"

        # PCM output format: raw Int16 LE, 22050 Hz mono — matches AudioWorklet frontend.
        # Falls back to settings value for the PTT (push-to-talk) endpoint which uses MP3.
        self._pcm_output_format = settings.ELEVENLABS_PCM_OUTPUT_FORMAT

        # FIX 7: Connection pool scaling for sentence-chunked TTS
        self._connector = aiohttp.TCPConnector(limit=500, limit_per_host=100)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # FIX 6: Track active TTS tasks for cancellation
        self._active_tasks: List[asyncio.Task] = []

    # ------------------------------------------------------------------ #
    #  Session management                                                  #
    # ------------------------------------------------------------------ #

    def _get_session(self) -> aiohttp.ClientSession:
        """Return (or lazily create) the shared HTTP session with scaled connection pool."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(connector=self._connector)
        return self._session

    async def aclose(self):
        """
        FIX 6: Cancel all active TTS tasks and close session.
        Prevents dangling tasks after WebSocket disconnect.
        """
        # Cancel all active TTS tasks
        for task in self._active_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cancellation with timeout
        if self._active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                logger.warning("[VoiceService] Some TTS tasks did not cancel in time")
        
        self._active_tasks.clear()
        
        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ #
    #  STT                                                                 #
    # ------------------------------------------------------------------ #

    async def transcribe_audio(self, audio_buffer: bytes) -> str:
        """
        Batch STT via ElevenLabs Scribe REST API.
        Called after END_OF_SPEECH with the complete collected audio buffer.
        This is the primary STT path — reliable, no WS race conditions.
        """
        if len(audio_buffer) < 1000:
            logger.warning("[STT] Audio buffer too small, skipping transcription")
            return ""

        logger.info(f"[STT] Sending {len(audio_buffer):,} bytes to ElevenLabs Scribe")
        logger.info(f"[TIMING] STT_START: {time.time()*1000:.3f}")

        headers = {"xi-api-key": self.api_key}
        session = self._get_session()

        try:
            form = aiohttp.FormData()
            form.add_field(
                "file",
                io.BytesIO(audio_buffer),
                filename="audio.webm",
                content_type="audio/webm;codecs=opus",
            )
            form.add_field("model_id", "scribe_v1")
            form.add_field("language_code", "en")

            timeout = aiohttp.ClientTimeout(total=30)
            async with session.post(
                self._stt_url, headers=headers, data=form, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"[STT] ElevenLabs STT {resp.status}: {error_text[:200]}")
                    return ""
                result = await resp.json()
                transcript = result.get("text", "").strip()
                if transcript:
                    logger.info(f"[STT] Transcribed: {transcript[:120]}")
                else:
                    logger.warning("[STT] Empty transcript returned")
                return transcript
        except Exception as e:
            logger.error(f"[STT] Transcription error: {e}")
            return ""

    # Keep this for any callers that still pass a generator (unused but safe)
    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
    ) -> str:
        """Collect stream into buffer then transcribe. Kept for API compatibility."""
        audio_buffer = bytearray()
        async for chunk in audio_stream:
            if chunk:
                audio_buffer.extend(chunk)
        return await self.transcribe_audio(bytes(audio_buffer))

    # ------------------------------------------------------------------ #
    #  TTS — sentence-chunked streaming with production fixes            #
    # ------------------------------------------------------------------ #

    async def stream_audio_pcm(
        self,
        text_chunk_generator: AsyncGenerator[str, None],
    ) -> AsyncGenerator[bytes, None]:
        """
        Duplex-endpoint TTS: outputs raw PCM Int16 LE at 22050 Hz.
        Drop-in replacement for stream_audio_from_text() for the duplex path.
        The only difference is output_format = pcm_22050 and Accept = audio/pcm.
        """
        async for chunk in self._stream_audio(text_chunk_generator, pcm=True):
            yield chunk

    async def stream_audio_from_text(
        self,
        text_chunk_generator: AsyncGenerator[str, None],
    ) -> AsyncGenerator[bytes, None]:
        """MP3 streaming TTS — used by the push-to-talk endpoint."""
        async for chunk in self._stream_audio(text_chunk_generator, pcm=False):
            yield chunk

    async def _stream_audio(
        self,
        text_chunk_generator: AsyncGenerator[str, None],
        pcm: bool = False,
    ) -> AsyncGenerator[bytes, None]:
        """
        Shared TTS engine.
        pcm=True  → raw PCM Int16 LE 22050Hz (duplex endpoint, AudioWorklet frontend)
        pcm=False → MP3 (push-to-talk endpoint, browser decodeAudioData)
        """
        out_format  = self._pcm_output_format if pcm else self.output_format
        accept_mime = "audio/pcm"             if pcm else "audio/mpeg"

        meta_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        tts_first_chunk_logged = False

        async def _tts_sentence(text: str, audio_q: asyncio.Queue) -> None:
            nonlocal tts_first_chunk_logged
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": accept_mime,
            }
            payload = {
                "text": text,
                "model_id": self.model_id,
                "language_code": "en",
                "optimize_streaming_latency": self.optimize_latency,
                "output_format": out_format,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
            }
            session = self._get_session()
            
            # FIX 3: try/finally guarantees sentinel even on failure
            try:
                for attempt in range(1, 4):
                    try:
                        timeout = aiohttp.ClientTimeout(total=60)
                        async with session.post(
                            self._tts_url, json=payload, headers=headers, timeout=timeout
                        ) as resp:
                            if resp.status != 200:
                                error_text = await resp.text()
                                raise RuntimeError(f"ElevenLabs TTS {resp.status}: {error_text}")
                            async for chunk in resp.content.iter_chunked(8192):
                                if chunk:
                                    await audio_q.put(chunk)
                                    if not tts_first_chunk_logged:
                                        tts_first_chunk_logged = True
                                        logger.info(f"[TIMING] TTS_FIRST_CHUNK: {time.time()*1000:.3f}")
                        break  # success
                    except Exception as e:
                        logger.error(f"[TTS] Error on sentence (attempt {attempt}/3): {e}")
                        if attempt < 3:
                            # No artificial delays; retry immediately for measurement.
                            continue
                        else:
                            # All retries failed - log but don't crash
                            logger.error(f"[TTS] Failed to synthesize: {text[:60]}")
            finally:
                # FIX 3: ALWAYS signal completion, even on failure
                await audio_q.put(None)

        async def _llm_producer() -> None:
            """
            FIX 5: Smart sentence boundary detection.
            Reads LLM tokens, detects REAL sentence ends (not "Dr." or "19.99").
            """
            buffer = ""
            async for token in text_chunk_generator:
                if not token:
                    continue
                buffer += token
                
                # FIX 5: Use smart boundary detection
                # Check if we hit a real sentence end
                if len(buffer) >= _MAX_BUFFER_CHARS:
                    # Force flush on buffer overflow
                    sentence = buffer.strip()
                    if sentence:
                        # FIX 1: Bounded queue with maxsize=10
                        audio_q: asyncio.Queue = asyncio.Queue(maxsize=10)
                        await meta_queue.put(audio_q)
                        task = asyncio.create_task(_tts_sentence(sentence, audio_q))
                        self._active_tasks.append(task)  # FIX 6: Track for cancellation
                        logger.debug(f"[TTS] Queued sentence (overflow, {len(sentence)} chars): {sentence[:60]}")
                    buffer = ""
                else:
                    # Check for smart sentence boundary
                    # Avoid treating the end of the *current buffer* as a sentence boundary.
                    # This prevents premature segmentation when tokens stream in incrementally.
                    for i in range(len(buffer) - 2, -1, -1):
                        if _is_sentence_boundary(buffer, i):
                            sentence = buffer[:i + 1].strip()
                            if sentence:
                                # FIX 1: Bounded queue
                                audio_q = asyncio.Queue(maxsize=10)
                                await meta_queue.put(audio_q)
                                task = asyncio.create_task(_tts_sentence(sentence, audio_q))
                                self._active_tasks.append(task)  # FIX 6
                                logger.debug(f"[TTS] Queued sentence ({len(sentence)} chars): {sentence[:60]}")
                            buffer = buffer[i + 1:].lstrip()
                            break

            # Flush any remaining tokens
            sentence = buffer.strip()
            if sentence:
                audio_q = asyncio.Queue(maxsize=10)
                await meta_queue.put(audio_q)
                task = asyncio.create_task(_tts_sentence(sentence, audio_q))
                self._active_tasks.append(task)
                logger.debug(f"[TTS] Queued final sentence ({len(sentence)} chars): {sentence[:60]}")

            # Signal consumer that no more sentences are coming
            await meta_queue.put(None)

        if not text_chunk_generator:
            logger.warning("[TTS] Empty text generator — nothing to synthesize")
            return

        # Launch producer as concurrent task
        producer_task = asyncio.create_task(_llm_producer())

        # Consume sentence queues in order (preserves natural flow)
        try:
            while True:
                sentence_q = await meta_queue.get()
                if sentence_q is None:  # all sentences dispatched
                    break
                # Drain this sentence's audio queue before moving to next
                while True:
                    chunk = await sentence_q.get()
                    if chunk is None:  # sentence TTS complete
                        break
                    yield chunk
        finally:
            # Ensure producer coroutine is not left running on early exit.
            if not producer_task.done():
                producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass
            # Cancel any in-flight per-sentence TTS tasks.
            pending = [t for t in self._active_tasks if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                try:
                    await asyncio.gather(*pending, return_exceptions=True)
                except asyncio.CancelledError:
                    pass
            # Prune completed tasks to prevent unbounded list growth.
            self._active_tasks = [t for t in self._active_tasks if not t.done()]
