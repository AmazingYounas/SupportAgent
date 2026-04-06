"""
Extreme Audio Debugging Utilities
Captures detailed information about audio buffers to diagnose WebM issues
"""
import logging
import hashlib
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Magic bytes for various audio formats
MAGIC_BYTES = {
    b'\x1a\x45\xdf\xa3': 'WebM (EBML)',
    b'RIFF': 'WAV/RIFF',
    b'ID3': 'MP3',
    b'OggS': 'Ogg',
    b'\xff\xfb': 'MP3 (no ID3)',
    b'\xff\xf3': 'MP3 (no ID3)',
    b'\xff\xf2': 'MP3 (no ID3)',
}

def analyze_audio_buffer(audio_buffer: bytes, label: str = "audio") -> dict:
    """
    Perform deep analysis of audio buffer.
    Returns detailed diagnostic information.
    """
    if not audio_buffer:
        return {
            "label": label,
            "error": "Empty buffer",
            "size": 0
        }
    
    size = len(audio_buffer)
    first_16 = audio_buffer[:16]
    first_4 = audio_buffer[:4]
    last_16 = audio_buffer[-16:]
    
    # Detect format
    detected_format = "Unknown"
    for magic, fmt in MAGIC_BYTES.items():
        if audio_buffer.startswith(magic):
            detected_format = fmt
            break
    
    # Check for EBML structure (WebM)
    has_ebml_header = audio_buffer[:4] == b'\x1a\x45\xdf\xa3'
    
    # Look for WebM-specific markers
    has_segment = b'\x18\x53\x80\x67' in audio_buffer[:1000]  # Segment marker
    has_cluster = b'\x1f\x43\xb6\x75' in audio_buffer[:1000]  # Cluster marker
    has_tracks = b'\x16\x54\xae\x6b' in audio_buffer[:1000]   # Tracks marker
    
    # Calculate hash for uniqueness
    buffer_hash = hashlib.md5(audio_buffer).hexdigest()[:8]
    
    # Check for all zeros (silence)
    is_all_zeros = audio_buffer == b'\x00' * size
    
    # Check for repeating patterns (corrupted)
    first_byte = audio_buffer[0]
    is_repeating = all(b == first_byte for b in audio_buffer[:100])
    
    analysis = {
        "label": label,
        "size": size,
        "hash": buffer_hash,
        "detected_format": detected_format,
        "first_4_bytes": first_4.hex(),
        "first_16_bytes": first_16.hex(),
        "last_16_bytes": last_16.hex(),
        "has_ebml_header": has_ebml_header,
        "has_segment_marker": has_segment,
        "has_cluster_marker": has_cluster,
        "has_tracks_marker": has_tracks,
        "is_all_zeros": is_all_zeros,
        "is_repeating": is_repeating,
        "likely_valid_webm": has_ebml_header and has_segment and has_cluster,
    }
    
    return analysis

def log_audio_analysis(audio_buffer: bytes, label: str = "audio", save_sample: bool = False):
    """
    Log detailed audio analysis and optionally save sample to disk.
    """
    analysis = analyze_audio_buffer(audio_buffer, label)
    
    logger.info(f"[AudioDebug:{label}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"[AudioDebug:{label}] Size: {analysis['size']:,} bytes")
    logger.info(f"[AudioDebug:{label}] Hash: {analysis['hash']}")
    logger.info(f"[AudioDebug:{label}] Format: {analysis['detected_format']}")
    logger.info(f"[AudioDebug:{label}] First 4 bytes: {analysis['first_4_bytes']}")
    logger.info(f"[AudioDebug:{label}] First 16 bytes: {analysis['first_16_bytes']}")
    logger.info(f"[AudioDebug:{label}] Last 16 bytes: {analysis['last_16_bytes']}")
    logger.info(f"[AudioDebug:{label}] Has EBML header: {analysis['has_ebml_header']}")
    logger.info(f"[AudioDebug:{label}] Has Segment: {analysis['has_segment_marker']}")
    logger.info(f"[AudioDebug:{label}] Has Cluster: {analysis['has_cluster_marker']}")
    logger.info(f"[AudioDebug:{label}] Has Tracks: {analysis['has_tracks_marker']}")
    logger.info(f"[AudioDebug:{label}] Likely valid WebM: {analysis['likely_valid_webm']}")
    logger.info(f"[AudioDebug:{label}] All zeros: {analysis['is_all_zeros']}")
    logger.info(f"[AudioDebug:{label}] Repeating pattern: {analysis['is_repeating']}")
    logger.info(f"[AudioDebug:{label}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Save sample to disk for manual inspection
    if save_sample and audio_buffer:
        try:
            debug_dir = Path("audio_debug_samples")
            debug_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{label}_{timestamp}_{analysis['hash']}.webm"
            filepath = debug_dir / filename
            
            with open(filepath, 'wb') as f:
                f.write(audio_buffer)
            
            logger.info(f"[AudioDebug:{label}] 💾 Sample saved: {filepath}")
        except Exception as e:
            logger.error(f"[AudioDebug:{label}] Failed to save sample: {e}")
    
    return analysis

def compare_buffers(buffer1: bytes, buffer2: bytes, label1: str = "buffer1", label2: str = "buffer2"):
    """
    Compare two audio buffers to find differences.
    """
    analysis1 = analyze_audio_buffer(buffer1, label1)
    analysis2 = analyze_audio_buffer(buffer2, label2)
    
    logger.info(f"[AudioDebug:Compare] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"[AudioDebug:Compare] {label1} vs {label2}")
    logger.info(f"[AudioDebug:Compare] Size: {analysis1['size']:,} vs {analysis2['size']:,}")
    logger.info(f"[AudioDebug:Compare] Format: {analysis1['detected_format']} vs {analysis2['detected_format']}")
    logger.info(f"[AudioDebug:Compare] Valid WebM: {analysis1['likely_valid_webm']} vs {analysis2['likely_valid_webm']}")
    logger.info(f"[AudioDebug:Compare] Same hash: {analysis1['hash'] == analysis2['hash']}")
    logger.info(f"[AudioDebug:Compare] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    return analysis1, analysis2
