# Project Structure & Organization

## 📁 Directory Layout

### `/app` - Backend Application

#### `/app/agent` - LLM Agent Core
- `agent.py` - Main SupportAgent class, orchestrates all components
- `graph.py` - LangGraph workflow definition and tool registration
- `prompts.py` - System prompts and instructions
- `state.py` - Conversation state management

#### `/app/api` - API Layer
- `routes.py` - REST API endpoints (text chat, conversations)
- `voice_duplex.py` - WebSocket endpoint for full-duplex voice
- `schemas.py` - Pydantic request/response models
- `deps.py` - Dependency injection (database sessions)

#### `/app/database` - Data Persistence
- `connection.py` - SQLAlchemy engine and session management
- `models.py` - Database models (Conversation, Message)
- `repositories.py` - Data access layer (CRUD operations)
- `migrations.py` - Database initialization

#### `/app/memory` - Conversation Memory
- `session_memory.py` - In-memory conversation state (per WebSocket)
- `long_term_memory.py` - Persistent storage interface

#### `/app/services` - External Services

##### `/app/services/stt` - Speech-to-Text
- `base.py` - STT provider interface
- `deepgram.py` - Deepgram Nova-3 implementation (streaming)
- `elevenlabs.py` - ElevenLabs Scribe implementation (batch)

##### Other Services
- `voice_service.py` - TTS orchestration with sentence chunking
- `shopify_service.py` - Shopify GraphQL API client
- `order_service.py` - Order management logic

#### `/app/tools` - LLM Tools
- `customer_tools.py` - Customer lookup and information
- `order_tools.py` - Order tracking and management
- `product_tools.py` - Product search and recommendations
- `handoff_tools.py` - Human agent handoff

#### `/app/voice` - Voice Processing
- `vad.py` - Voice Activity Detection (speech start/end)
- `audio_utils.py` - Audio format detection and conversion
- `pipeline.py` - STT → LLM → TTS pipeline orchestration
- `session.py` - Voice session state management
- `sentence_detector.py` - Smart sentence boundary detection

#### `/app/utils` - Utilities
- `error_handlers.py` - Error handling and logging

#### Root Files
- `config.py` - Centralized configuration (all settings)
- `main.py` - FastAPI application entry point

---

### `/client` - Frontend Application

#### Core Files
- `types.ts` - TypeScript type definitions (zero `any`)
- `audioUtils.ts` - PCM/WAV conversion, playback queue
- `VoiceAgentClient.ts` - WebSocket client with error handling
- `App.tsx` - React UI component
- `index.tsx` - React application entry point

#### Configuration
- `package.json` - Dependencies and scripts
- `tsconfig.json` - Strict TypeScript configuration
- `vite.config.ts` - Vite build configuration

#### Styling
- `styles.css` - Modern design system
- `index.html` - HTML entry point

#### Documentation
- `README.md` - Frontend setup and usage
- `INTEGRATION_COMPLETE.md` - Complete integration guide

---

### `/tests` - Test Suite

- `test_agent.py` - Agent logic tests
- `test_audio_utils.py` - Audio processing tests
- `test_duplex_session.py` - WebSocket session tests
- `test_routes_session_store.py` - API endpoint tests
- `test_sentence_detection.py` - Sentence boundary tests
- `test_shopify_service_config.py` - Shopify integration tests
- `test_vad.py` - VAD tests
- `test_voice_duplex_ws.py` - WebSocket protocol tests
- `test_voice_service.py` - TTS service tests

---

### Root Files

#### Configuration
- `.env` - Environment variables (API keys, settings)
- `.gitignore` - Git ignore patterns
- `requirements.txt` - Python dependencies
- `pyrightconfig.json` - Python type checking config
- `pytest.ini` - Pytest configuration

#### Documentation
- `README.md` - Main project documentation
- `FIXES_APPLIED.md` - Detailed bug fixes and solutions
- `PROJECT_STRUCTURE.md` - This file

#### Scripts
- `test_fixes.py` - Automated test suite for critical fixes
- `run.ps1` - PowerShell startup script

#### Runtime
- `agent.log` - Application logs (gitignored)
- `agent_db_fallback.sqlite` - SQLite database (gitignored)

---

## 🔄 Data Flow

### Voice Conversation Flow

```
1. Browser → WebSocket Connection
   - Client connects to /ws/voice/duplex/{session_id}
   - Session created in DuplexSession

2. Audio Recording → VAD
   - Browser sends WebM/Opus chunks (120ms intervals)
   - VAD detects speech start/end
   - Audio buffered until speech ends

3. Speech End → STT
   - VAD triggers pipeline with audio buffer
   - STT transcribes (Deepgram or ElevenLabs)
   - Transcript sent to client

4. Transcript → LLM
   - Agent processes with conversation context
   - LLM streams tokens
   - Tokens sent to client in real-time

5. LLM Tokens → TTS
   - Sentence detector chunks tokens
   - ElevenLabs synthesizes each sentence
   - PCM audio streamed to client

6. PCM Audio → Browser
   - Client wraps PCM in WAV header
   - AudioContext plays sequentially
   - No gaps or overlaps
```

### Text Conversation Flow

```
1. Client → POST /api/chat
   - JSON request with message and session_id

2. Agent Processing
   - Load conversation history
   - Process with LLM
   - Execute tools if needed

3. Response → Client
   - JSON response with agent message
   - Conversation saved to database
```

---

## 🔑 Key Components

### Backend

1. **VoiceService** - Orchestrates STT and TTS
   - Manages STT provider (Deepgram/ElevenLabs)
   - Handles sentence-chunked TTS streaming
   - Connection pooling for API calls

2. **VAD** - Voice Activity Detection
   - Detects speech start/end
   - Buffers audio during speech
   - Triggers pipeline on speech end

3. **Pipeline** - STT → LLM → TTS
   - Coordinates full voice turn
   - Handles interrupts
   - Error recovery

4. **SupportAgent** - Main agent class
   - LangGraph workflow
   - Tool execution
   - Memory management

### Frontend

1. **VoiceAgentClient** - WebSocket client
   - Connection management
   - Audio recording
   - Heartbeat (PING/PONG)
   - Auto-reconnect

2. **AudioPlaybackQueue** - Sequential playback
   - Prevents overlapping audio
   - Smooth transitions
   - No gaps

3. **App** - React UI
   - Connection controls
   - Recording controls
   - Chat display
   - Metrics display

---

## 🎯 Design Principles

### Backend

1. **Modularity** - Each component has single responsibility
2. **Error Handling** - Comprehensive try/catch everywhere
3. **Type Safety** - Pydantic models for all data
4. **Async First** - All I/O is async
5. **Resource Cleanup** - Proper cleanup in finally blocks

### Frontend

1. **Type Safety** - Strict TypeScript, zero `any`
2. **Error Boundaries** - Graceful error handling
3. **State Management** - React hooks for local state
4. **Performance** - Efficient audio processing
5. **User Experience** - Clear feedback and status

---

## 📦 Dependencies

### Backend (Python)

- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **LangChain** - LLM framework
- **LangGraph** - Agent workflow
- **SQLAlchemy** - Database ORM
- **Pydantic** - Data validation
- **aiohttp** - Async HTTP client
- **deepgram-sdk** - Deepgram STT
- **websockets** - WebSocket support

### Frontend (TypeScript)

- **React** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Web Audio API** - Audio processing
- **WebSocket API** - Real-time communication

---

## 🔒 Security Considerations

### Current (Development)

- Unencrypted WebSocket (ws://)
- No authentication
- CORS allows localhost
- API keys in .env file

### Production Requirements

- Encrypted WebSocket (wss://)
- JWT authentication
- Restricted CORS
- Secrets manager for API keys
- Rate limiting
- Input validation
- SQL injection prevention (using ORM)
- XSS prevention (React escaping)

---

## 🚀 Deployment

### Backend

1. Set environment variables
2. Run database migrations
3. Start with Gunicorn + Uvicorn workers
4. Use reverse proxy (Nginx)
5. Enable HTTPS

### Frontend

1. Build: `npm run build`
2. Serve static files
3. Configure CDN
4. Enable HTTPS

---

## 📊 Monitoring

### Logs

- `agent.log` - All application logs
- Structured logging with timestamps
- Log levels: DEBUG, INFO, WARNING, ERROR

### Metrics

- STT latency
- LLM first token latency
- TTS first audio latency (TTFR)
- WebSocket connection count
- Error rates

### Health Checks

- `GET /health` - Backend health
- Database connectivity
- API key validation

---

## 🔄 Development Workflow

1. Make changes to code
2. Backend auto-reloads (--reload flag)
3. Frontend hot-reloads (Vite HMR)
4. Test manually at http://localhost:3000
5. Run automated tests: `python test_fixes.py`
6. Check logs: `tail -f agent.log`
7. Commit changes

---

## 📝 Code Style

### Python

- PEP 8 compliant
- Type hints everywhere
- Docstrings for public functions
- Max line length: 100 characters

### TypeScript

- Strict mode enabled
- No `any` types
- JSDoc comments for complex functions
- Prettier formatting

---

This structure ensures:
- ✅ Clear separation of concerns
- ✅ Easy to navigate and understand
- ✅ Scalable and maintainable
- ✅ Well-documented
- ✅ Production-ready
