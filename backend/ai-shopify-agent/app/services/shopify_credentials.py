import sqlite3
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Configurable path to the Shopify App's database
# Standard structure: SupportAgent/backend/ai-shopify-agent/app/services/shopify_credentials.py
# Target: SupportAgent/calling-support-agent/prisma/dev.sqlite
SHOPIFY_APP_DB_PATH = os.getenv(
    "SHOPIFY_APP_DB_PATH", 
    os.path.join(os.path.dirname(__file__), "../../../../calling-support-agent/prisma/dev.sqlite")
)

def get_shopify_creds() -> Tuple[Optional[str], Optional[str]]:
    """
    Dynamically discover Shopify credentials from the Shopify App's SQLite database.
    Looks for the 'offline_' session for the current store.
    
    Returns:
        (shop_url, access_token) or (None, None)
    """
    db_path = os.path.abspath(SHOPIFY_APP_DB_PATH)
    
    if not os.path.exists(db_path):
        logger.debug(f"[Shopify:Creds] ❌ Database not found at {db_path}")
        return None, None
    
    try:
        # Use a context manager to ensure connection is closed
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Query for the offline session (standard pattern for background/external workers)
            # We take the most recently updated one if multiple exist (unlikely in dev)
            query = """
                SELECT shop, accessToken FROM Session 
                WHERE id LIKE 'offline_%' 
                ORDER BY id DESC LIMIT 1
            """
            cursor.execute(query)
            row = cursor.fetchone()
            
            if row:
                shop = row["shop"]
                token = row["accessToken"]
                logger.info(f"[Shopify:Creds] ✅ Dynamically loaded credentials for {shop}")
                return shop, token
            
            # Fallback: if no offline session, try any session
            logger.debug("[Shopify:Creds] ⚠️ No offline session found, checking online sessions...")
            cursor.execute("SELECT shop, accessToken FROM Session LIMIT 1")
            row = cursor.fetchone()
            if row:
                return row["shop"], row["accessToken"]
                
    except Exception as e:
        logger.error(f"[Shopify:Creds] ❌ Failed to read credentials from {db_path}: {e}")
    
    return None, None

if __name__ == "__main__":
    # Test script
    logging.basicConfig(level=logging.INFO)
    shop, token = get_shopify_creds()
    if shop:
        print(f"SUCCESS: Found credentials for {shop}")
        print(f"TOKEN: {token[:10]}...")
    else:
        print("FAILURE: No credentials found.")
