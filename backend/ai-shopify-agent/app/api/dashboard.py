from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database.connection import get_db
from app.database.repositories import ConversationRepository, CampaignRepository, AgentSettingsRepository
from app.database.models import Conversation, Campaign, AgentSettings, CallDirection, CallStatus

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# --- Pydantic Schemas ---

class HistoryItem(BaseModel):
    id: int
    customer_name: Optional[str] = None
    session_key: Optional[str] = None
    direction: str
    status: str
    outcome: Optional[str] = None
    summary: Optional[str] = None
    duration_seconds: int
    created_at: datetime

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_calls: int
    inbound_count: int
    outbound_count: int
    active_count: int
    resolution_rate: float

class CampaignSchema(BaseModel):
    id: Optional[int] = None
    name: str
    trigger_event: str
    active: int
    goal_prompt: Optional[str] = None

class SettingsSchema(BaseModel):
    voice_id: Optional[str] = None
    base_personality: Optional[str] = None

# --- Endpoints ---

@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Conversation).count()
    inbound = db.query(Conversation).filter(Conversation.direction == CallDirection.INBOUND).count()
    outbound = db.query(Conversation).filter(Conversation.direction == CallDirection.OUTBOUND).count()
    active = db.query(Conversation).filter(Conversation.status == CallStatus.ACTIVE).count()
    
    # Simple resolution rate: % of completed calls with an outcome
    resolved = db.query(Conversation).filter(Conversation.outcome != None).count()
    rate = (resolved / total * 100) if total > 0 else 0
    
    return {
        "total_calls": total,
        "inbound_count": inbound,
        "outbound_count": outbound,
        "active_count": active,
        "resolution_rate": round(rate, 1)
    }

@router.get("/history", response_model=List[HistoryItem])
def get_history(limit: int = 50, db: Session = Depends(get_db)):
    repo = ConversationRepository(db)
    calls = repo.get_dashboard_history(limit=limit)
    
    result = []
    for c in calls:
        name = c.customer.name if c.customer else "Unknown"
        result.append({
            "id": c.id,
            "customer_name": name,
            "session_key": c.session_key,
            "direction": c.direction,
            "status": c.status,
            "outcome": c.outcome,
            "summary": c.summary,
            "duration_seconds": c.duration_seconds,
            "created_at": c.created_at
        })
    return result

@router.get("/active", response_model=List[HistoryItem])
def get_active(db: Session = Depends(get_db)):
    repo = ConversationRepository(db)
    # Include both ACTIVE and PENDING for the live monitor
    calls = db.query(Conversation).filter(
        Conversation.status.in_([CallStatus.ACTIVE, CallStatus.PENDING])
    ).all()
    
    result = []
    for c in calls:
        name = c.customer.name if c.customer else "Unknown"
        result.append({
            "id": c.id,
            "customer_name": name,
            "session_key": c.session_key,
            "direction": c.direction,
            "status": c.status,
            "outcome": c.outcome,
            "summary": c.summary,
            "duration_seconds": c.duration_seconds,
            "created_at": c.created_at
        })
    return result

@router.get("/campaigns", response_model=List[CampaignSchema])
def get_campaigns(db: Session = Depends(get_db)):
    repo = CampaignRepository(db)
    return repo.get_all()

@router.post("/campaigns", response_model=CampaignSchema)
def create_campaign(campaign: CampaignSchema, db: Session = Depends(get_db)):
    repo = CampaignRepository(db)
    return repo.create(name=campaign.name, trigger_event=campaign.trigger_event, goal_prompt=campaign.goal_prompt)

@router.get("/settings", response_model=SettingsSchema)
def get_settings(db: Session = Depends(get_db)):
    repo = AgentSettingsRepository(db)
    settings = repo.get_settings()
    if not settings:
        return {"voice_id": "", "base_personality": ""}
    return settings

@router.post("/settings", response_model=SettingsSchema)
def update_settings(settings: SettingsSchema, db: Session = Depends(get_db)):
    repo = AgentSettingsRepository(db)
    return repo.update_settings(voice_id=settings.voice_id, base_personality=settings.base_personality)
