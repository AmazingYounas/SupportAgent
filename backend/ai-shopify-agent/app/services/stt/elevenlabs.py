"""
ElevenLabs STT Provider (Batch-only)

Current implementation using ElevenLabs Scribe API.
Batch-only (no streaming support from ElevenLabs yet).
"""
import aiohttp
import io
import logging
import time
from typing import AsyncGenerator, Optional

from app.config import settings
from app.services.stt.base import STTProvider

logger = logging.getLogger(__name__)


class ElevenLabsSTT(STTProvider):
    """ElevenLabs Scribe STT provider."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._stt_url = "https://api.elevenlabs.io/v1/speech-to-text"
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Lazy session creation with connection pooling."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                keepalive_timeout=300,
            )
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def transcribe_batch(self, audio_buffer: bytes) -> str:
        """
        Batch STT via ElevenLabs Scribe REST API.
        Waits for complete transcription before returning.
        
        FIX: Added validation to prevent crashes on empty/corrupt audio.
        """
        # Validate audio buffer
        if not audio_buffer:
            logger.warning("[STT:ElevenLabs] Empty audio buffer, skipping")
            return ""
        
        if len(audio_buffer) < 1000:
            logger.warning(f"[STT:ElevenLabs] Audio buffer too small ({len(audio_buffer)}b), skipping")
            return ""
        
        # Check if buffer looks valid (not all zeros)
        if audio_buffer == b'\x00' * len(audio_buffer):
            logger.warning("[STT:ElevenLabs] Audio buffer is all zeros (silence), skipping")
            return ""
        
        logger.info(f"[STT:ElevenLabs] 🎤 Sending {len(audio_buffer):,}b to Scribe")
        t_start = time.time() * 1000
        
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
                    logger.error(f"[STT:ElevenLabs] ❌ API error {resp.status}: {error_text[:200]}")
                    return ""
                
                result = await resp.json()
                transcript = result.get("text", "").strip()
                
                t_end = time.time() * 1000
                logger.info(
                    f"[STT:ElevenLabs] ✅ Transcribed in {t_end - t_start:.0f}ms: "
                    f"{transcript[:120]}"
                )
                return transcript
        
        except asyncio.TimeoutError:
            logger.error("[STT:ElevenLabs] ❌ Transcription timeout (30s)")
            return ""
        except Exception as e:
            logger.error(f"[STT:ElevenLabs] ❌ Transcription error: {e}")
            return ""
    
    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        ElevenLabs doesn't support streaming STT yet.
        Fallback: collect all chunks then batch transcribe.
        """
        logger.warning("[STT:ElevenLabs] Streaming not supported, falling back to batch")
        
        audio_buffer = bytearray()
        async for chunk in audio_stream:
            if chunk:
                audio_buffer.extend(chunk)
        
        transcript = await self.transcribe_batch(bytes(audio_buffer))
        if transcript:
            yield transcript
    
    async def aclose(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("[STT:ElevenLabs] Session closed")
