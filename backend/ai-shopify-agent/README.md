# AI Shopify Agent Backend

Text and Zero-Latency Streaming Voice Assistant for E-Commerce.

## Architecture

- **FastAPI**: REST API + WebSocket server
- **LangGraph**: Stateful AI agent workflow
- **LangChain**: LLM orchestration
- **PostgreSQL**: Persistent storage
- **OpenAI GPT-4**: Agent reasoning
- **ElevenLabs**: Voice streaming (optional)

## Setup

### 1. Prerequisites

- **Python 3.13.12** (Latest Stable - RECOMMENDED)
  - Download: https://www.python.org/downloads/
  - Direct: https://www.python.org/ftp/python/3.13.12/python-3.13.12-amd64.exe
  - Why 3.13? Python 3.12.13+ no longer provides Windows installers
  - See `PYTHON_UPGRADE_GUIDE.md` for detailed instructions
- PostgreSQL database
- OpenAI API key
- Shopify API credentials

### 2. Quick Installation (Automated)

**Option A: PowerShell (Recommended)**
```powershell
# Run the setup script
.\setup_python313.ps1
```

**Option B: CMD**
```cmd
setup_python313.bat
```

### 3. Manual Installation

```bash
# Verify Python 3.13 is installed
py -3.13 --version

# Remove old virtual environment (if exists)
Remove-Item -Recurse -Force .venv

# Create virtual environment with Python 3.13
py -3.13 -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Windows CMD)
.venv\Scripts\activate.bat

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Copy `.env` and fill in your credentials:

```env
OPENAI_API_KEY=sk-...
SHOPIFY_API_KEY=...
SHOPIFY_API_SECRET=...
SHOPIFY_SHOP_URL=your-store.myshopify.com
DATABASE_URL=postgresql://user:password@localhost/agent_db
ELEVENLABS_API_KEY=...
```

**Note on Certificate Warning:** ~~If you see a Windows SmartScreen warning during Python installation, see `CERTIFICATE_WARNING_INFO.md` for details. TL;DR: It's safe - click "More info" → "Run anyway".~~

**Update:** Python 3.13.12 has proper Windows installers and no certificate issues!

### 4. Database Setup

```bash
# Initialize database tables
python -m app.database.migrations
```

### 5. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/
```

### 6. Start Server

```bash
# Development mode
python app/main.py

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
app/
├── agent/          # LangGraph AI agent
├── api/            # FastAPI routes
├── database/       # SQLAlchemy models
├── memory/         # Conversation memory
├── services/       # Business logic
├── tools/          # LangChain tools
└── utils/          # Utilities
```

## Known Issues

### Windows Path Length Error (ElevenLabs)

If you encounter path length errors on Windows:

1. Enable long paths in Windows:
   - Run as Administrator: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force`
   - Restart your computer

2. Or install ElevenLabs separately:
   ```bash
   pip install elevenlabs --no-cache-dir
   ```

3. Or use a shorter project path (e.g., `C:\Dev\Agent\`)
