"""
STT (Speech-to-Text) service providers.

Available providers:
- ElevenLabsRealtimeSTT: WebSocket streaming, ~150ms latency (Scribe v2) - CURRENTLY USED
- ElevenLabsSTT: Batch-only, 1.5-2s latency (Scribe v1)
- DeepgramSTT: Streaming, 200-400ms latency
"""
from app.services.stt.base import STTProvider
from app.services.stt.elevenlabs import ElevenLabsSTT
from app.services.stt.elevenlabs_realtime import ElevenLabsRealtimeSTT
from app.services.stt.deepgram import DeepgramSTT

__all__ = ["STTProvider", "ElevenLabsSTT", "ElevenLabsRealtimeSTT", "DeepgramSTT"]
