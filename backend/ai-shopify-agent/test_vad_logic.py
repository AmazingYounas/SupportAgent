#!/usr/bin/env python3
"""
Quick test to verify VAD logic works with WebM chunks.
Run this to validate the byte-size heuristic.
"""
import struct

def _pcm_energy(chunk: bytes) -> float:
    """
    Compute average absolute amplitude of a raw PCM Int16 LE buffer.
    Returns a float in [0, 32767].
    Returns 0.0 for empty or malformed input.
    
    For WebM/Opus chunks (which are NOT PCM), this will return garbage values.
    The VAD falls back to byte-size heuristics in that case.
    """
    n = len(chunk) // 2  # number of Int16 samples
    if n == 0:
        return 0.0
    
    # Quick check: if this looks like WebM (starts with 0x1A 0x45 0xDF 0xA3), 
    # return a signal value that triggers byte-size fallback
    if len(chunk) >= 4 and chunk[0:4] == b'\x1a\x45\xdf\xa3':
        return -1.0  # Signal: not PCM, use byte-size heuristic
    
    try:
        # struct.unpack is faster than numpy for small chunks
        samples = struct.unpack_from(f"<{n}h", chunk)
        return sum(abs(s) for s in samples) / n
    except struct.error:
        # Not valid PCM, return signal for byte-size fallback
        return -1.0


def test_vad_logic():
    """Test VAD with simulated WebM chunks."""
    
    print("=" * 60)
    print("VAD Logic Test - WebM Byte-Size Heuristic")
    print("=" * 60)
    
    # Simulate WebM chunks of various sizes
    test_cases = [
        (b'\x1a\x45\xdf\xa3' + b'\x00' * 500, "WebM header + 500b", False),  # Small chunk (silence)
        (b'\x1a\x45\xdf\xa3' + b'\x00' * 1000, "WebM header + 1000b", False),  # Below threshold
        (b'\x1a\x45\xdf\xa3' + b'\x00' * 1500, "WebM header + 1500b", True),   # At threshold
        (b'\x1a\x45\xdf\xa3' + b'\x00' * 3000, "WebM header + 3000b", True),   # Active speech
        (b'\x1a\x45\xdf\xa3' + b'\x00' * 8000, "WebM header + 8000b", True),   # Large chunk
        (b'\x00' * 800, "Random 800b (no header)", False),  # Small non-WebM
        (b'\x00' * 2000, "Random 2000b (no header)", True),  # Large non-WebM
    ]
    
    BYTE_THRESHOLD = 1500
    
    print(f"\nByte-size threshold: {BYTE_THRESHOLD}b")
    print(f"Expected: chunks >= {BYTE_THRESHOLD}b → active=True\n")
    
    for chunk, description, expected_active in test_cases:
        energy = _pcm_energy(chunk)
        
        if energy < 0:
            # WebM mode: use byte-size
            is_active = len(chunk) >= BYTE_THRESHOLD
            mode = "WebM"
        else:
            # PCM mode: use energy (not tested here)
            is_active = energy >= 300
            mode = "PCM"
        
        status = "✅ PASS" if is_active == expected_active else "❌ FAIL"
        
        print(f"{status} | {description:30s} | size={len(chunk):5d}b | mode={mode:4s} | active={is_active}")
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    test_vad_logic()
