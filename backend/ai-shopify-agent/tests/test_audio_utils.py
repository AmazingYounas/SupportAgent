import struct

from app.config import settings
from app.voice.audio_utils import (
    WEBM_MAGIC,
    compute_audio_activity,
    create_wav_header,
    detect_audio_format,
)


def test_detect_audio_format_webm_magic():
    chunk = WEBM_MAGIC + b"\x00\x00\x00\x00"
    assert detect_audio_format(chunk) == "webm"


def test_compute_audio_activity_pcm_uses_config_threshold(monkeypatch):
    pcm_samples = struct.pack("<20h", *([400] * 20))

    monkeypatch.setattr(settings, "VAD_SPEECH_THRESHOLD", 450)
    active_high, meta_high = compute_audio_activity(pcm_samples, format_hint="pcm")
    assert active_high is False
    assert meta_high["method"] == "energy"

    monkeypatch.setattr(settings, "VAD_SPEECH_THRESHOLD", 300)
    active_low, meta_low = compute_audio_activity(pcm_samples, format_hint="pcm")
    assert active_low is True
    assert meta_low["energy"] >= 300


def test_compute_audio_activity_webm_uses_size_threshold(monkeypatch):
    monkeypatch.setattr(settings, "VAD_WEBM_THRESHOLD", 100)
    active, meta = compute_audio_activity(b"\x00" * 120, format_hint="webm")
    assert active is True
    assert meta["method"] == "size"


def test_create_wav_header_has_riff_wave_markers():
    header = create_wav_header(3200, sample_rate=22050, channels=1, bits_per_sample=16)
    assert len(header) == 44
    assert header[0:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    assert header[36:40] == b"data"
