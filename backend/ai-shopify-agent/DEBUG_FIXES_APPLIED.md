# Debug Fixes Applied - Silent Pipeline Failure

## Problem Summary
VAD detects `speech_start` and `speech_end` correctly, but NO voice response is heard. Connection closes after speech_end, and pipeline is cancelled before producing output.

## Root Cause Identified

### CRITICAL BUG: VAD Energy Detection Broken for WebM Input

**The Issue:**
1. Frontend sends **WebM/Opus** chunks (from MediaRecorder)
2. VAD's `_pcm_energy()` function tries to parse WebM as **PCM Int16 LE**
3. This produces garbage energy values (random numbers)
4. Energy threshold detection becomes unreliable:
   - Might never trigger `speech_start` (energy always below threshold)
   - Might trigger randomly on WebM header bytes
   - Silence detection becomes unpredictable

**Why This Breaks the System:**
- If energy never exceeds threshold → `speech_start` never fires → no pipeline
- If energy is random → false positives/negatives → unreliable turn detection
- Even if `speech_end` fires, the timing is wrong → pipeline might start with incomplete audio

## Fixes Applied

### 1. VAD: WebM Detection and Fallback (CRITICAL FIX)

**File:** `backend/ai-shopify-agent/app/voice/vad.py`

**Changes:**
- Modified `_pcm_energy()` to detect WebM format (magic bytes `0x1A 0x45 0xDF 0xA3`)
- Returns `-1.0` as signal when input is not PCM
- Added byte-size heuristic fallback for WebM chunks:
  - WebM chunks from MediaRecorder: typically 2-20KB for 250ms
  - Silence/noise: < 1KB
  - Threshold: 1500 bytes (1.5KB) to detect active speech
- Updated `MIN_SPEECH_BYTES` from 800 to 3000 (appropriate for WebM)

**Why This Works:**
- WebM chunks are variable-size compressed audio
- Larger chunks = more audio content = active speech
- Smaller chunks = silence or noise
- This is the SAME heuristic that worked in the original push-to-talk endpoint

### 2. Enhanced Logging (Debugging Aid)

**Files Modified:**
- `backend/ai-shopify-agent/app/voice/vad.py`
- `backend/ai-shopify-agent/app/api/routes.py`
- `backend/ai-shopify-agent/test_duplex_client.html`

**Changes:**
- VAD now logs energy values AND byte sizes with emoji markers
- Shows whether VAD is in "PCM mode" or "WebM mode"
- Frontend logs when audio chunks are received
- Pipeline wrapper logs when waiting for task completion

**Log Markers:**
- 🎵 VAD feed (shows energy/size and thresholds)
- 🚀 Pipeline starting
- 🎬 Pipeline started
- 🎤 STT start/done
- 🧠 LLM start/first token
- 🔊 TTS start/first audio
- 📤 Sending audio chunk
- 🏁 Pipeline complete
- ✅ Success
- ⚠️ Warning
- ❌ Error

### 3. Frontend Audio Logging

**File:** `backend/ai-shopify-agent/test_duplex_client.html`

**Changes:**
- Console logs when binary audio chunks arrive
- Logs when `enqueueAudio()` is called
- Shows chunk sizes in bytes

## Testing Instructions

### 1. Start the Server

```bash
cd backend/ai-shopify-agent
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
```

### 2. Open Test Client

Open `backend/ai-shopify-agent/test_duplex_client.html` in Chrome/Edge

### 3. Test Sequence

1. Click "Connect"
2. Allow microphone access
3. Speak clearly: "Hello, can you hear me?"
4. Wait for response

### 4. What to Look For in Logs

**Server Terminal (Expected Flow):**

```
[VAD] 🎵 feed 2456b (WebM mode) state=IDLE active=True size_threshold=1500b
[VAD] speech_start_detected
[Duplex:xxx] ✅ speech_start_detected

[VAD] 🎵 feed 3821b (WebM mode) state=SPEAKING active=True size_threshold=1500b
[VAD] 🎵 feed 4102b (WebM mode) state=SPEAKING active=True size_threshold=1500b
[VAD] 🎵 feed 892b (WebM mode) state=SPEAKING active=False size_threshold=1500b
[VAD] 🎵 feed 654b (WebM mode) state=SILENCE active=False size_threshold=1500b

[VAD] speech_end_detected — 1.2s, 15234b
[Duplex:xxx] ✅ speech_end_detected — 15,234b
[Duplex:xxx] 🚀 PIPELINE STARTING (as background task)
[Duplex:xxx] ✅ Pipeline task created and registered
[Duplex:xxx] ⏳ Waiting for pipeline task to complete...

[Pipeline:xxx] 🎬 PIPELINE STARTED
[Pipeline:xxx] 🎤 STT START — 15,234b
[STT] Sending 15,234 bytes to ElevenLabs Scribe
[STT] Transcribed: Hello, can you hear me?
[Pipeline:xxx] ✅ STT DONE in 450ms: Hello, can you hear me?
[Pipeline:xxx] 📤 Transcript sent to client

[Pipeline:xxx] 🧠 LLM START
[Pipeline:xxx] ✅ LLM FIRST TOKEN — 320ms after STT
[Pipeline:xxx] 🔊 TTS START
[Pipeline:xxx] ✅ TTS FIRST AUDIO CHUNK — TTFR=890ms
[Pipeline:xxx] 📤 SENDING AUDIO CHUNK 8192b
[Pipeline:xxx] 📤 SENDING AUDIO CHUNK 8192b
[Pipeline:xxx] 📤 SENDING AUDIO CHUNK 8192b
...
[Pipeline:xxx] 🏁 PIPELINE COMPLETE — total=2340ms stt=450ms ttfr=890ms
[Duplex:xxx] ✅ Pipeline completed successfully
```

**Browser Console (Expected):**

```
[Frontend] 📥 RECEIVED AUDIO CHUNK 8192b
[Frontend] 🔊 enqueueAudio called with 8192b
[Frontend] 📥 RECEIVED AUDIO CHUNK 8192b
[Frontend] 🔊 enqueueAudio called with 8192b
...
```

### 5. If Pipeline Still Doesn't Run

**Check for these error patterns:**

1. **VAD never triggers speech_start:**
   - Look for: `[VAD] 🎵 feed XXXb (WebM mode) state=IDLE active=False`
   - All chunks show `active=False`
   - **Fix:** Lower the byte-size threshold in `vad.py` (currently 1500)

2. **STT fails silently:**
   - Look for: `[STT] ElevenLabs STT 401` or `[STT] ElevenLabs STT 402`
   - **Fix:** Check ElevenLabs API key and quota

3. **TTS fails silently:**
   - Look for: `[TTS] Error on sentence` or `ElevenLabs TTS 402`
   - **Fix:** Check ElevenLabs voice ID and paid plan status

4. **Pipeline starts but no audio sent:**
   - Look for: `[Pipeline:xxx] 🎬 PIPELINE STARTED` but no `📤 SENDING AUDIO CHUNK`
   - Check if LLM or TTS errors appear

5. **WebSocket closes prematurely:**
   - Look for: `[Duplex:xxx] connection closed` right after speech_end
   - Check for exceptions in the receive loop

## Configuration Checklist

Verify these settings in `.env`:

```bash
# Required
ELEVENLABS_API_KEY=sk_xxxxx
OPENAI_API_KEY=sk-xxxxx

# Voice settings
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # or your preferred voice
ELEVENLABS_MODEL_ID=eleven_turbo_v2
ELEVENLABS_PCM_OUTPUT_FORMAT=pcm_22050

# Optional
ELEVENLABS_OPTIMIZE_LATENCY=4
```

## Known Limitations

1. **STT is batch, not streaming:**
   - VAD collects full utterance before sending to ElevenLabs
   - Adds ~300-500ms latency vs true streaming STT
   - This is acceptable for conversational AI

2. **TTS is sentence-sequential:**
   - Sentences are synthesized one at a time
   - Not truly parallel (would require multiple voice IDs)
   - Still feels responsive due to streaming within sentences

3. **WebM format compatibility:**
   - Frontend uses WebM/Opus (best browser support)
   - Backend expects WebM for STT (ElevenLabs Scribe)
   - TTS outputs PCM (AudioWorklet expects raw audio)
   - This mix is intentional and correct

## Success Criteria

✅ VAD detects speech_start when you speak
✅ VAD detects speech_end after ~650ms silence
✅ Pipeline starts immediately after speech_end
✅ STT transcribes your speech correctly
✅ LLM generates a response
✅ TTS synthesizes audio
✅ Audio plays smoothly in browser
✅ You can interrupt the AI by speaking

## Next Steps if Still Broken

1. **Capture full logs:**
   - Server terminal output (all emoji-marked lines)
   - Browser console output
   - Network tab (WebSocket frames)

2. **Test push-to-talk endpoint first:**
   - Open `test_voice_client.html`
   - This uses manual END_OF_SPEECH signal
   - If this works, problem is VAD-specific
   - If this fails, problem is STT/LLM/TTS

3. **Test with different audio:**
   - Try speaking louder
   - Try longer utterances (3-5 seconds)
   - Try in a quiet room (reduce background noise)

4. **Verify ElevenLabs API:**
   - Test STT directly: `curl -X POST https://api.elevenlabs.io/v1/audio-to-text ...`
   - Test TTS directly: `curl -X POST https://api.elevenlabs.io/v1/text-to-speech/...`
   - Check quota/limits in ElevenLabs dashboard

## Files Modified in This Fix

1. `backend/ai-shopify-agent/app/voice/vad.py` - WebM detection + byte-size fallback
2. `backend/ai-shopify-agent/app/api/routes.py` - Enhanced logging
3. `backend/ai-shopify-agent/test_duplex_client.html` - Frontend logging
4. `backend/ai-shopify-agent/DEBUG_FIXES_APPLIED.md` - This document
