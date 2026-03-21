# Quick Start Guide - Full-Duplex Voice Agent

## 🚀 Start the Server

```bash
cd backend/ai-shopify-agent
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
```

## 🎤 Test the Agent

### Option 1: Full-Duplex Mode (Recommended)
Open `test_duplex_client.html` in Chrome/Edge
- VAD automatically detects when you speak
- Speak naturally, no buttons needed
- Interrupt the AI by speaking over it

### Option 2: Push-to-Talk Mode (Simpler)
Open `test_voice_client.html` in Chrome/Edge
- Click "Start Recording" to speak
- Click "Stop Recording" when done
- Good for testing basic STT/LLM/TTS flow

## 📊 What to Look For

### Server Logs (Good Flow)
```
[VAD] 🎵 feed 3456b (WebM mode) state=IDLE active=True
[VAD] speech_start_detected
[VAD] speech_end_detected — 1.2s, 15234b
[Duplex:xxx] 🚀 PIPELINE STARTING
[Pipeline:xxx] 🎬 PIPELINE STARTED
[Pipeline:xxx] 🎤 STT START
[Pipeline:xxx] ✅ STT DONE in 450ms
[Pipeline:xxx] 🧠 LLM START
[Pipeline:xxx] ✅ LLM FIRST TOKEN
[Pipeline:xxx] 🔊 TTS START
[Pipeline:xxx] ✅ TTS FIRST AUDIO CHUNK — TTFR=890ms
[Pipeline:xxx] 📤 SENDING AUDIO CHUNK 8192b
[Pipeline:xxx] 🏁 PIPELINE COMPLETE
```

### Browser Console (Good Flow)
```
[Frontend] 📥 RECEIVED AUDIO CHUNK 8192b
[Frontend] 🔊 enqueueAudio called with 8192b
```

## ⚠️ Common Issues

### Issue: VAD never triggers
**Symptom:** All chunks show `active=False`
**Fix:** Speak louder or lower threshold in `vad.py` line 28

### Issue: STT fails (401/402)
**Symptom:** `[STT] ElevenLabs STT 401`
**Fix:** Check `ELEVENLABS_API_KEY` in `.env`

### Issue: TTS fails (402)
**Symptom:** `[TTS] ElevenLabs TTS 402`
**Fix:** Verify paid plan and `ELEVENLABS_VOICE_ID`

### Issue: No audio plays
**Symptom:** No `[Frontend] 📥 RECEIVED AUDIO CHUNK` in console
**Fix:** Check TTS logs for errors

## 🔧 Configuration

Required in `.env`:
```bash
ELEVENLABS_API_KEY=sk_xxxxx
OPENAI_API_KEY=sk-xxxxx
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
ELEVENLABS_PCM_OUTPUT_FORMAT=pcm_22050
```

## 📝 Test Commands

```bash
# Test VAD logic
python test_vad_logic.py

# Check diagnostics
python -m pytest tests/ -v

# View logs in real-time
# (server already shows logs, no extra command needed)
```

## 🎯 Success Checklist

- [ ] Server starts without errors
- [ ] Browser connects to WebSocket
- [ ] Microphone permission granted
- [ ] VAD detects speech_start when you speak
- [ ] VAD detects speech_end after silence
- [ ] Pipeline starts and completes
- [ ] Audio plays in browser
- [ ] You can interrupt the AI

## 📚 Documentation

- `SOLUTION_SUMMARY.md` - What was fixed and why
- `DEBUG_FIXES_APPLIED.md` - Detailed debugging guide
- `SYSTEM_ARCHITECTURE.md` - Full system overview
- `FLOW_DIAGRAMS.md` - Visual flow diagrams
- `QUICK_REFERENCE.md` - Developer reference

## 🆘 Still Not Working?

1. Capture full server logs (all emoji lines)
2. Capture browser console output
3. Check Network tab for WebSocket frames
4. Try push-to-talk mode first (`test_voice_client.html`)
5. Verify ElevenLabs API works: test STT/TTS directly via curl

## 🎉 Expected Performance

- STT: 300-600ms
- LLM first token: 200-400ms
- TTS first audio: 400-800ms
- **Total TTFR: < 2 seconds** ✅
