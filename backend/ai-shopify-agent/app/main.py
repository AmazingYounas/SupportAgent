from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import os
import pathlib

from app.config import settings
from app.api.routes import router as api_router
from app.database.migrations import init_db

# ---------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agent.log', encoding='utf-8')
    ]
)
# Force UTF-8 for console output on Windows
import sys
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass  # Fallback if reconfigure not available

logger = logging.getLogger(__name__)

# Project root — where test.html lives (two levels up from app/main.py)
_ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------
# FastAPI App Initialization
# ---------------------------------------------------------
app = FastAPI(
    title="Voice AI Agent",
    description="Real-time duplex voice assistant for E-Commerce.",
    version="1.0.0",
)

# ---------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------
# "null" is the Origin sent by browsers when opening a local HTML file directly
# (file:// scheme). Include it so test.html works without a dev server.
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://localhost:5173"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"null",   # allow file:// origin during local testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Startup Events
# ---------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    """Run DB creation and migration checks on startup (if database is configured)."""
    try:
        if settings.DATABASE_URL and settings.DATABASE_URL != "postgresql://user:password@localhost/dbname":
            init_db()
            logger.info("Database initialized successfully")
        else:
            logger.warning("Database not configured - running in test mode without persistence")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        logger.warning("Continuing without database - persistence disabled")
    
    logger.info("AI Agent Backend started on http://localhost:8000")
    logger.info("Test UI available at http://localhost:8000/")

# ---------------------------------------------------------
# Route Inclusion
# ---------------------------------------------------------
app.include_router(api_router)

# ---------------------------------------------------------
# Health Check
# ---------------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Voice AI Agent", "version": "1.0.0"}

# ---------------------------------------------------------
# Serve test.html at root  (no build tools, no client folder)
# ---------------------------------------------------------
from fastapi.responses import FileResponse

@app.get("/")
async def serve_ui():
    """Serve the standalone voice agent test UI."""
    html_path = _ROOT / "test.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    return {"error": "test.html not found at project root"}

# ---------------------------------------------------------
# Execution Entry
# ---------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
