"""
Repository Layer: Handles all direct database operations.
Services should call repositories instead of directly accessing the database.
"""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database.models import Customer, Order, Conversation, OrderStatus, Campaign, AgentSettings, CallStatus, CallDirection


class CustomerRepository:
    """Repository for Customer database operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_shopify_id(self, shopify_customer_id: str) -> Optional[Customer]:
        """Get customer by Shopify ID."""
        return self.db.query(Customer).filter(
            Customer.shopify_customer_id == shopify_customer_id
        ).first()
    
    def get_by_email(self, email: str) -> Optional[Customer]:
        """Get customer by email."""
        return self.db.query(Customer).filter(Customer.email == email).first()
    
    def create(self, shopify_customer_id: str, email: str = None, 
               phone: str = None, name: str = None) -> Customer:
        """Create a new customer."""
        customer = Customer(
            shopify_customer_id=shopify_customer_id,
            email=email,
            phone=phone,
            name=name
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer
    
    def update_long_term_memory(self, customer_id: int, memory_text: str) -> Customer:
        """Update customer's long-term memory."""
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if customer:
            customer.long_term_memory = memory_text
            self.db.commit()
            self.db.refresh(customer)
        return customer


class OrderRepository:
    """Repository for Order database operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_shopify_id(self, shopify_order_id: str) -> Optional[Order]:
        """Get order by Shopify ID."""
        return self.db.query(Order).filter(
            Order.shopify_order_id == shopify_order_id
        ).first()
    
    def create(self, shopify_order_id: str, customer_id: int, 
               status: OrderStatus, total_price: str = None, 
               order_data_snapshot: dict = None) -> Order:
        """Create a new order."""
        order = Order(
            shopify_order_id=shopify_order_id,
            customer_id=customer_id,
            status=status,
            total_price=total_price,
            order_data_snapshot=order_data_snapshot
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def update_status(self, order_id: int, status: OrderStatus) -> Order:
        """Update order status."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.status = status
            self.db.commit()
            self.db.refresh(order)
        return order
    
    def update_snapshot(self, order_id: int, snapshot: dict) -> Order:
        """Update order data snapshot."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.order_data_snapshot = snapshot
            self.db.commit()
            self.db.refresh(order)
        return order


class ConversationRepository:
    """Repository for Conversation database operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, customer_id: int = None, linked_order_id: int = None, 
               history: list = None, direction: CallDirection = CallDirection.INBOUND,
               status: CallStatus = CallStatus.ACTIVE, session_key: str = None) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            customer_id=customer_id,
            linked_order_id=linked_order_id,
            history=history or [],
            direction=direction,
            status=status,
            session_key=session_key
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
    
    def update_history(self, conversation_id: int, history: list) -> Conversation:
        """Update conversation history."""
        conversation = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conversation:
            conversation.history = history
            self.db.commit()
            self.db.refresh(conversation)
        return conversation
    
    def update_status(self, conversation_id: int, status: CallStatus) -> Conversation:
        """Update conversation status."""
        conversation = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conversation:
            conversation.status = status
            self.db.commit()
            self.db.refresh(conversation)
        return conversation

    def complete_conversation(self, conversation_id: int, summary: str, outcome: str = None, duration: int = 0) -> Conversation:
        """Mark conversation as completed with summary and outcome."""
        conversation = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conversation:
            conversation.status = CallStatus.COMPLETED
            conversation.summary = summary
            conversation.outcome = outcome
            conversation.duration_seconds = duration
            self.db.commit()
            self.db.refresh(conversation)
        return conversation

    def get_by_session_key(self, session_key: str) -> Optional[Conversation]:
        """Look up a conversation by its WebSocket/chat session key."""
        return self.db.query(Conversation).filter(
            Conversation.session_key == session_key
        ).first()

    def upsert_by_session_key(self, session_key: str, history: list, customer_id: int = None) -> Optional[Conversation]:
        """Create or update a Conversation row keyed by session_key."""
        conversation = self.get_by_session_key(session_key)
        if conversation:
            conversation.history = history
            # Ensure it's marked as ACTIVE once the connection starts
            if conversation.status == CallStatus.PENDING:
                conversation.status = CallStatus.ACTIVE
            if customer_id:
                conversation.customer_id = customer_id
            self.db.commit()
            self.db.refresh(conversation)
        else:
            conversation = Conversation(
                session_key=session_key, 
                history=history, 
                customer_id=customer_id,
                status=CallStatus.ACTIVE
            )
            self.db.add(conversation)
            self.db.commit()
            self.db.refresh(conversation)
        return conversation

    def get_dashboard_history(self, limit: int = 50) -> List[Conversation]:
        """Fetch historical conversations for the dashboard."""
        return self.db.query(Conversation).order_by(Conversation.created_at.desc()).limit(limit).all()

    def get_active_calls(self) -> List[Conversation]:
        """Fetch all currently active calls."""
        return self.db.query(Conversation).filter(Conversation.status == CallStatus.ACTIVE).all()


class CampaignRepository:
    """Repository for Outbound Campaign management."""
    
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Campaign]:
        return self.db.query(Campaign).all()

    def get_active_by_event(self, event: str) -> List[Campaign]:
        return self.db.query(Campaign).filter(
            Campaign.trigger_event == event,
            Campaign.active == 1
        ).all()

    def create(self, name: str, trigger_event: str, goal_prompt: str = None) -> Campaign:
        campaign = Campaign(name=name, trigger_event=trigger_event, goal_prompt=goal_prompt)
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign


class AgentSettingsRepository:
    """Repository for Global Agent Settings."""
    
    def __init__(self, db: Session):
        self.db = db

    def get_settings(self) -> Optional[AgentSettings]:
        return self.db.query(AgentSettings).first()

    def update_settings(self, voice_id: str = None, base_personality: str = None) -> AgentSettings:
        settings = self.get_settings()
        if not settings:
            settings = AgentSettings(voice_id=voice_id, base_personality=base_personality)
            self.db.add(settings)
        else:
            if voice_id:
                settings.voice_id = voice_id
            if base_personality:
                settings.base_personality = base_personality
        self.db.commit()
        self.db.refresh(settings)
        return settings
