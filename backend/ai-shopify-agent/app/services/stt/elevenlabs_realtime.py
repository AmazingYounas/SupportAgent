"""
ElevenLabs Scribe v2 Realtime - Streaming STT

WebSocket-based streaming speech-to-text.
Corrected to use the actual ElevenLabs Realtime API protocol:
  - Client sends: {"message_type": "input_audio_chunk", "audio_base_64": "..."}
  - Server sends: {"type": "partialTranscript", "text": "..."} 
                  {"type": "committedTranscript", "text": "..."}
"""
import asyncio
import base64
import json
import logging
import time
from typing import AsyncGenerator, Optional
import aiohttp

from app.services.stt.base import STTProvider
from app.config import settings

logger = logging.getLogger(__name__)


class ElevenLabsRealtimeSTT(STTProvider):
    """
    ElevenLabs Scribe v2 Realtime - True streaming STT via WebSocket.
    
    Uses the correct ElevenLabs Realtime STT WebSocket protocol.
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._ws_url = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Lazy session creation."""
        import socket
        if self._session is None or self._session.closed:
            # Force IPv4 to prevent getaddrinfo resolution errors on Windows asyncio.
            # Use default ThreadedResolver (not AsyncResolver) — aiodns fails on Windows.
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def transcribe_batch(self, audio_buffer: bytes) -> str:
        """
        Fallback: Use streaming internally for single utterance.
        """
        logger.info("[STT:ElevenLabsRealtime] Using realtime streaming for batch request")
        full_transcript = ""
        async for partial in self.transcribe_stream(self._buffer_to_stream(audio_buffer)):
            full_transcript = partial  # Always take the latest
        return full_transcript.strip()
    
    async def transcribe_stream(
        self, 
        audio_stream: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        True streaming STT via WebSocket.
        Yields partial/committed transcripts as audio arrives.
        
        Protocol (ElevenLabs Realtime STT):
          Client -> Server:
            {"message_type": "input_audio_chunk", "audio_base_64": "<base64>"}
            {"message_type": "flush"}  (end of stream)
          Server -> Client:
            {"type": "partialTranscript", "text": "..."} 
            {"type": "committedTranscript", "text": "..."}
        """
        logger.info("[STT:ElevenLabsRealtime] 🔌 Connecting to Scribe v2 Realtime...")
        
        headers = {
            "xi-api-key": self.api_key,
        }
        
        # Query parameters for the WebSocket handshake
        params = {
            "model_id": "scribe_v2_realtime",
            "language_code": "en",
            "audio_format": "pcm_16000",
            "commit_strategy": "manual",
        }
        
        session = self._get_session()
        transcript_queue: asyncio.Queue[Optional[dict]] = asyncio.Queue(maxsize=10)
        
        try:
            async with session.ws_connect(
                self._ws_url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=45)
            ) as ws:
                logger.info("[STT:ElevenLabsRealtime] ✅ WebSocket connected - streaming audio")
                
                async def send_loop():
                    """Send audio chunks to WebSocket using correct field names."""
                    try:
                        chunk_count = 0
                        async for chunk in audio_stream:
                            if chunk:
                                audio_b64 = base64.b64encode(chunk).decode('utf-8')
                                await ws.send_str(json.dumps({
                                    "message_type": "input_audio_chunk",
                                    "audio_base_64": audio_b64,
                                    "commit": False,
                                    "sample_rate": 16000,
                                }))
                                chunk_count += 1
                        # Manual commit is sent as a final chunk with commit=true.
                        await ws.send_str(json.dumps({
                            "message_type": "input_audio_chunk",
                            "audio_base_64": "",
                            "commit": True,
                            "sample_rate": 16000,
                        }))
                        logger.info(f"[STT:ElevenLabsRealtime] Sent {chunk_count} audio chunks + final commit")
                    except Exception as e:
                        logger.error(f"[STT:ElevenLabsRealtime] Send error: {e}", exc_info=True)
                
                async def receive_loop():
                    """Receive transcripts from WebSocket using correct event types."""
                    try:
                        committed_text = ""
                        idle_timeout_s = 20.0
                        last_message_time = time.monotonic()
                        
                        async for msg in ws:
                            now = time.monotonic()
                            if now - last_message_time > idle_timeout_s:
                                logger.warning(f"[STT:ElevenLabsRealtime] Idle timeout ({idle_timeout_s}s)")
                                break
                            last_message_time = now

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    msg_type = (data.get("type") or data.get("message_type") or "").strip()
                                    msg_type_norm = msg_type.lower().replace("-", "_")
                                    
                                    if msg_type_norm in ("partialtranscript", "partial_transcript"):
                                        text = (data.get("text") or data.get("transcript") or "").strip()
                                        if text:
                                            logger.debug(f"[STT:ElevenLabsRealtime] Partial: {text[:80]}")
                                            await transcript_queue.put({"text": text, "is_final": False})
                                    
                                    elif msg_type_norm in (
                                        "committedtranscript",
                                        "committed_transcript",
                                        "committed_transcript_with_timestamps",
                                    ):
                                        text = (data.get("text") or data.get("transcript") or "").strip()
                                        if text:
                                            committed_text = (committed_text + " " + text).strip()
                                            logger.info(f"[STT:ElevenLabsRealtime] Committed: {committed_text[:80]}")
                                            await transcript_queue.put({"text": committed_text, "is_final": True})
                                    
                                    elif msg_type_norm == "error":
                                        logger.error(f"[STT:ElevenLabsRealtime] Server error: {data}")

                                    elif msg_type_norm in ("sessionstarted", "session_started"):
                                        logger.info(f"[STT:ElevenLabsRealtime] Session started: {data}")

                                    
                                    elif msg_type_norm in ("done", "transcript_done"):
                                        logger.info("[STT:ElevenLabsRealtime] Server signalled done")
                                        break

                                    else:
                                        logger.debug(
                                            f"[STT:ElevenLabsRealtime] Ignored msg type '{msg_type}': {str(data)[:200]}"
                                        )
                                        
                                except json.JSONDecodeError:
                                    logger.warning(f"[STT:ElevenLabsRealtime] Invalid JSON: {msg.data[:200]}")
                                    
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"[STT:ElevenLabsRealtime] WebSocket error: {ws.exception()}")
                                break
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.info("[STT:ElevenLabsRealtime] WebSocket closed by server")
                                break
                        
                        # Final push of committed text
                        if committed_text:
                            await transcript_queue.put({"text": committed_text, "is_final": True})
                    except Exception as e:
                        logger.error(f"[STT:ElevenLabsRealtime] Receive error: {e}", exc_info=True)
                    finally:
                        await transcript_queue.put(None)  # Signal done
                
                # Run both send and receive concurrently
                send_task = asyncio.create_task(send_loop())
                receive_task = asyncio.create_task(receive_loop())
                
                # Yield transcripts as they arrive
                try:
                    while True:
                        transcript_data = await transcript_queue.get()
                        if transcript_data is None:
                            break
                        yield transcript_data
                finally:
                    # Cleanup
                    if not send_task.done():
                        send_task.cancel()
                    if not receive_task.done():
                        receive_task.cancel()
                    await asyncio.gather(send_task, receive_task, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"[STT:ElevenLabsRealtime] Connection error: {e}", exc_info=True)
            raise
    
    def _buffer_to_stream(self, audio_buffer: bytes) -> AsyncGenerator[bytes, None]:
        """Convert a buffer to an async stream for compatibility."""
        async def stream():
            chunk_size = 4096
            for i in range(0, len(audio_buffer), chunk_size):
                yield audio_buffer[i:i + chunk_size]
        return stream()
    
    async def aclose(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("[STT:ElevenLabsRealtime] Session closed")
