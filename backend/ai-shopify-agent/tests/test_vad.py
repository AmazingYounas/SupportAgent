import asyncio
import struct

import pytest

from app.config import settings
from app.voice.vad import VAD


@pytest.mark.asyncio
async def test_vad_emits_start_and_end_for_pcm(monkeypatch):
    events: list[tuple[str, int]] = []

    async def on_start():
        events.append(("start", 0))

    async def on_end(audio: bytes):
        events.append(("end", len(audio)))

    monkeypatch.setattr(settings, "VAD_SPEECH_THRESHOLD", 200)
    monkeypatch.setattr(settings, "VAD_MIN_SPEECH_DURATION", 0.0)
    monkeypatch.setattr(settings, "VAD_MIN_SPEECH_BYTES", 2)
    monkeypatch.setattr(settings, "VAD_SILENCE_DURATION", 0.01)

    vad = VAD(on_speech_start=on_start, on_speech_end=on_end)

    loud_pcm = struct.pack("<400h", *([500] * 400))
    silent_pcm = struct.pack("<400h", *([0] * 400))

    await vad.feed(loud_pcm)
    await vad.feed(silent_pcm)
    await asyncio.sleep(0.02)

    assert events[0][0] == "start"
    assert any(name == "end" and size > 0 for name, size in events)


@pytest.mark.asyncio
async def test_vad_force_end_triggers_callback(monkeypatch):
    called = {"end": False}

    async def on_start():
        return None

    async def on_end(_: bytes):
        called["end"] = True

    monkeypatch.setattr(settings, "VAD_SPEECH_THRESHOLD", 100)
    monkeypatch.setattr(settings, "VAD_MIN_SPEECH_DURATION", 0.0)
    monkeypatch.setattr(settings, "VAD_MIN_SPEECH_BYTES", 2)

    vad = VAD(on_speech_start=on_start, on_speech_end=on_end)
    loud_pcm = struct.pack("<200h", *([400] * 200))

    await vad.feed(loud_pcm)
    await vad.force_end()

    assert called["end"] is True
