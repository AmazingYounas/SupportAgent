"""
Shared FastAPI dependencies used across API modules.
"""
import logging
from typing import Generator, Optional

from sqlalchemy.orm import Session

from app.database.connection import get_db

logger = logging.getLogger(__name__)


def get_db_optional() -> Generator[Optional[Session], None, None]:
    """Yield a DB session, or None if the database is unavailable."""
    try:
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    except Exception as e:
        logger.warning("[Database] Not available: %s", e)
        yield None
