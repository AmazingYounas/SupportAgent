from app.services.stt.elevenlabs import ElevenLabsSTT
from app.services.voice_service import VoiceService


def test_voice_service_unknown_provider_falls_back_to_elevenlabs():
    service = VoiceService(stt_provider="unknown-provider")
    assert isinstance(service.stt, ElevenLabsSTT)


def test_voice_service_deepgram_without_key_falls_back_to_elevenlabs(monkeypatch):
    monkeypatch.setattr("app.services.voice_service.settings.DEEPGRAM_API_KEY", "")
    service = VoiceService(stt_provider="deepgram")
    assert isinstance(service.stt, ElevenLabsSTT)
