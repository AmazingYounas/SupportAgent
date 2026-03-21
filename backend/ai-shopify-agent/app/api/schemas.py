from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    """
    Standard text payload for generic chat interactions.
    """
    message: str
    session_id: str
    shopify_customer_id: Optional[str] = None

class ChatResponse(BaseModel):
    """
    Response encapsulation for text-based chat.
    """
    response: str
    session_id: str

class WebhookRequest(BaseModel):
    """
    Basic structure expected from the Shopify `ORDERS_CREATE` webhook payload forwarded by Remix.
    """
    shop: str
    topic: str
    payload: dict
