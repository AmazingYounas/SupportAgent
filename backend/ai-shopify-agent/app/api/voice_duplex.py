"""
Realtime voice WebSocket: VAD → STT → LLM → TTS (PCM), with interrupt support.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import asyncio
import json
import logging

from app.api.deps import get_db_optional
from app.agent.agent import SupportAgent
from app.voice.session import DuplexSession
from app.voice.vad import VAD
from app.voice.pipeline import run_pipeline
from app.database.repositories import ConversationRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/voice/duplex/{session_id}")
async def voice_duplex_endpoint(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db_optional),
):
    """
    Full-duplex voice endpoint with VAD-driven turn detection.
    
    Protocol (incoming):
      - Binary frames: audio chunks (WebM/Opus 48kHz or PCM)
      - Text "INTERRUPT": client-side interrupt signal
    
    Protocol (outgoing):
      - Binary frames: raw PCM Int16 LE (22050Hz mono)
      - {"type": "transcript", "text": "...", "final": true}
      - {"type": "event", "name": "speech_start|speech_end|ai_start|ai_chunk|ai_end|interrupted|no_speech|error"}
    """
    await websocket.accept()
    logger.info(f"[Duplex] ✅ Connection established: {session_id}")
    
    session = DuplexSession(session_id)
    agent = SupportAgent(db)
    
    # Restore session from DB if available
    if db:
        try:
            repo = ConversationRepository(db)
            conversation = repo.get_by_session_key(session_id)
            if conversation and conversation.history:
                session.memory.restore_from(conversation.history)
                logger.info(f"[Duplex] 📚 Restored {len(conversation.history)} messages")
        except Exception as e:
            logger.warning(f"[Duplex] Could not restore session: {e}")
    
    async def send_event(data: dict) -> None:
        """Send JSON event to client (non-blocking)."""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.debug(f"[Duplex] Failed to send event: {e}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VAD Callbacks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def on_speech_start() -> None:
        """Triggered when VAD detects speech beginning."""
        nonlocal stt_task, stt_audio_queue, final_stt_transcript, last_partial_transcript
        logger.info(f"[Duplex:{session_id}] 🎤 speech_start")
        was_ai_speaking = session.ai_is_speaking
        session.mark_user_speaking()
        await send_event({"type": "event", "name": "speech_start"})
        
        # If AI is speaking, interrupt it (non-blocking)
        if was_ai_speaking:
            logger.info(f"[Duplex:{session_id}] ⚠️ User interrupted AI")
            await send_event({"type": "event", "name": "interrupted"})
            asyncio.create_task(session.cancel_pipeline())

        # Create a FRESH queue for this utterance (prevents stale None sentinels)
        stt_audio_queue = asyncio.Queue(maxsize=1000)
        final_stt_transcript = ""
        last_partial_transcript = ""

        # Start live STT stream
        if not stt_task or stt_task.done():
            stt_task = asyncio.create_task(run_stt_stream())

        # Push cached speech buffer so STT gets audio from the very start of the utterance
        try:
            for cached_chunk in vad._speech_buffer:
                await stt_audio_queue.put(cached_chunk)
            logger.info(f"[Duplex:{session_id}] 🎤 Pushed {len(vad._speech_buffer)} cached chunks to STT")
        except Exception as e:
            logger.warning(f"[Duplex:{session_id}] Failed to push cached audio: {e}")
    
    async def _run_pipeline_wrapper(transcript: str) -> None:
        try:
            await run_pipeline(
                transcript=transcript,
                session=session,
                agent=agent,
                websocket=websocket,
                send_event=send_event,
            )
            logger.info(f"[Duplex:{session_id}] ✅ Pipeline completed")
        except asyncio.CancelledError:
            logger.warning(f"[Duplex:{session_id}] ⚠️ Pipeline cancelled")
        except Exception as e:
            logger.error(f"[Duplex:{session_id}] ❌ Pipeline error: {e}", exc_info=True)
            await send_event({
                "type": "event",
                "name": "error",
                "message": "I encountered an error. Please try again."
            })
        finally:
            # Persist session to DB
            if db:
                try:
                    repo = ConversationRepository(db)
                    history = session.memory.serialize()
                    if history:
                        repo.upsert_by_session_key(session_id, history)
                except Exception as e:
                    logger.warning(f"[Duplex] Could not persist session: {e}")

    async def on_speech_end(audio_buffer: bytes) -> None:
        """
        Triggered when VAD detects speech ending.
        STT stream is killed, resulting transcript is instantly pipelined.
        """
        logger.info(f"[Duplex:{session_id}] 🔇 speech_end — {len(audio_buffer):,}b")
        await send_event({"type": "event", "name": "speech_end"})
        
        # Shutdown live STT by sending None sentinel
        try:
            await stt_audio_queue.put(None)
        except Exception:
            pass
        
        if stt_task and not stt_task.done():
            # Wait for STT to finish processing.
            try:
                await asyncio.wait_for(stt_task, timeout=8.0)
            except asyncio.TimeoutError:
                logger.warning(f"[Duplex:{session_id}] ⚠️ STT task timed out after 8s, cancelling")
                stt_task.cancel()
            except Exception as e:
                logger.error(f"[Duplex:{session_id}] STT task error: {e}")
        
        # Guard: Cancel any existing pipeline task
        if session.pipeline_task and not session.pipeline_task.done():
            logger.info(f"[Duplex:{session_id}] Cancelling existing STT/LLM pipeline before starting new turn")
            session.pipeline_task.cancel()
        
        if session.ai_is_speaking:
            await session.cancel_pipeline()
            
        # VERY IMPORTANT: Clear any hanging interrupts just before launching
        session.interrupt.clear()

        # Fallback logic: Use final if available, else last_partial immediately
        transcript = final_stt_transcript.strip()
        if not transcript and last_partial_transcript.strip():
            transcript = last_partial_transcript.strip()
            logger.warning(f"[Duplex:{session_id}] STT commit dropped — falling back to partial: '{transcript[:60]}'")
            await send_event({"type": "transcript", "text": transcript, "is_final": True})
            
        logger.info(f"[Duplex:{session_id}] 🚀 Starting pipeline with transcript: '{transcript[:60]}'")
        
        if not transcript:
            logger.warning(f"[Duplex:{session_id}] ⚠️ No transcript from live STT — skipping pipeline")
            await send_event({"type": "event", "name": "no_speech"})
            session.mark_idle()
            return
        
        pipeline_task = asyncio.create_task(_run_pipeline_wrapper(transcript))
        session.set_pipeline_task(pipeline_task)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Main Loop (FIXED: True Live Streaming overlap)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    vad = VAD(on_speech_start=on_speech_start, on_speech_end=on_speech_end)
    receive_queue = asyncio.Queue(maxsize=100)
    
    # queues for STT 
    stt_audio_queue = asyncio.Queue(maxsize=1000)
    stt_task = None
    final_stt_transcript = ""
    last_partial_transcript = ""

    async def stt_audio_generator():
        """Yields active audio chunks to NineLabs Realtime socket."""
        while True:
            chunk = await stt_audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def run_stt_stream():
        """Runs the continuous ElevenLabs STT stream to catch partials."""
        nonlocal final_stt_transcript, last_partial_transcript
        stt_provider = agent.voice_service.stt
        
        try:
            async for transcript_data in stt_provider.transcribe_stream(stt_audio_generator()):
                if transcript_data:
                    text = transcript_data.get("text", "").strip()
                    is_final = transcript_data.get("is_final", False)
                    
                    if text:
                        if is_final:
                            final_stt_transcript = text
                        else:
                            last_partial_transcript = text
                            
                        # Push partial/final directly to frontend (only while user is speaking for UI)
                        if session.user_is_speaking or is_final:
                            await send_event({
                                "type": "transcript", 
                                "text": text, 
                                "is_final": is_final
                            })
                        if is_final:
                            logger.debug(f"[Duplex:{session_id}] STT final: {text[:60]}")
                        else:
                            logger.debug(f"[Duplex:{session_id}] STT partial: {text[:60]}")
        except Exception as e:
            logger.error(f"[Duplex:{session_id}] Live STT Stream error: {e}", exc_info=True)
            
    audio_chunk_count = 0
    audio_byte_count = 0

    async def receive_loop():
        """Receive audio chunks from WebSocket."""
        nonlocal audio_chunk_count, audio_byte_count
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                
                # Binary audio data
                if "bytes" in message and message["bytes"]:
                    audio_chunk_count += 1
                    audio_byte_count += len(message["bytes"])
                    if audio_chunk_count <= 5 or audio_chunk_count % 10 == 0:
                        logger.info(
                            f"[Duplex:{session_id}] 📦 Audio chunk #{audio_chunk_count}: "
                            f"{len(message['bytes'])}b (total: {audio_byte_count:,}b)"
                        )
                    try:
                        await receive_queue.put(("audio", message["bytes"]))
                    except asyncio.QueueFull:
                        logger.warning(f"[Duplex:{session_id}] ⚠️ receive_queue FULL — dropping chunk")
                
                # Text commands
                elif "text" in message:
                    text = message["text"].strip()
                    if text == "INTERRUPT":
                        logger.info(f"[Duplex:{session_id}] 📨 INTERRUPT received")
                        await receive_queue.put(("interrupt", None))
                    elif text == "END_OF_SPEECH":
                        logger.info(f"[Duplex:{session_id}] 📨 END_OF_SPEECH received")
                        await receive_queue.put(("end_of_speech", None))
                    elif text == "PING":
                        try:
                            await websocket.send_text("PONG")
                        except Exception:
                            pass
                    else:
                        logger.info(f"[Duplex:{session_id}] 📨 Text: {text[:60]}")
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as e:
            logger.error(f"[Duplex:{session_id}] Receive loop error: {e}")
        finally:
            logger.info(
                f"[Duplex:{session_id}] 📊 Receive loop ended — "
                f"{audio_chunk_count} chunks, {audio_byte_count:,}b total"
            )
            await receive_queue.put(("close", None))
    
    async def vad_loop():
        nonlocal stt_task, final_stt_transcript
        try:
            while True:
                msg_type, data = await receive_queue.get()
                
                if msg_type == "close":
                    break
                    
                elif msg_type == "audio":
                    await vad.feed(data)
                    # If we are officially in speaking mode, pipe audio directly to STT 
                    # Note: STT task is created exclusively in on_speech_start to avoid race conditions.
                    if session.user_is_speaking:
                        try:
                            await stt_audio_queue.put(data)
                        except asyncio.QueueFull:
                            pass
                            
                elif msg_type == "interrupt":
                    logger.info(f"[Duplex:{session_id}] 🛑 Client INTERRUPT signal")
                    asyncio.create_task(session.cancel_pipeline())
                    await send_event({"type": "event", "name": "interrupted"})
                    
                elif msg_type == "end_of_speech":
                    logger.info(f"[Duplex:{session_id}] 🛑 Client END_OF_SPEECH signal")
                    try:
                        await vad.force_end()
                    except Exception as e:
                        logger.error(f"[Duplex:{session_id}] VAD force_end error: {e}", exc_info=True)
                        
        except Exception as e:
            logger.error(f"[Duplex:{session_id}] VAD loop error: {e}", exc_info=True)
    
    # Run both loops concurrently
    try:
        await asyncio.gather(
            receive_loop(),
            vad_loop(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"[Duplex:{session_id}] Main loop error: {e}", exc_info=True)
    finally:
        # Clean shutdown
        await stt_audio_queue.put(None)
        await vad.flush()
        await session.cancel_pipeline()
        await agent.aclose()
        logger.info(f"[Duplex:{session_id}] 🔌 Connection closed")
