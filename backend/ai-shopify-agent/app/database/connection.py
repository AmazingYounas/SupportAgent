from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Base class for declarative class definitions (always safe to create)
Base = declarative_base()

# Lazy engine / session — only created on first use so startup never crashes
_engine = None
_SessionLocal = None


def _get_engine():
    """Return a cached SQLAlchemy engine, creating it lazily on first call."""
    global _engine
    if _engine is None:
        connect_args = {}
        db_url = settings.DATABASE_URL
        # SQLite needs check_same_thread=False; Postgres doesn't support pool_size for NullPool
        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            _engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
        else:
            _engine = create_engine(db_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
        logger.info(f"Database engine created for: {db_url.split('@')[-1]}")  # hide credentials
    return _engine


# Keep `engine` and `SessionLocal` as module-level proxies for backwards compatibility
class _EngineProxy:
    """Thin proxy so code that does `from connection import engine` still works."""
    def __getattr__(self, name):
        return getattr(_get_engine(), name)

engine = _EngineProxy()


def _get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _SessionLocal


def get_db():
    """
    Dependency generator to yield a database session.
    Closes the session after use.
    """
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
