import asyncio
import json
import threading

from fastapi.testclient import TestClient

from app.main import app


class FakeSupportAgent:
    def __init__(self, db=None):
        self.db = db

    async def aclose(self):
        return None


def _parse_text_frame(frame):
    if frame.get("text"):
        return json.loads(frame["text"])
    return None


def _receive_with_timeout(ws, timeout=2.0):
    result = {}

    def _recv():
        result["frame"] = ws.receive()

    thread = threading.Thread(target=_recv, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise TimeoutError("Timed out waiting for websocket frame")
    return result["frame"]


def test_duplex_ws_turn_flow(monkeypatch):
    import app.api.voice_duplex as duplex_mod

    monkeypatch.setattr("app.voice.vad.settings.VAD_MIN_SPEECH_DURATION", 0.0)
    monkeypatch.setattr("app.voice.vad.settings.VAD_MIN_SPEECH_BYTES", 1)
    monkeypatch.setattr("app.voice.vad.settings.VAD_WEBM_THRESHOLD", 100)

    async def fake_run_pipeline(audio_buffer, session, agent, websocket, send_event):
        assert audio_buffer
        await send_event({"type": "transcript", "text": "hello", "final": True})
        session.mark_ai_speaking()
        await send_event({"type": "event", "name": "ai_start"})
        await websocket.send_bytes(b"\x00\x01\x02\x03")
        await send_event({"type": "event", "name": "ai_chunk"})
        await send_event({"type": "event", "name": "ai_end"})
        session.mark_idle()

    monkeypatch.setattr(duplex_mod, "SupportAgent", FakeSupportAgent)
    monkeypatch.setattr(duplex_mod, "run_pipeline", fake_run_pipeline)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/duplex/test-duplex-flow") as ws:
            ws.send_bytes(b"\x11" * 1000)
            ws.send_text("END_OF_SPEECH")

            seen = []
            saw_binary = False
            for _ in range(8):
                try:
                    frame = _receive_with_timeout(ws)
                except TimeoutError:
                    break
                payload = _parse_text_frame(frame)
                if payload:
                    seen.append(payload)
                if frame.get("bytes"):
                    saw_binary = True
                if any(p.get("name") == "ai_end" for p in seen if p.get("type") == "event"):
                    break

            event_names = [p["name"] for p in seen if p.get("type") == "event" and "name" in p]
            assert "speech_start" in event_names
            assert "speech_end" in event_names
            assert "ai_start" in event_names
            assert "ai_chunk" in event_names
            assert "ai_end" in event_names
            assert any(p.get("type") == "transcript" for p in seen)
            assert saw_binary is True


def test_duplex_ws_interrupt(monkeypatch):
    import app.api.voice_duplex as duplex_mod

    monkeypatch.setattr("app.voice.vad.settings.VAD_MIN_SPEECH_DURATION", 0.0)
    monkeypatch.setattr("app.voice.vad.settings.VAD_MIN_SPEECH_BYTES", 1)
    monkeypatch.setattr("app.voice.vad.settings.VAD_WEBM_THRESHOLD", 100)

    async def fake_run_pipeline(audio_buffer, session, agent, websocket, send_event):
        session.mark_ai_speaking()
        await send_event({"type": "event", "name": "ai_start"})
        for _ in range(30):
            if session.interrupt.is_set():
                await send_event({"type": "event", "name": "interrupted"})
                session.mark_idle()
                return
            await asyncio.sleep(0.01)
        await send_event({"type": "event", "name": "ai_end"})
        session.mark_idle()

    monkeypatch.setattr(duplex_mod, "SupportAgent", FakeSupportAgent)
    monkeypatch.setattr(duplex_mod, "run_pipeline", fake_run_pipeline)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/duplex/test-duplex-interrupt") as ws:
            ws.send_bytes(b"\x22" * 1000)
            ws.send_text("END_OF_SPEECH")
            ws.send_text("INTERRUPT")

            events = []
            for _ in range(10):
                frame = _receive_with_timeout(ws)
                payload = _parse_text_frame(frame)
                if payload and payload.get("type") == "event":
                    events.append(payload.get("name"))
                    if "interrupted" in events:
                        break

            assert "interrupted" in events
