from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from sqlalchemy.orm import Session
from typing import Dict, Optional
from collections import OrderedDict
import asyncio
import json
import logging
import traceback
import hmac
import hashlib
import base64
import time

from app.config import settings
from app.database.connection import get_db
from app.api.schemas import ChatRequest, ChatResponse, WebhookRequest
from app.agent.agent import SupportAgent
from app.memory.session_memory import SessionMemory
from app.database.repositories import ConversationRepository
from app.voice.vad import VAD
from app.voice.session import DuplexSession
from app.voice.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


async def _cancel_listener(websocket: WebSocket, cancel_event: asyncio.Event) -> None:
    """Listen for CANCEL_TURN from client during response generation."""
    try:
        while not cancel_event.is_set():
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                cancel_event.set()
                return
            if "text" in message and message["text"].strip() == "CANCEL_TURN":
                cancel_event.set()
                return
    except (WebSocketDisconnect, RuntimeError):
        cancel_event.set()

# ------------------------------------------------------------------ #
#  Session store — bounded LRU with per-session locking              #
# ------------------------------------------------------------------ #

_active_sessions: Dict[str, SessionMemory] = OrderedDict()
_session_locks: Dict[str, asyncio.Lock] = {}
_store_lock = asyncio.Lock()   # protects mutations of _active_sessions / _session_locks
MAX_SESSIONS = 1000


async def _get_session(session_id: str) -> tuple[SessionMemory, asyncio.Lock]:
    """
    FIX 2: Return lock by VALUE not reference.
    Atomically return (or create) the SessionMemory and its asyncio.Lock.
    Creates NEW lock object on each call to prevent race condition where
    lock is deleted while another coroutine holds a reference to it.
    """
    async with _store_lock:
        if session_id not in _active_sessions:
            if len(_active_sessions) >= MAX_SESSIONS:
                evicted_id, _ = _active_sessions.popitem(last=False)
                _session_locks.pop(evicted_id, None)
            _active_sessions[session_id] = SessionMemory()
            _session_locks[session_id] = asyncio.Lock()
        else:
            _active_sessions.move_to_end(session_id)
        
        # FIX 2: Return copies to prevent TOCTOU race
        # If we return the reference and another coroutine evicts this session,
        # the lock could be deleted while caller is using it
        session_memory = _active_sessions[session_id]
        session_lock = _session_locks[session_id]
        
        return session_memory, session_lock


def _restore_session_from_db(session_id: str, session_memory: SessionMemory, db: Optional[Session]) -> None:
    """
    Fix 4: If the session is empty (new in-memory) and DB is available,
    restore conversation history from the last persisted state.
    Called once per session on first access after a server restart.
    """
    if db is None:
        return
    # Only restore if the session has no messages yet (i.e., just created)
    if session_memory._messages:
        return
    try:
        repo = ConversationRepository(db)
        conversation = repo.get_by_session_key(session_id)
        if conversation and conversation.history:
            session_memory.restore_from(conversation.history)
            logger.info(f"[Session] Restored {len(conversation.history)} messages for session {session_id}")
    except Exception as e:
        logger.warning(f"[Session] Could not restore session {session_id} from DB: {e}")


def _persist_session_to_db(session_id: str, session_memory: SessionMemory, db: Optional[Session]) -> None:
    """
    Fix 4: Persist the current session history to DB after each turn.
    Silently skips if DB is unavailable.
    """
    if db is None:
        return
    try:
        repo = ConversationRepository(db)
        history = session_memory.serialize()
        if history:
            repo.upsert_by_session_key(session_id, history)
    except Exception as e:
        logger.warning(f"[Session] Could not persist session {session_id} to DB: {e}")


# ------------------------------------------------------------------ #
#  DB dependency (optional — falls back to None if DB not available) #
# ------------------------------------------------------------------ #

def get_db_optional():
    try:
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[Database] Not available: {str(e)}")
        yield None


# ------------------------------------------------------------------ #
#  1.  Text Chat                                                       #
# ------------------------------------------------------------------ #

@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db_optional)):
    """Standard HTTP text chat."""
    agent = None
    try:
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(request.message) > 5000:
            raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")

        session_memory, session_lock = await _get_session(request.session_id)
        _restore_session_from_db(request.session_id, session_memory, db)
        agent = SupportAgent(db)

        # Per-session lock — only serializes concurrent requests for the SAME session
        async with session_lock:
            response_text, _ = await agent.chat_text(
                user_message=request.message,
                session_memory=session_memory,
                customer_id=request.shopify_customer_id,
            )

        _persist_session_to_db(request.session_id, session_memory, db)
        return ChatResponse(response=response_text, session_id=request.session_id)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[Chat] Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Chat] Unexpected error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="I'm having trouble processing your request right now. Please try again in a moment.",
        )
    finally:
        # FIX 4: Always cleanup agent resources
        if agent:
            await agent.aclose()


# ------------------------------------------------------------------ #
#  2.  Shopify Webhook                                                 #
# ------------------------------------------------------------------ #

@router.post("/api/webhooks/shopify")
async def handle_shopify_webhook(raw_request: Request, db: Session = Depends(get_db_optional)):
    """
    Receives forwarded webhooks from the Remix app.
    Raw body is read before any JSON parsing so HMAC verification works correctly.
    """
    try:
        raw_body = await raw_request.body()
        hmac_header = raw_request.headers.get("X-Shopify-Hmac-Sha256")

        if not hmac_header:
            raise HTTPException(status_code=401, detail="Missing HMAC header")

        calculated_hmac = base64.b64encode(
            hmac.new(
                settings.SHOPIFY_API_SECRET.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        if not hmac.compare_digest(calculated_hmac, hmac_header):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        topic = raw_request.headers.get("X-Shopify-Topic", "")

        if topic == "orders/create" or payload.get("topic") == "ORDERS_CREATE":
            logger.info(f"[Webhook] Order event received — ID: {payload.get('id')}")

        return {"status": "received", "topic": topic}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Webhook] Processing error: {str(e)}")
        # Raise 500 so Shopify retries the delivery (200 = silent data loss)
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# ------------------------------------------------------------------ #
#  3.  Voice WebSocket  (push-to-talk, renamed to /simple/)           #
# ------------------------------------------------------------------ #

@router.websocket("/ws/voice/simple/{session_id}")
async def voice_websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db_optional),
):
    """
    Push-to-talk voice endpoint with production-grade cleanup (FIX 4, FIX 6).

    Protocol:
      - Client streams raw audio blobs while recording (any number of chunks).
      - Client sends text "END_OF_SPEECH" when recording stops.
      - Server transcribes the complete buffer, runs LLM, streams TTS audio back.
      - Server sends JSON {"event": "TURN_COMPLETE"} after each turn.
    """
    await websocket.accept()
    logger.info(f"[WS] Voice connection: {session_id}")

    session_memory, _ = await _get_session(session_id)
    _restore_session_from_db(session_id, session_memory, db)
    agent = SupportAgent(db)

    disconnected = False

    try:
        while True:
            # ---- Phase 1: Collect audio until END_OF_SPEECH ---- #
            audio_chunks: list[bytes] = []
            cancel_event = asyncio.Event()

            # Timing instrumentation (per turn)
            end_of_speech_ts = None
            stt_complete_ts = None
            llm_first_token_ts = None
            audio_sent_first_ts = None

            def log_timing_summary() -> None:
                if end_of_speech_ts is None:
                    return
                stt_dur = (stt_complete_ts - end_of_speech_ts) if stt_complete_ts is not None else None
                llm_dur = (llm_first_token_ts - end_of_speech_ts) if llm_first_token_ts is not None else None
                audio_dur = (audio_sent_first_ts - end_of_speech_ts) if audio_sent_first_ts is not None else None
                logger.info(
                    "--- TIMING SUMMARY ---\n"
                    f"STT duration: {stt_dur if stt_dur is not None else 'N/A'} ms\n"
                    f"Time to first LLM token: {llm_dur if llm_dur is not None else 'N/A'} ms\n"
                    f"Time to first audio: {audio_dur if audio_dur is not None else 'N/A'} ms\n"
                    f"TOTAL TTFR: {audio_dur if audio_dur is not None else 'N/A'} ms\n"
                    "----------------"
                )

            # Collect audio blobs until END_OF_SPEECH or disconnect
            try:
                while True:
                    message = await websocket.receive()

                    if message.get("type") == "websocket.disconnect":
                        disconnected = True
                        logger.info(f"[WS] Client disconnected during recording: {session_id}")
                        return

                    if "bytes" in message and message["bytes"]:
                        chunk = message["bytes"]
                        if len(chunk) >= 100:
                            audio_chunks.append(chunk)

                    elif "text" in message:
                        text_msg = message["text"].strip()
                        if text_msg == "END_OF_SPEECH":
                            end_of_speech_ts = time.time() * 1000.0
                            logger.info(f"[WS] END_OF_SPEECH — {len(audio_chunks)} chunks, {sum(len(c) for c in audio_chunks):,} bytes")
                            logger.info(f"[TIMING] END_OF_SPEECH: {end_of_speech_ts:.3f}")
                            break
                        elif text_msg == "CANCEL_TURN":
                            cancel_event.set()
                            logger.info(f"[WS] CANCEL_TURN during recording: {session_id}")
                            break
            except (WebSocketDisconnect, RuntimeError):
                disconnected = True
                logger.info(f"[WS] Client disconnected during recording: {session_id}")
                return

            if cancel_event.is_set():
                await websocket.send_text(json.dumps({"event": "TURN_CANCELLED"}))
                continue

            # ---- Phase 2: Transcribe collected buffer ---- #
            cancel_task = asyncio.create_task(_cancel_listener(websocket, cancel_event))
            try:
                audio_buffer = b"".join(audio_chunks)
                stt_task = asyncio.create_task(
                    agent.voice_service.transcribe_audio(audio_buffer)
                )

                cancel_wait_task = asyncio.create_task(cancel_event.wait())
                try:
                    await asyncio.wait({stt_task, cancel_wait_task}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    cancel_wait_task.cancel()

                if cancel_event.is_set():
                    stt_task.cancel()
                    await asyncio.gather(stt_task, return_exceptions=True)
                    cancel_task.cancel()
                    log_timing_summary()
                    await websocket.send_text(json.dumps({"event": "TURN_CANCELLED"}))
                    continue

                transcribed_text = await stt_task
                stt_complete_ts = time.time() * 1000.0
                logger.info(f"[TIMING] STT_COMPLETE: {stt_complete_ts:.3f}")

            except (WebSocketDisconnect, RuntimeError):
                disconnected = True
                cancel_task.cancel()
                return
            except Exception as stt_error:
                logger.error(f"[WS] STT error: {stt_error}")
                cancel_task.cancel()
                log_timing_summary()
                try:
                    await websocket.send_text(json.dumps({
                        "error": "Speech recognition failed",
                        "message": "I couldn't understand that. Please try again.",
                    }))
                except Exception:
                    return
                continue

            if not transcribed_text:
                cancel_task.cancel()
                log_timing_summary()
                try:
                    await websocket.send_text(json.dumps({
                        "error": "No speech detected",
                        "message": "I didn't catch that. Please speak clearly and try again.",
                    }))
                except Exception:
                    return
                continue

            logger.info(f"[WS] Transcribed: {transcribed_text[:100]}")
            # Send transcript to client for display
            try:
                await websocket.send_text(json.dumps({
                    "event": "TRANSCRIPT",
                    "text": transcribed_text,
                }))
            except Exception:
                cancel_task.cancel()
                return

            # ---- Phase 4: LLM + sentence-chunked TTS stream ---- #
            try:
                loop = asyncio.get_event_loop()
                pending_text = ""
                last_flush = loop.time()

                async def flush_pending(force: bool = False) -> None:
                    nonlocal pending_text, last_flush
                    if cancel_event.is_set():
                        return
                    if not pending_text:
                        return
                    # Keep chunking coarse to avoid flooding the websocket.
                    if not force and len(pending_text) < 80 and (loop.time() - last_flush) < 0.05:
                        return
                    await websocket.send_text(json.dumps({
                        "event": "AGENT_STREAM",
                        "text": pending_text,
                    }))
                    pending_text = ""
                    last_flush = loop.time()

                async def on_text_chunk(chunk: str) -> None:
                    nonlocal pending_text, last_flush
                    nonlocal llm_first_token_ts
                    if llm_first_token_ts is None:
                        llm_first_token_ts = time.time() * 1000.0
                    pending_text += chunk
                    await flush_pending(force=False)

                async def stream_voice() -> bool:
                    audio_sent = False
                    nonlocal audio_sent_first_ts
                    try:
                        async for audio_chunk in agent.chat_voice_stream(
                            user_message=transcribed_text,
                            session_memory=session_memory,
                            on_text_chunk=on_text_chunk,
                        ):
                            if audio_chunk:
                                if audio_sent_first_ts is None:
                                    audio_sent_first_ts = time.time() * 1000.0
                                    logger.info(f"[TIMING] AUDIO_SENT_FIRST: {audio_sent_first_ts:.3f}")
                                await websocket.send_bytes(audio_chunk)
                                audio_sent = True
                    finally:
                        # Flush any remaining text only if not cancelled.
                        await flush_pending(force=True)
                    return audio_sent

                voice_task = asyncio.create_task(stream_voice())
                try:
                    cancel_wait_task = asyncio.create_task(cancel_event.wait())
                    try:
                        done, _ = await asyncio.wait(
                            {voice_task, cancel_wait_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    finally:
                        cancel_wait_task.cancel()

                    if cancel_event.is_set():
                        voice_task.cancel()
                        await asyncio.gather(voice_task, return_exceptions=True)
                        log_timing_summary()
                        await websocket.send_text(json.dumps({"event": "TURN_CANCELLED"}))
                        continue

                    audio_sent = await voice_task
                finally:
                    if not cancel_task.done():
                        cancel_task.cancel()

                if not audio_sent:
                    logger.warning("[WS] TTS produced no audio")
                    await websocket.send_text(json.dumps({
                        "error": "Voice generation failed",
                        "message": "Voice service unavailable. Please try text chat.",
                        "fallback": True,
                    }))

                await websocket.send_text(json.dumps({"event": "TURN_COMPLETE"}))
                _persist_session_to_db(session_id, session_memory, db)
                log_timing_summary()

            except WebSocketDisconnect:
                logger.info(f"[WS] Client disconnected during response: {session_id}")
                return
            except Exception as agent_error:
                logger.error(f"[WS] Agent error: {agent_error}\n{traceback.format_exc()}")
                await websocket.send_text(json.dumps({
                    "error": "Processing failed",
                    "message": "I encountered an error. Please try again.",
                }))
                log_timing_summary()

    except (WebSocketDisconnect, RuntimeError):
        if not disconnected:
            logger.info(f"[WS] Client disconnected: {session_id}")
    except Exception as outer_error:
        logger.error(f"[WS] Outer error: {outer_error}\n{traceback.format_exc()}")
        try:
            await websocket.send_text(json.dumps({
                "error": "Connection error",
                "message": "Please reconnect.",
            }))
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # FIX 4 & FIX 6: Always cleanup agent resources and cancel TTS tasks
        await agent.aclose()
        logger.debug(f"[WS] Cleaned up agent for session: {session_id}")


# ------------------------------------------------------------------ #
#  4.  Full-Duplex Voice WebSocket  (registered FIRST — no shadowing) #
# ------------------------------------------------------------------ #

@router.websocket("/ws/voice/duplex/{session_id}")
async def voice_duplex_endpoint(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db_optional),
):
    """
    Full-duplex voice endpoint with VAD-driven turn detection.

    Protocol (incoming):
      - Binary frames: raw PCM Int16 LE chunks (48kHz mono, ~20ms from AudioWorklet)
      - Text "INTERRUPT": client-side interrupt signal

    Protocol (outgoing):
      - Binary frames: raw PCM Int16 LE (22050Hz mono) — NO base64, NO MP3
      - {"type": "transcript", "text": "...", "final": true}
      - {"type": "event", "name": "speech_start|speech_end|ai_start|ai_chunk|ai_end|interrupted|no_speech"}

    VAD detects speech_end automatically after ~650ms of silence.
    Interruption is NON-BLOCKING — cancel_pipeline fires as a background task
    so the receive loop never pauses.
    """
    await websocket.accept()
    logger.info(f"[Duplex] Connection: {session_id}")

    session = DuplexSession(session_id)
    agent   = SupportAgent(db)

    _restore_session_from_db(session_id, session.memory, db)

    async def send_event(data: dict) -> None:
        try:
            await websocket.send_text(json.dumps(data))
        except Exception:
            pass

    async def on_speech_start() -> None:
        logger.info(f"[Duplex:{session_id}] ✅ speech_start_detected")
        session.mark_user_speaking()
        await send_event({"type": "event", "name": "speech_start"})

        # NON-BLOCKING interrupt — fire-and-forget so receive loop never stalls
        if session.ai_is_speaking:
            logger.info(f"[Duplex:{session_id}] ⚠️ interrupt_triggered — user spoke over AI")
            await send_event({"type": "event", "name": "interrupted"})
            asyncio.create_task(session.cancel_pipeline())   # ← non-blocking

    async def on_speech_end(audio_buffer: bytes) -> None:
        logger.info(f"[Duplex:{session_id}] ✅ speech_end_detected — {len(audio_buffer):,}b")
        await send_event({"type": "event", "name": "speech_end"})

        # If AI is still speaking (interrupt may still be in-flight), cancel first
        if session.ai_is_speaking:
            logger.info(f"[Duplex:{session_id}] Cancelling existing pipeline before starting new one")
            await session.cancel_pipeline()

        logger.info(f"[Duplex:{session_id}] 🚀 PIPELINE STARTING (as background task)")
        
        task = asyncio.create_task(
            run_pipeline(
                audio_buffer=audio_buffer,
                session=session,
                agent=agent,
                websocket=websocket,
                send_event=send_event,
            )
        )
        session.set_pipeline_task(task)
        logger.info(f"[Duplex:{session_id}] ✅ Pipeline task created and registered")

        async def _persist_on_done(t: asyncio.Task) -> None:
            try:
                logger.info(f"[Duplex:{session_id}] ⏳ Waiting for pipeline task to complete...")
                await t
                logger.info(f"[Duplex:{session_id}] ✅ Pipeline completed successfully")
            except asyncio.CancelledError:
                logger.warning(f"[Duplex:{session_id}] ⚠️ Pipeline was cancelled")
            except Exception as e:
                logger.error(f"[Duplex:{session_id}] ❌ Pipeline error: {e}", exc_info=True)
            finally:
                _persist_session_to_db(session_id, session.memory, db)

        asyncio.create_task(_persist_on_done(task))

    vad = VAD(on_speech_start=on_speech_start, on_speech_end=on_speech_end)

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                chunk = message["bytes"]
                logger.debug(f"[Duplex:{session_id}] audio_in_chunk {len(chunk)}b")
                await vad.feed(chunk)

            elif "text" in message:
                text = message["text"].strip()
                if text == "INTERRUPT":
                    logger.info(f"[Duplex:{session_id}] client INTERRUPT signal")
                    # NON-BLOCKING — receive loop continues immediately
                    asyncio.create_task(session.cancel_pipeline())
                    await send_event({"type": "event", "name": "interrupted"})

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        logger.error(f"[Duplex:{session_id}] outer error: {e}", exc_info=True)
    finally:
        await vad.flush()
        await session.cancel_pipeline()
        await agent.aclose()
        logger.info(f"[Duplex:{session_id}] connection closed")


# ------------------------------------------------------------------ #
#  5.  Legacy alias — keep /ws/voice/{session_id} pointing to simple  #
# ------------------------------------------------------------------ #

@router.websocket("/ws/voice/{session_id}")
async def voice_websocket_legacy(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db_optional),
):
    """Alias for backwards compatibility with the PTT test client."""
    await voice_websocket_endpoint(websocket, session_id, db)
