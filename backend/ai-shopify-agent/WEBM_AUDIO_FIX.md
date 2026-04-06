# WebM Audio Concatenation Issue

## Problem Identified

**Symptom**: Both Deepgram and ElevenLabs STT providers reject audio with "Invalid data" / "corrupted file" errors.

**Root Cause**: MediaRecorder sends WebM/Opus in chunks:
- First chunk: Contains EBML header + Opus frame
- Subsequent chunks: Raw Opus frames WITHOUT container headers
- When VAD concatenates with `b"".join()`, it creates an INVALID WebM file

**Why It Fails**:
```
Valid WebM structure:
[EBML Header][Segment][Cluster 1][Cluster 2]...

What we're creating:
[EBML Header + Frame 1][Frame 2][Frame 3]... ❌ INVALID
```

## Solutions

### Option 1: Use Streaming STT (RECOMMENDED)
Instead of batch transcription, use Deepgram's Live API which accepts chunked audio.

**Pros**:
- Handles chunked WebM natively
- Lower latency (real-time transcription)
- Already implemented in `deepgram.py`

**Cons**:
- More complex state management
- Requires connection management

### Option 2: Save to Temporary File
Write accumulated audio to a temp file, let OS/ffmpeg handle WebM validation.

**Pros**:
- Simple implementation
- Works with any format

**Cons**:
- Disk I/O overhead
- Requires cleanup

### Option 3: Use MediaRecorder with Smaller timeslice
Configure MediaRecorder to send complete WebM files more frequently.

**Client-side change**:
```typescript
this.mediaRecorder.start(5000); // 5 second chunks instead of 120ms
```

**Pros**:
- Each chunk is a valid WebM file
- No backend changes needed

**Cons**:
- Higher latency (5s delay before STT)
- Not true real-time

### Option 4: Convert to PCM on Client
Use Web Audio API to convert to PCM before sending.

**Pros**:
- PCM is simple, no container issues
- Works with all STT providers

**Cons**:
- Larger bandwidth (PCM is uncompressed)
- More client-side processing

## Recommended Fix: Hybrid Approach

1. **Short-term**: Increase MediaRecorder timeslice to 3000ms (3 seconds)
   - Each chunk will be a complete, valid WebM file
   - Acceptable latency for customer support use case

2. **Long-term**: Implement streaming STT
   - Use Deepgram Live API
   - True real-time transcription
   - Better user experience

## Implementation

### Quick Fix (Client-side)
```typescript
// In VoiceAgentClient.ts, line ~290
this.mediaRecorder.start(3000); // Change from 120 to 3000
```

### Proper Fix (Backend - Streaming STT)
Already implemented in `deepgram.py` - need to wire it up in `voice_service.py`.

## Testing

After applying fix, verify:
1. Connection succeeds
2. Speech detected by VAD
3. STT returns transcript (not "Invalid data")
4. Agent responds with audio
5. No "corrupted file" errors in logs
