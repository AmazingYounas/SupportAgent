from sqlalchemy import text
from app.database.connection import engine, Base
# Import models so Base.metadata.create_all recognizes them
from app.database import models

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
        # Add session_key column to conversations (added for Fix 4 — session persistence)
        if db_url.startswith("sqlite"):
            try:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN session_key VARCHAR UNIQUE"))
                conn.commit()
                print("Migration applied: conversations.session_key")
            except Exception:
                pass  # Column already exists
        else:
            # PostgreSQL / MySQL
            try:
                conn.execute(text(
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS "
                    "session_key VARCHAR UNIQUE"
                ))
                conn.commit()
                print("Migration applied: conversations.session_key")
            except Exception:
                pass


if __name__ == "__main__":
    init_db()
