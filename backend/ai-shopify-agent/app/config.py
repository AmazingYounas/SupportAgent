import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """
    Centralized configuration for the AI Shopify Agent Backend.
    All tunable parameters are here for easy adjustment.
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # System Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OpenAI Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # OPTIMIZED: gpt-4o-mini for 2-3x faster responses
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "250"))  # OPTIMIZED: Increased for mini
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))
    OPENAI_TIMEOUT: float = float(os.getenv("OPENAI_TIMEOUT", "30.0"))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Shopify Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    SHOPIFY_API_KEY: str = os.getenv("SHOPIFY_API_KEY", "")
    SHOPIFY_API_SECRET: str = os.getenv("SHOPIFY_API_SECRET", "")
    # Prefer dedicated admin token; fallback keeps old envs working.
    SHOPIFY_ADMIN_ACCESS_TOKEN: str = os.getenv(
        "SHOPIFY_ADMIN_ACCESS_TOKEN",
        os.getenv("SHOPIFY_API_SECRET", "")
    )
    SHOPIFY_SHOP_URL: str = os.getenv("SHOPIFY_SHOP_URL", "")
    SHOPIFY_API_VERSION: str = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Database Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./agent_db_fallback.sqlite")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STT (Speech-to-Text) Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    STT_PROVIDER: str = os.getenv("STT_PROVIDER", "deepgram")  # "deepgram" or "elevenlabs"
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TTS (Text-to-Speech) Settings - ElevenLabs
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")  # Creator plan: Turbo v2.5 for best quality + speed balance
    ELEVENLABS_OPTIMIZE_LATENCY: int = int(os.getenv("ELEVENLABS_OPTIMIZE_LATENCY", "2"))
    
    # Audio formats
    ELEVENLABS_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    ELEVENLABS_PCM_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_PCM_OUTPUT_FORMAT", "pcm_24000")  # Creator plan max: pcm_24000 (pcm_44100 requires Pro+)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VAD (Voice Activity Detection) Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Energy thresholds for PCM mode (0-32767 scale)
    # With PCM Int16 from browser ScriptProcessorNode:
    #   Ambient silence ≈ 30-80, speech ≈ 200-8000, loud speech ≈ 5000-20000
    VAD_SPEECH_THRESHOLD: int = int(os.getenv("VAD_SPEECH_THRESHOLD", "150"))
    VAD_SILENCE_THRESHOLD: int = int(os.getenv("VAD_SILENCE_THRESHOLD", "80"))
    
    # Byte-size threshold for WebM fallback mode (bytes)
    # With PCM capture, energy-based detection is preferred (more accurate).
    # This threshold is only used if audio is misdetected as WebM.
    VAD_WEBM_THRESHOLD: int = int(os.getenv("VAD_WEBM_THRESHOLD", "1200"))
    
    # Timing thresholds
    VAD_SILENCE_DURATION: float = float(os.getenv("VAD_SILENCE_DURATION", "0.65"))
    VAD_MIN_SPEECH_DURATION: float = float(os.getenv("VAD_MIN_SPEECH_DURATION", "0.25"))
    VAD_MIN_SPEECH_BYTES: int = int(os.getenv("VAD_MIN_SPEECH_BYTES", "8000"))
    VAD_MAX_SPEECH_DURATION: float = float(os.getenv("VAD_MAX_SPEECH_DURATION", "5.0"))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TTS Streaming Settings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sentence detection (OPTIMIZED: 200 → 40 for faster response)
    TTS_MAX_BUFFER_CHARS: int = int(os.getenv("TTS_MAX_BUFFER_CHARS", "40"))
    TTS_SENTENCE_TIMEOUT: float = float(os.getenv("TTS_SENTENCE_TIMEOUT", "0.5"))
    
    # Queue sizes
    TTS_META_QUEUE_SIZE: int = int(os.getenv("TTS_META_QUEUE_SIZE", "10"))
    TTS_AUDIO_QUEUE_SIZE: int = int(os.getenv("TTS_AUDIO_QUEUE_SIZE", "10"))
    
    # Connection pool
    TTS_MAX_CONNECTIONS: int = int(os.getenv("TTS_MAX_CONNECTIONS", "500"))
    TTS_MAX_CONNECTIONS_PER_HOST: int = int(os.getenv("TTS_MAX_CONNECTIONS_PER_HOST", "100"))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Session Management
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    MAX_ACTIVE_SESSIONS: int = int(os.getenv("MAX_ACTIVE_SESSIONS", "1000"))
    MAX_SESSION_LOCKS: int = int(os.getenv("MAX_SESSION_LOCKS", "5000"))
    SESSION_MEMORY_LIMIT: int = int(os.getenv("SESSION_MEMORY_LIMIT", "20"))


settings = Settings()
