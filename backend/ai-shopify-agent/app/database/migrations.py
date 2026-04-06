import logging
from sqlalchemy import text
from app.database.connection import engine, Base
# Import models so Base.metadata.create_all recognizes them
from app.database import models
 
logger = logging.getLogger(__name__)

def init_db():
    """
    Initialize the database by creating all tables defined in `models.py`.
    This serves as a lightweight migration approach for the initial setup.
    Also applies any additive column migrations for existing databases.
    """
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    _apply_migrations()
    print("Database tables created successfully.")


def _apply_migrations():
    """
    Additive migrations for existing databases.
    Each block is idempotent — safe to run on every startup.
    """
    db_url = str(engine.url)
    with engine.connect() as conn:
        # Add session_key column to conversations (added for session persistence)
        try:
            if db_url.startswith("sqlite"):
                result = conn.execute(text("PRAGMA table_info(conversations)")).fetchall()
                existing_columns = {row[1] for row in result}
                if "session_key" not in existing_columns:
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN session_key VARCHAR"))
                    conn.execute(
                        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_conversations_session_key ON conversations (session_key)")
                    )
                    conn.commit()
                    print("Migration applied: conversations.session_key")
            else:
                exists_query = text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'conversations' AND column_name = 'session_key'"
                )
                exists = conn.execute(exists_query).first() is not None
                if not exists:
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN session_key VARCHAR"))
                    conn.execute(text("CREATE UNIQUE INDEX ix_conversations_session_key ON conversations (session_key)"))
                    conn.commit()
                    print("Migration applied: conversations.session_key")
        except Exception as e:
            logger.warning("Migration check/apply failed for conversations.session_key: %s", e)


if __name__ == "__main__":
    init_db()
