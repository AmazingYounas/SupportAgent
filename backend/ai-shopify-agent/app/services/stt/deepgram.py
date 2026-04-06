"""
Deepgram STT Provider — Official SDK v6
Uses deepgram-sdk for reliable WebM/Opus transcription.
"""
import asyncio
import logging
import threading
from typing import AsyncGenerator

from deepgram import DeepgramClient
from deepgram.core.events import EventType

from app.services.stt.base import STTProvider

logger = logging.getLogger(__name__)


class DeepgramSTT(STTProvider):
    """Deepgram Nova-3 STT using official SDK v6."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = DeepgramClient(api_key=api_key)

    # ──────────────────────────────────────────────────────────────────
    # Batch (push-to-talk) — uses Prerecorded API, auto-detects WebM
    # ──────────────────────────────────────────────────────────────────
    async def transcribe_batch(self, audio_buffer: bytes) -> str:
        """
        Batch STT via Deepgram Prerecorded API.
        
        FIX: Added validation to prevent crashes on empty/corrupt audio.
        """
        # Validate audio buffer
        if not audio_buffer:
            logger.warning("[STT:Deepgram] Empty audio buffer, skipping")
            return ""
        
        if len(audio_buffer) < 1000:
            logger.warning(f"[STT:Deepgram] Buffer too small ({len(audio_buffer)}b), skipping")
            return ""
        
        # Check if buffer looks valid (not all zeros)
        if audio_buffer == b'\x00' * len(audio_buffer):
            logger.warning("[STT:Deepgram] Audio buffer is all zeros (silence), skipping")
            return ""

        logger.info(f"[STT:Deepgram] 🎤 Transcribing {len(audio_buffer):,}b")
        
        # Log first 20 bytes for debugging
        header_hex = audio_buffer[:20].hex()
        logger.debug(f"[STT:Deepgram] Header: {header_hex}")
        
        # Check if it starts with WebM magic bytes
        if audio_buffer[:4] == b'\x1a\x45\xdf\xa3':
            logger.debug("[STT:Deepgram] ✅ Valid WebM header detected")
        else:
            logger.warning(f"[STT:Deepgram] ⚠️ No WebM header! First 4 bytes: {audio_buffer[:4].hex()}")

        try:
            # Run synchronous SDK call in a thread so we don't block the event loop
            response = await asyncio.to_thread(
                self.client.listen.v1.media.transcribe_file,
                request=audio_buffer,
                model="nova-3",
                language="en",
                punctuate=True,
                smart_format=True,
            )

            channels = getattr(getattr(response, "results", None), "channels", None)
            if not channels:
                logger.warning("[STT:Deepgram] ⚠️ No channels in response")
                return ""

            alts = getattr(channels[0], "alternatives", None)
            if not alts:
                logger.warning("[STT:Deepgram] ⚠️ No alternatives in response")
                return ""

            transcript = (alts[0].transcript or "").strip()
            confidence = getattr(alts[0], "confidence", 0.0)

            if transcript:
                logger.info(f"[STT:Deepgram] ✅ '{transcript[:80]}' (conf={confidence:.2f})")
            else:
                logger.warning("[STT:Deepgram] ⚠️ Empty transcript — silence or bad audio?")

            return transcript

        except asyncio.TimeoutError:
            logger.error("[STT:Deepgram] ❌ Transcription timeout")
            return ""
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "INVALID_AUTH" in err_str or "Invalid credentials" in err_str:
                logger.error("[STT:Deepgram] ❌ Invalid API key — check DEEPGRAM_API_KEY in .env")
            else:
                logger.error(f"[STT:Deepgram] ❌ transcribe_batch error: {e}")
            import traceback; logger.debug(traceback.format_exc())
            return ""

    # ──────────────────────────────────────────────────────────────────
    # Streaming — uses Live API (for future full-duplex use)
    # ──────────────────────────────────────────────────────────────────
    async def transcribe_stream(
        self, audio_stream: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        Live streaming transcription via Deepgram SDK.
        Mirrors the official SDK example pattern.
        """
        logger.info("[STT:Deepgram] 🔌 Starting live transcription")

        transcript_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        try:
            connection = self.client.listen.v1.connect(
                model="nova-3",
                language="en",
                punctuate=True,
                interim_results=False,
                endpointing=300,
            )

            def on_message(result):
                channel = getattr(result, "channel", None)
                if channel and hasattr(channel, "alternatives"):
                    text = (channel.alternatives[0].transcript or "").strip()
                    is_final = getattr(result, "is_final", True)
                    if text and is_final:
                        logger.info(f"[STT:Deepgram] ✅ Live: '{text[:80]}'")
                        asyncio.run_coroutine_threadsafe(
                            transcript_queue.put(text), loop
                        )

            def on_error(error):
                logger.error(f"[STT:Deepgram] ❌ Live error: {error}")

            ready = threading.Event()
            connection.on(EventType.OPEN, lambda _: ready.set())
            connection.on(EventType.MESSAGE, on_message)
            connection.on(EventType.ERROR, on_error)

            # Start connection in background thread
            def run_connection():
                connection.start_listening()

            conn_thread = threading.Thread(target=run_connection, daemon=True)
            conn_thread.start()
            ready.wait(timeout=5)

            # Send audio chunks
            async def send_audio():
                try:
                    async for chunk in audio_stream:
                        if chunk:
                            await asyncio.to_thread(connection.send_media, chunk)
                    await asyncio.to_thread(connection.finish)
                except Exception as e:
                    logger.error(f"[STT:Deepgram] Send error: {e}")
                finally:
                    await transcript_queue.put(None)

            send_task = asyncio.create_task(send_audio())
            try:
                while True:
                    item = await transcript_queue.get()
                    if item is None:
                        break
                    yield item
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"[STT:Deepgram] ❌ Live error: {e}")
            import traceback; logger.debug(traceback.format_exc())

    async def aclose(self) -> None:
        logger.debug("[STT:Deepgram] Closed")
