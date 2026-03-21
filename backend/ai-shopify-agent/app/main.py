from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import os

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

# ---------------------------------------------------------
# FastAPI App Initialization
# ---------------------------------------------------------
app = FastAPI(
    title="Shopify AI Agent Backend",
    description="Text and Zero-Latency Streaming Voice Assistant for E-Commerce.",
    version="1.0.0",
)

# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------
# Configure CORS - restrict to specific origins
# For development, allow localhost. For production, set ALLOWED_ORIGINS in .env
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Restricted to specific domains
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
            logger.info("✅ Database initialized successfully")
        else:
            logger.warning("⚠️  Database not configured - running in test mode without persistence")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        logger.warning("⚠️  Continuing without database - persistence disabled")
    
    logger.info("🚀 AI Agent Backend Services started")
    logger.info(f"📝 Logging to: agent.log")
    logger.info(f"🔧 Debug mode: {settings.DEBUG}")

# ---------------------------------------------------------
# Route Inclusion
# ---------------------------------------------------------
app.include_router(api_router)

# ---------------------------------------------------------
# Execution Entry
# ---------------------------------------------------------
if __name__ == "__main__":
    # Run locally using Uvicorn.
    # In production, use `uvicorn app.main:app --host 0.0.0.0 --port 8000`
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=settings.DEBUG
    )
