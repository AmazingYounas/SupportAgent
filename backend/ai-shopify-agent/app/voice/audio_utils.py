"""
Audio format utilities and constants.

This module documents and handles audio format conversions throughout the pipeline.

AUDIO FORMAT FLOW:
1. Browser → Backend:  WebM/Opus 48kHz mono (MediaRecorder output)
2. VAD Processing:     Format-agnostic (byte-size heuristic)
3. STT Input:          WebM/Opus (ElevenLabs Scribe accepts this)
4. TTS Output:         PCM Int16 LE 22050Hz mono (raw audio)
5. Backend → Browser:  PCM Int16 LE 22050Hz (binary WebSocket frames)
6. Browser Playback:   AudioContext decodes PCM (wrapped in WAV header)
"""
import struct
import logging
from typing import Tuple

from app.config import settings

logger = logging.getLogger(__name__)

# WebM magic bytes (EBML header)
WEBM_MAGIC = b'\x1a\x45\xdf\xa3'


def detect_audio_format(chunk: bytes) -> str:
    """
    Detect audio format from chunk header.
    
    The frontend sends raw PCM Int16 LE at 16kHz (via ScriptProcessorNode).
    Each chunk is exactly 8192 bytes (4096 samples × 2 bytes/sample).
    Falls back to WebM detection for legacy clients.
    
    Returns:
        "pcm"  - Raw PCM Int16 LE (default for fixed-size chunks from frontend)
        "webm" - WebM/Opus container
    """
    if len(chunk) < 4:
        return "pcm"
    
    # Explicit WebM header (EBML magic bytes)
    if chunk[:4] == WEBM_MAGIC:
        return "webm"
    
    # Fixed-size chunks from ScriptProcessorNode are usually PCM.
    # With downsampling, they might be different sizes (e.g. 2730 bytes).
    # Since we only expect WebM or PCM, and we've ruled out WebM, assume PCM.
    return "pcm"


def compute_pcm_energy(chunk: bytes) -> float:
    """
    Compute average absolute amplitude of raw PCM Int16 LE buffer.
    
    Returns:
        float in [0, 32767] representing average amplitude
        -1.0 if chunk is not valid PCM
    """
    n = len(chunk) // 2
    if n == 0:
        return 0.0
    
    try:
        samples = struct.unpack_from(f"<{n}h", chunk)
        return sum(abs(s) for s in samples) / n
    except struct.error:
        return -1.0


def compute_audio_activity(chunk: bytes, format_hint: str = "auto") -> Tuple[bool, dict]:
    """
    Unified audio activity detection for any format.
    
    FIX: Lowered WebM threshold from 3500 to 1500 bytes to match MediaRecorder chunk sizes.
    
    Args:
        chunk: Audio data bytes
        format_hint: "auto", "webm", "pcm" - auto-detects if "auto"
    
    Returns:
        (is_active, metadata_dict)
        
    Metadata includes:
        - format: detected format
        - energy: PCM energy (if PCM)
        - size: chunk size in bytes
        - method: "energy" or "size"
    """
    if format_hint == "auto":
        format_hint = detect_audio_format(chunk)
    
    metadata = {
        "format": format_hint,
        "size": len(chunk),
    }
    
    if format_hint == "pcm":
        energy = compute_pcm_energy(chunk)
        metadata["energy"] = energy
        metadata["method"] = "energy"
        # PCM threshold is configurable via settings.
        is_active = energy >= settings.VAD_SPEECH_THRESHOLD
    else:
        # WebM: use byte-size heuristic
        # At 250ms chunks: speech ~300-800 bytes, silence ~50-200 bytes
        metadata["method"] = "size"
        threshold = settings.VAD_WEBM_THRESHOLD
        is_active = len(chunk) >= threshold
    
    return is_active, metadata


def create_wav_header(pcm_data_size: int, sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """
    Create WAV header for raw PCM data.
    Used by browser to decode PCM chunks via AudioContext.
    
    Args:
        pcm_data_size: Size of PCM data in bytes
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        bits_per_sample: Bits per sample (8 or 16)
    
    Returns:
        44-byte WAV header
    """
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    
    header = bytearray(44)
    
    # RIFF chunk
    header[0:4] = b'RIFF'
    struct.pack_into('<I', header, 4, 36 + pcm_data_size)
    header[8:12] = b'WAVE'
    
    # fmt chunk
    header[12:16] = b'fmt '
    struct.pack_into('<I', header, 16, 16)  # fmt chunk size
    struct.pack_into('<H', header, 20, 1)   # audio format (PCM)
    struct.pack_into('<H', header, 22, channels)
    struct.pack_into('<I', header, 24, sample_rate)
    struct.pack_into('<I', header, 28, byte_rate)
    struct.pack_into('<H', header, 32, block_align)
    struct.pack_into('<H', header, 34, bits_per_sample)
    
    # data chunk
    header[36:40] = b'data'
    struct.pack_into('<I', header, 40, pcm_data_size)
    
    return bytes(header)
