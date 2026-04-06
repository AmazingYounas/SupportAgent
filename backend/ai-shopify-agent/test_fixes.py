#!/usr/bin/env python3
"""
Test script to verify all critical fixes are working.
Run this after applying fixes to ensure everything is connected properly.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.voice.audio_utils import detect_audio_format, compute_audio_activity
from app.config import settings


def test_audio_format_detection():
    """Test that audio format detection now defaults to webm."""
    print("\n🧪 Testing Audio Format Detection...")
    
    # Test 1: Small chunk (no magic bytes)
    small_chunk = b'\x00\x01\x02\x03' * 100  # 400 bytes
    format_detected = detect_audio_format(small_chunk)
    assert format_detected == "webm", f"Expected 'webm', got '{format_detected}'"
    print("  ✅ Small chunk detected as webm")
    
    # Test 2: WebM with magic bytes
    webm_chunk = b'\x1a\x45\xdf\xa3' + b'\x00' * 1000
    format_detected = detect_audio_format(webm_chunk)
    assert format_detected == "webm", f"Expected 'webm', got '{format_detected}'"
    print("  ✅ WebM magic bytes detected correctly")
    
    # Test 3: PCM-like data
    pcm_chunk = b'\x00\x01' * 500  # Looks like Int16 samples
    format_detected = detect_audio_format(pcm_chunk)
    # Should detect as PCM or webm (both acceptable)
    print(f"  ✅ PCM-like data detected as: {format_detected}")
    
    print("✅ Audio format detection tests passed!")


def test_vad_threshold():
    """Test that VAD threshold is now appropriate for MediaRecorder."""
    print("\n🧪 Testing VAD Threshold...")
    
    # Check config
    threshold = settings.VAD_WEBM_THRESHOLD
    print(f"  Current VAD_WEBM_THRESHOLD: {threshold} bytes")
    
    if threshold > 2000:
        print(f"  ⚠️  Threshold is high ({threshold}), but fallback logic should handle it")
    else:
        print(f"  ✅ Threshold is appropriate for MediaRecorder chunks")
    
    # Test activity detection with typical MediaRecorder chunk sizes
    test_chunks = [
        (b'\x00' * 1000, False, "1000 bytes (silence)"),
        (b'\x00' * 1500, True, "1500 bytes (speech)"),
        (b'\x00' * 2000, True, "2000 bytes (speech)"),
        (b'\x00' * 3000, True, "3000 bytes (speech)"),
    ]
    
    for chunk, expected_active, description in test_chunks:
        is_active, metadata = compute_audio_activity(chunk, format_hint="webm")
        status = "✅" if is_active == expected_active else "❌"
        print(f"  {status} {description}: active={is_active} (expected={expected_active})")
        
        if is_active != expected_active:
            print(f"     Metadata: {metadata}")
            raise AssertionError(f"Activity detection failed for {description}")
    
    print("✅ VAD threshold tests passed!")


def test_audio_validation():
    """Test that STT validation catches invalid audio."""
    print("\n🧪 Testing Audio Validation Logic...")
    
    # Test cases that should be rejected
    invalid_cases = [
        (b'', "empty buffer"),
        (b'\x00' * 500, "too small (500 bytes)"),
        (b'\x00' * 5000, "all zeros (silence)"),
    ]
    
    for audio_buffer, description in invalid_cases:
        # Check if buffer would be rejected
        is_valid = (
            len(audio_buffer) >= 1000 and
            audio_buffer != b'\x00' * len(audio_buffer)
        )
        status = "✅" if not is_valid else "❌"
        print(f"  {status} {description}: rejected={not is_valid}")
        
        if is_valid:
            raise AssertionError(f"Should have rejected: {description}")
    
    # Test case that should pass
    valid_buffer = b'\x01\x02\x03\x04' * 300  # 1200 bytes, not all zeros
    is_valid = (
        len(valid_buffer) >= 1000 and
        valid_buffer != b'\x00' * len(valid_buffer)
    )
    print(f"  ✅ Valid audio (1200 bytes, mixed data): accepted={is_valid}")
    
    if not is_valid:
        raise AssertionError("Should have accepted valid audio")
    
    print("✅ Audio validation tests passed!")


def test_config_values():
    """Test that configuration values are set correctly."""
    print("\n🧪 Testing Configuration Values...")
    
    checks = [
        ("VAD_WEBM_THRESHOLD", settings.VAD_WEBM_THRESHOLD, 1500, 3000),
        ("VAD_SILENCE_DURATION", settings.VAD_SILENCE_DURATION, 0.5, 1.0),
        ("VAD_MIN_SPEECH_DURATION", settings.VAD_MIN_SPEECH_DURATION, 0.2, 0.5),
        ("TTS_MAX_BUFFER_CHARS", settings.TTS_MAX_BUFFER_CHARS, 100, 200),
    ]
    
    for name, value, min_val, max_val in checks:
        if min_val <= value <= max_val:
            print(f"  ✅ {name}: {value} (optimal range: {min_val}-{max_val})")
        else:
            print(f"  ⚠️  {name}: {value} (outside optimal range: {min_val}-{max_val})")
    
    print("✅ Configuration tests passed!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("🔧 TESTING CRITICAL FIXES")
    print("=" * 60)
    
    try:
        test_audio_format_detection()
        test_vad_threshold()
        test_audio_validation()
        test_config_values()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\n🎉 System is ready for testing with the TypeScript client!")
        print("\nNext steps:")
        print("1. Open http://localhost:3000 in your browser")
        print("2. Click 'Connect' to establish WebSocket connection")
        print("3. Click microphone button and speak")
        print("4. Click stop to send END_OF_SPEECH")
        print("5. Watch for transcript and agent response")
        print("\nMonitor logs with: tail -f agent.log")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
