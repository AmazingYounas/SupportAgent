# Extreme Audio Debugging Guide

## What Was Implemented

### 1. Deep Audio Analysis Module (`audio_debug.py`)

**Analyzes every audio buffer with**:
- Size and hash (for uniqueness tracking)
- Format detection (WebM, WAV, MP3, etc.)
- First 4, 16 bytes (hex dump)
- Last 16 bytes (hex dump)
- WebM structure validation:
  - EBML header presence
  - Segment marker
  - Cluster marker
  - Tracks marker
- Corruption detection:
  - All zeros check
  - Repeating pattern check
- **Saves samples to disk** for manual inspection

### 2. VAD Buffer Analysis

**Logs when speech ends**:
- Number of chunks accumulated
- Total buffer size
- Complete buffer analysis
- **Saves accumulated buffer to disk**

### 3. Voice Service Extreme Logging

**Logs at every step**:
1. **Incoming buffer** - What VAD sends
2. **Temp file write** - What gets written
3. **Temp file read** - What gets read back
4. **Comparison** - Original vs file (catches corruption)
5. **Sending to Deepgram** - Final buffer analysis
6. **Direct buffer attempt** - If temp file fails
7. **ElevenLabs fallback** - Last resort

## What You'll See in Logs

### Successful Recording
```
🔍 EXTREME AUDIO DEBUGGING ENABLED
[AudioDebug:INCOMING_BUFFER] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[AudioDebug:INCOMING_BUFFER] Size: 60,754 bytes
[AudioDebug:INCOMING_BUFFER] Hash: a3f2b1c4
[AudioDebug:INCOMING_BUFFER] Format: WebM (EBML)
[AudioDebug:INCOMING_BUFFER] First 4 bytes: 1a45dfa3
[AudioDebug:INCOMING_BUFFER] Has EBML header: True
[AudioDebug:INCOMING_BUFFER] Has Segment: True
[AudioDebug:INCOMING_BUFFER] Has Cluster: True
[AudioDebug:INCOMING_BUFFER] Likely valid WebM: True ✅
[AudioDebug:INCOMING_BUFFER] 💾 Sample saved: audio_debug_samples/INCOMING_BUFFER_20260403_210830_a3f2b1c4.webm
```

### Failed Recording (Corrupted)
```
🔍 EXTREME AUDIO DEBUGGING ENABLED
[AudioDebug:INCOMING_BUFFER] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[AudioDebug:INCOMING_BUFFER] Size: 87,833 bytes
[AudioDebug:INCOMING_BUFFER] Hash: f7e9d2a1
[AudioDebug:INCOMING_BUFFER] Format: Unknown ❌
[AudioDebug:INCOMING_BUFFER] First 4 bytes: 43c38102 ❌
[AudioDebug:INCOMING_BUFFER] Has EBML header: False ❌
[AudioDebug:INCOMING_BUFFER] Has Segment: False ❌
[AudioDebug:INCOMING_BUFFER] Has Cluster: False ❌
[AudioDebug:INCOMING_BUFFER] Likely valid WebM: False ❌
[AudioDebug:INCOMING_BUFFER] 💾 Sample saved: audio_debug_samples/INCOMING_BUFFER_20260403_211001_f7e9d2a1.webm
```

## Audio Samples Saved

All audio buffers are saved to: `backend/ai-shopify-agent/audio_debug_samples/`

**Naming convention**: `{label}_{timestamp}_{hash}.webm`

Examples:
- `INCOMING_BUFFER_20260403_210830_a3f2b1c4.webm` - What VAD sent
- `VAD_ACCUMULATED_15_chunks_20260403_210830_a3f2b1c4.webm` - VAD buffer (15 chunks)

**You can**:
1. Play these files in VLC/media player
2. Inspect with `ffprobe` or `mediainfo`
3. Compare working vs broken files
4. Send to us for analysis

## How to Use

### 1. Test and Collect Samples

```bash
# Start backend (extreme debug is now active)
cd backend/ai-shopify-agent
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Test voice recording
# Samples will be saved to audio_debug_samples/
```

### 2. Inspect Logs

```bash
# Watch logs in real-time
tail -f agent.log | grep -E "AudioDebug|🔍"

# Or check full logs
cat agent.log | grep "AudioDebug"
```

### 3. Analyze Saved Samples

```bash
# Check if file is valid WebM
ffprobe audio_debug_samples/INCOMING_BUFFER_*.webm

# Or use mediainfo
mediainfo audio_debug_samples/INCOMING_BUFFER_*.webm

# Play in VLC
vlc audio_debug_samples/INCOMING_BUFFER_*.webm
```

### 4. Compare Working vs Broken

```bash
# List all samples
ls -lh audio_debug_samples/

# Compare hex dumps
xxd audio_debug_samples/INCOMING_BUFFER_good.webm | head -20
xxd audio_debug_samples/INCOMING_BUFFER_bad.webm | head -20
```

## What to Look For

### In Logs

1. **First 4 bytes**:
   - `1a45dfa3` = Valid WebM ✅
   - Anything else = Corrupted ❌

2. **WebM markers**:
   - Has EBML header: True ✅
   - Has Segment: True ✅
   - Has Cluster: True ✅
   - All three = Valid WebM

3. **Comparison results**:
   - "Same hash: True" = File write/read OK ✅
   - "Same hash: False" = Corruption during file I/O ❌

### In Saved Files

1. **File size**:
   - Should match log size
   - If different = corruption

2. **Playability**:
   - Can play in VLC = Valid ✅
   - Cannot play = Corrupted ❌

3. **ffprobe output**:
   - Shows codec info = Valid ✅
   - Errors = Corrupted ❌

## Debugging Scenarios

### Scenario 1: First Recording Works, Second Fails

**Look for**:
- Compare hashes of first vs second
- Check if second has EBML header
- Compare VAD chunk counts
- Check MediaRecorder reset in client

### Scenario 2: All Recordings Fail

**Look for**:
- Browser sending wrong format
- MediaRecorder codec issues
- Network corruption
- VAD concatenation problems

### Scenario 3: Temp File Corruption

**Look for**:
- "Comparing original buffer vs temp file"
- Different hashes = File I/O issue
- Same hash but still fails = Deepgram API issue

### Scenario 4: Random Failures

**Look for**:
- Pattern in chunk counts
- Pattern in buffer sizes
- Specific hash that always fails
- Time-based patterns

## Performance Impact

**Overhead**:
- Logging: ~10ms per recording
- File I/O: ~50ms per recording
- Disk space: ~50-100KB per recording

**Recommendation**:
- Use for debugging only
- Disable in production
- Clean up samples regularly

## Disabling Debug Mode

To disable extreme debugging:

```python
# In voice_service.py, comment out debug lines:
# log_audio_analysis(audio_buffer, label="INCOMING_BUFFER", save_sample=True)

# In vad.py, comment out:
# log_audio_analysis(audio, label=f"VAD_ACCUMULATED_{len(self._speech_buffer)}_chunks", save_sample=True)
```

## Next Steps

1. **Test multiple recordings**
2. **Collect samples** (working + broken)
3. **Analyze logs** for patterns
4. **Inspect saved files** with ffprobe
5. **Compare** working vs broken files
6. **Share findings** for deeper analysis

This will definitively show us what's wrong with the audio!
