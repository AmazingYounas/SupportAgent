"""
Full-duplex voice pipeline: STT → LLM → TTS (PCM)

Runs as a single asyncio task per turn.
Checks session.interrupt at every yield point so interruptions are instant.

Flow:
  1. transcribe_audio(buffer)           — ElevenLabs Scribe batch
  2. astream_events(state)              — LangGraph streaming tokens
  3. stream_audio_pcm(tokens)           — sentence-chunked TTS → raw PCM Int16 22050Hz
  4. websocket.send_bytes(pcm_chunk)    — binary frames to client

Event semantics (corrected):
  ai_start  → LLM has begun generating (first token received)
  ai_chunk  → first audio chunk is about to be sent (TTS started)
  ai_end    → all audio sent, turn complete
  interrupted → pipeline cancelled mid-turn
  no_speech   → STT returned empty transcript
"""
import asyncio
import logging
import time
from typing import Callable, Awaitable

from fastapi import WebSocket

from app.agent.agent import SupportAgent
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import ConversationState
from app.voice.session import DuplexSession

logger = logging.getLogger(__name__)


async def run_pipeline(
    audio_buffer: bytes,
    session: DuplexSession,
    agent: SupportAgent,
    websocket: WebSocket,
    send_event: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Execute one full STT → LLM → TTS turn.

    Checks session.interrupt before every blocking step.
    Designed to be run as an asyncio.Task so it can be cancelled externally.
    """
    logger.info(f"[Pipeline:{session.session_id}] 🎬 PIPELINE STARTED")
    t_start = time.time() * 1000

    try:
        # ── 1. STT ────────────────────────────────────────────────────────── #
        if session.interrupt.is_set():
            logger.info(f"[Pipeline:{session.session_id}] ⚠️ Interrupted before STT")
            return

        logger.info(f"[Pipeline:{session.session_id}] 🎤 STT START — {len(audio_buffer):,}b")
        try:
            transcript = await agent.voice_service.transcribe_audio(audio_buffer)
        except asyncio.CancelledError:
            logger.info(f"[Pipeline:{session.session_id}] ⚠️ Cancelled during STT")
            raise
        except Exception as e:
            logger.error(f"[Pipeline:{session.session_id}] ❌ STT ERROR: {e}", exc_info=True)
            await send_event({
                "type": "event",
                "name": "error",
                "message": f"Speech recognition failed: {str(e)}"
            })
            session.mark_idle()
            return

        t_stt = time.time() * 1000
        logger.info(
            f"[Pipeline:{session.session_id}] ✅ STT DONE in {t_stt - t_start:.0f}ms: "
            f"{transcript[:80]}"
        )

        if not transcript:
            logger.warning(f"[Pipeline:{session.session_id}] ⚠️ Empty transcript")
            await send_event({"type": "event", "name": "no_speech"})
            session.mark_idle()
            return

        if session.interrupt.is_set():
            logger.info(f"[Pipeline:{session.session_id}] ⚠️ Interrupted after STT")
            return

        # Send transcript to client immediately
        await send_event({"type": "transcript", "text": transcript, "final": True})
        logger.info(f"[Pipeline:{session.session_id}] 📤 Transcript sent to client")

        # ── 2. LLM + TTS (overlapping) ────────────────────────────────────── #
        memory = session.memory
        if not memory.get_messages():
            memory.set_system_prompt(SYSTEM_PROMPT)
        memory.add_user_message(transcript)

        state = ConversationState(
            messages=memory.get_messages(),
            customer_id=None,
            active_order_id=None,
        )

        full_response    = ""
        first_token_ts:  float | None = None
        first_audio_ts:  float | None = None
        audio_sent       = False
        ai_start_sent    = False

        logger.info(f"[Pipeline:{session.session_id}] 🧠 LLM START")

        async def _token_stream():
            """
            Yield LLM tokens, checking interrupt between each.
            Sends ai_start on the FIRST token (correct semantics).
            """
            nonlocal full_response, first_token_ts, ai_start_sent

            try:
                async for event in agent.app_graph.astream_events(state, version="v2"):
                    if session.interrupt.is_set():
                        logger.info(f"[Pipeline:{session.session_id}] ⚠️ Interrupted during LLM")
                        return
                    if event["event"] == "on_chat_model_stream":
                        chunk = event["data"]["chunk"].content
                        if chunk:
                            if first_token_ts is None:
                                first_token_ts = time.time() * 1000
                                logger.info(
                                    f"[Pipeline:{session.session_id}] ✅ LLM FIRST TOKEN "
                                    f"— {first_token_ts - t_stt:.0f}ms after STT"
                                )
                                # ai_start fires on first LLM token (correct semantics)
                                if not ai_start_sent:
                                    ai_start_sent = True
                                    session.mark_ai_speaking()
                                    await send_event({"type": "event", "name": "ai_start"})

                            full_response += chunk
                            logger.debug(
                                f"[Pipeline:{session.session_id}] llm_token: {repr(chunk)}"
                            )
                            yield chunk
            except Exception as e:
                logger.error(f"[Pipeline:{session.session_id}] ❌ LLM ERROR: {e}", exc_info=True)
                raise

        logger.info(f"[Pipeline:{session.session_id}] 🔊 TTS START")

        try:
            async for audio_chunk in agent.voice_service.stream_audio_pcm(_token_stream()):
                if session.interrupt.is_set():
                    logger.info(
                        f"[Pipeline:{session.session_id}] ⚠️ Interrupted during TTS"
                    )
                    break

                if audio_chunk:
                    if first_audio_ts is None:
                        first_audio_ts = time.time() * 1000
                        ttfr = first_audio_ts - t_start
                        logger.info(
                            f"[Pipeline:{session.session_id}] ✅ TTS FIRST AUDIO CHUNK "
                            f"— TTFR={ttfr:.0f}ms"
                        )
                        # ai_chunk fires when first audio is about to be sent
                        await send_event({"type": "event", "name": "ai_chunk"})

                    logger.debug(
                        f"[Pipeline:{session.session_id}] 📤 SENDING AUDIO CHUNK {len(audio_chunk)}b"
                    )
                    await websocket.send_bytes(audio_chunk)
                    audio_sent = True

        except asyncio.CancelledError:
            logger.info(f"[Pipeline:{session.session_id}] ⚠️ Cancelled during LLM/TTS")
            if full_response:
                memory.add_ai_message(full_response + " [interrupted]")
            await send_event({"type": "event", "name": "interrupted"})
            session.mark_idle()
            raise
        except Exception as e:
            logger.error(f"[Pipeline:{session.session_id}] ❌ TTS ERROR: {e}", exc_info=True)
            await send_event({
                "type": "event",
                "name": "error",
                "message": f"Voice generation failed: {str(e)}"
            })
            session.mark_idle()
            return

        # ── 3. Finalise ───────────────────────────────────────────────────── #
        if full_response:
            memory.add_ai_message(full_response)
            logger.info(f"[Pipeline:{session.session_id}] 💾 Response saved to memory")

        if not audio_sent:
            logger.warning(f"[Pipeline:{session.session_id}] ⚠️ TTS produced NO audio")
            await send_event({"type": "event", "name": "ai_end", "fallback": True})
        else:
            logger.info(f"[Pipeline:{session.session_id}] ✅ Audio sent successfully")
            await send_event({"type": "event", "name": "ai_end"})

        t_end = time.time() * 1000
        logger.info(
            f"[Pipeline:{session.session_id}] 🏁 PIPELINE COMPLETE — "
            f"total={t_end - t_start:.0f}ms "
            f"stt={t_stt - t_start:.0f}ms "
            f"ttfr={((first_audio_ts or t_end) - t_start):.0f}ms"
        )

        session.mark_idle()

    except asyncio.CancelledError:
        logger.info(f"[Pipeline:{session.session_id}] ⚠️ Pipeline cancelled")
        session.mark_idle()
        raise
    except Exception as e:
        logger.error(
            f"[Pipeline:{session.session_id}] ❌ PIPELINE FATAL ERROR: {e}",
            exc_info=True
        )
        await send_event({
            "type": "event",
            "name": "error",
            "message": f"Pipeline error: {str(e)}"
        })
        session.mark_idle()
        raise
