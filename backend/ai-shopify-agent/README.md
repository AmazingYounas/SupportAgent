# AI Shopify Voice Agent

Production-ready voice assistant for e-commerce with real-time speech processing, LLM integration, and text-to-speech capabilities.

## 🏗️ Project Structure

```
backend/ai-shopify-agent/
├── app/                          # Main application code
│   ├── agent/                    # LLM agent logic
│   ├── api/                      # API endpoints & WebSocket
│   ├── database/                 # Database layer
│   ├── memory/                   # Conversation memory
│   ├── services/                 # External services (STT, TTS, Shopify)
│   ├── tools/                    # LLM tools
│   ├── voice/                    # Voice processing (VAD, pipeline)
│   ├── utils/                    # Utilities
│   ├── config.py                 # Configuration
│   └── main.py                   # FastAPI app entry
├── client/                       # TypeScript React client
│   ├── types.ts                 # Type definitions
│   ├── audioUtils.ts            # Audio processing
│   ├── VoiceAgentClient.ts      # WebSocket client
│   ├── App.tsx                  # React UI
│   └── ...
├── tests/                        # Test suite
├── .env                          # Environment variables
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── FIXES_APPLIED.md             # Bug fixes documentation
└── test_fixes.py                # Automated test suite
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- API Keys: OpenAI, ElevenLabs, Deepgram (optional)

### 1. Backend Setup

```bash
cd backend/ai-shopify-agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
# Edit .env with your API keys

# Run tests
python test_fixes.py

# Start server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup

```bash
cd backend/ai-shopify-agent/client

# Install dependencies
npm install

# Start dev server
npm run dev

# Open browser to http://localhost:3000
```

## 🔧 Configuration

### Required Environment Variables

```bash
# OpenAI (LLM)
OPENAI_API_KEY=sk-...

# ElevenLabs (TTS + optional STT)
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Deepgram (optional, better STT)
DEEPGRAM_API_KEY=...
STT_PROVIDER=deepgram  # or "elevenlabs"
```

### Optional Configuration

```bash
# Shopify Integration
SHOPIFY_ADMIN_ACCESS_TOKEN=...
SHOPIFY_SHOP_URL=your-store.myshopify.com

# VAD Tuning
VAD_WEBM_THRESHOLD=1500        # Lower = more sensitive
VAD_SILENCE_DURATION=0.65      # Seconds before speech ends

# TTS Tuning
TTS_MAX_BUFFER_CHARS=150       # Lower = faster, choppier
TTS_SENTENCE_TIMEOUT=0.5       # Force flush timeout
```

## 📊 Architecture

### Voice Pipeline Flow

```
Browser (MediaRecorder)
    ↓ WebSocket (WebM/Opus audio)
Backend WebSocket Handler
    ↓ Audio chunks
Voice Activity Detection (VAD)
    ↓ Speech detected
Speech-to-Text (Deepgram/ElevenLabs)
    ↓ Transcript
LLM Agent (OpenAI GPT-4)
    ↓ Streaming tokens
Text-to-Speech (ElevenLabs)
    ↓ PCM audio chunks
Browser (AudioContext playback)
```

## 🧪 Testing

### Run Backend Tests

```bash
cd backend/ai-shopify-agent
python test_fixes.py
```

### Manual Testing

1. Open `http://localhost:3000`
2. Click "Connect"
3. Click microphone button
4. Speak for 2-3 seconds
5. Click stop
6. Verify: transcript → agent response → audio playback

### Monitor Logs

```bash
tail -f backend/ai-shopify-agent/agent.log
```

## 📈 Performance Targets

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| STT Latency | < 800ms | < 2000ms | > 2000ms |
| First LLM Token | < 1500ms | < 3000ms | > 3000ms |
| First Audio (TTFR) | < 2000ms | < 4000ms | > 4000ms |

## 📚 Documentation

- [FIXES_APPLIED.md](./FIXES_APPLIED.md) - Detailed bug fixes
- [client/README.md](./client/README.md) - Frontend documentation
- [client/INTEGRATION_COMPLETE.md](./client/INTEGRATION_COMPLETE.md) - Integration guide

## 🔐 Security Notes

**Development Mode** (current):
- WebSocket uses `ws://` (unencrypted)
- No authentication
- CORS allows localhost

**Production Requirements**:
- Use `wss://` (secure WebSocket)
- Implement authentication/authorization
- Restrict CORS to production domains
- Use secrets manager for API keys

## 📝 License

MIT
