from fastapi import APIRouter, Depends, HTTPException, WebSocket, Request
from sqlalchemy.orm import Session
from typing import Dict, Optional
from collections import OrderedDict
import asyncio
import json
import logging
import traceback
import hmac
import hashlib
import base64

from app.config import settings
from app.api.schemas import ChatRequest, ChatResponse, WebhookRequest
from app.api.deps import get_db_optional
from app.agent.agent import SupportAgent
from app.memory.session_memory import SessionMemory
from app.database.repositories import ConversationRepository
from app.api.voice_duplex import router as duplex_router, voice_duplex_endpoint

logger = logging.getLogger(__name__)
router = APIRouter()


# ------------------------------------------------------------------ #
#  Session store — bounded LRU with per-session locking              #
# ------------------------------------------------------------------ #

_active_sessions: Dict[str, SessionMemory] = OrderedDict()
_session_locks: "OrderedDict[str, asyncio.Lock]" = OrderedDict()
_store_lock = asyncio.Lock()   # protects mutations of _active_sessions / _session_locks
MAX_SESSIONS = settings.MAX_ACTIVE_SESSIONS
MAX_SESSION_LOCKS = settings.MAX_SESSION_LOCKS


async def _get_session(session_id: str) -> tuple[SessionMemory, asyncio.Lock]:
    """
    FIXED: Prevent TOCTOU race by never evicting locks.
    Atomically return (or create) the SessionMemory and its asyncio.Lock.
    """
    async with _store_lock:
        if session_id not in _active_sessions:
            if len(_active_sessions) >= MAX_SESSIONS:
                evicted_id, _ = _active_sessions.popitem(last=False)
                # FIXED: Never evict locks, only evict memory
                # _session_locks.pop(evicted_id, None)  ← REMOVED
            _active_sessions[session_id] = SessionMemory()
        else:
            _active_sessions.move_to_end(session_id)
        
        # Create lock if missing.
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        else:
            _session_locks.move_to_end(session_id)
        
        # Bounded lock-store cleanup:
        # remove oldest locks only when they are not active sessions and unlocked.
        if len(_session_locks) > MAX_SESSION_LOCKS:
            removable = []
            for sid, lock in _session_locks.items():
                if sid in _active_sessions:
                    continue
                if lock.locked():
                    continue
                removable.append(sid)
                if len(_session_locks) - len(removable) <= MAX_SESSION_LOCKS:
                    break
            for sid in removable:
                _session_locks.pop(sid, None)
        
        session_memory = _active_sessions[session_id]
        session_lock = _session_locks[session_id]
        
        return session_memory, session_lock


def _restore_session_from_db(session_id: str, session_memory: SessionMemory, db: Optional[Session]) -> None:
    """
    Fix 4: If the session is empty (new in-memory) and DB is available,
    restore conversation history from the last persisted state.
    Called once per session on first access after a server restart.
    """
    if db is None:
        return
    # Only restore if the session has no messages yet (i.e., just created)
    if session_memory._messages:
        return
    try:
        repo = ConversationRepository(db)
        conversation = repo.get_by_session_key(session_id)
        if conversation and conversation.history:
            session_memory.restore_from(conversation.history)
            logger.info(f"[Session] Restored {len(conversation.history)} messages for session {session_id}")
    except Exception as e:
        logger.warning(f"[Session] Could not restore session {session_id} from DB: {e}")


def _persist_session_to_db(session_id: str, session_memory: SessionMemory, db: Optional[Session]) -> None:
    """
    Fix 4: Persist the current session history to DB after each turn.
    Silently skips if DB is unavailable.
    """
    if db is None:
        return
    try:
        repo = ConversationRepository(db)
        history = session_memory.serialize()
        if history:
            repo.upsert_by_session_key(session_id, history)
    except Exception as e:
        logger.warning(f"[Session] Could not persist session {session_id} to DB: {e}")


# ------------------------------------------------------------------ #
#  1.  Text Chat                                                       #
# ------------------------------------------------------------------ #

@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db_optional)):
    """Standard HTTP text chat."""
    agent = None
    try:
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(request.message) > 5000:
            raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")

        session_memory, session_lock = await _get_session(request.session_id)
        _restore_session_from_db(request.session_id, session_memory, db)
        agent = SupportAgent(db)

        # Per-session lock — only serializes concurrent requests for the SAME session
        async with session_lock:
            response_text, _ = await agent.chat_text(
                user_message=request.message,
                session_memory=session_memory,
                customer_id=request.shopify_customer_id,
            )

        _persist_session_to_db(request.session_id, session_memory, db)
        return ChatResponse(response=response_text, session_id=request.session_id)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[Chat] Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Chat] Unexpected error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="I'm having trouble processing your request right now. Please try again in a moment.",
        )
    finally:
        # FIX 4: Always cleanup agent resources
        if agent:
            await agent.aclose()


# ------------------------------------------------------------------ #
#  2.  Shopify Webhook                                                 #
# ------------------------------------------------------------------ #

@router.post("/api/webhooks/shopify")
async def handle_shopify_webhook(raw_request: Request, db: Session = Depends(get_db_optional)):
    """
    Receives forwarded webhooks from the Remix app.
    Raw body is read before any JSON parsing so HMAC verification works correctly.
    """
    try:
        raw_body = await raw_request.body()
        hmac_header = raw_request.headers.get("X-Shopify-Hmac-Sha256")

        if not hmac_header:
            raise HTTPException(status_code=401, detail="Missing HMAC header")

        calculated_hmac = base64.b64encode(
            hmac.new(
                settings.SHOPIFY_API_SECRET.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        if not hmac.compare_digest(calculated_hmac, hmac_header):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        topic = raw_request.headers.get("X-Shopify-Topic", "")

        if topic == "orders/create" or payload.get("topic") == "ORDERS_CREATE":
            logger.info(f"[Webhook] Order event received — ID: {payload.get('id')}")

        return {"status": "received", "topic": topic}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Webhook] Processing error: {str(e)}")
        # Raise 500 so Shopify retries the delivery (200 = silent data loss)
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# ------------------------------------------------------------------ #
#  3.  Voice WebSocket — realtime duplex only (aliases + main route)  #
# ------------------------------------------------------------------ #

router.include_router(duplex_router)


@router.websocket("/ws/voice/simple/{session_id}")
@router.websocket("/ws/voice/{session_id}")
async def voice_websocket_aliases(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db_optional),
):
    """Legacy URL shapes; same behavior as /ws/voice/duplex/{session_id}."""
    await voice_duplex_endpoint(websocket, session_id, db)
