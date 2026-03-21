import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
# Assuming .env is at the root of the backend folder
load_dotenv()

class Settings(BaseSettings):
    """
    Centralized configuration for the AI Shopify Agent Backend.
    Values are loaded from the environment or .env file.
    """
    
    # ---------------------------------------------------------
    # System Settings
    # ---------------------------------------------------------
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # ---------------------------------------------------------
    # OpenAI Settings
    # ---------------------------------------------------------
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # ---------------------------------------------------------
    # Shopify Settings
    # ---------------------------------------------------------
    SHOPIFY_API_KEY: str = os.getenv("SHOPIFY_API_KEY", "")
    SHOPIFY_API_SECRET: str = os.getenv("SHOPIFY_API_SECRET", "")
    SHOPIFY_SHOP_URL: str = os.getenv("SHOPIFY_SHOP_URL", "")
    SHOPIFY_API_VERSION: str = os.getenv("SHOPIFY_API_VERSION", "2024-01")

    # ---------------------------------------------------------
    # Database Settings
    # ---------------------------------------------------------
    # Default to an in-memory or file-based sqlite db if not provided to avoid leaking hardcoded credentials
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:///./agent_db_fallback.sqlite"
    )

    # ---------------------------------------------------------
    # ElevenLabs Voice Settings
    # ---------------------------------------------------------
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    # Default voice ID for a human-like, professional agent (e.g., Sarah/Rachel)
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") 
    # Use eleven_turbo_v2 for speed (with language_code lock) or eleven_monolingual_v1 for English-only
    ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2")
    
    # Streaming specific parameters to minimize latency
    ELEVENLABS_OPTIMIZE_LATENCY: int = int(os.getenv("ELEVENLABS_OPTIMIZE_LATENCY", "4"))
    # MP3 format for push-to-talk endpoint (browser decodeAudioData)
    ELEVENLABS_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    # PCM format for duplex endpoint (AudioWorklet frontend expects raw Int16 22050Hz)
    ELEVENLABS_PCM_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_PCM_OUTPUT_FORMAT", "pcm_22050")

settings = Settings()
