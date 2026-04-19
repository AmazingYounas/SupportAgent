import enum
from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.connection import Base


class OrderStatus(str, enum.Enum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    UPDATED = "UPDATED"


class CallDirection(str, enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class CallStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


class Customer(Base):
    """
    Represents a customer in the database.
    Stores basic info mapping to Shopify and long-term memory for AI context.
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    shopify_customer_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    
    # Store persistent AI facts globally about this user
    # e.g., "Prefers fast shipping", "Is a VIP"
    long_term_memory = Column(Text, nullable=True) 

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    orders = relationship("Order", back_populates="customer")
    conversations = relationship("Conversation", back_populates="customer")


class Order(Base):
    """
    Tracks local state of Shopify orders managed by the AI Agent.
    """
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    shopify_order_id = Column(String, unique=True, index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING_CONFIRMATION, nullable=False)
    total_price = Column(String, nullable=True)
    
    # Snapshot of the last known order data from Shopify to minimize API calls
    order_data_snapshot = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("Customer", back_populates="orders")


class Conversation(Base):
    """
    Represents an ongoing or past interaction thread between Customer and AI.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    
    # Metadata for Dashboard
    direction = Column(Enum(CallDirection), default=CallDirection.INBOUND, nullable=False)
    status = Column(Enum(CallStatus), default=CallStatus.ACTIVE, nullable=False)
    
    # Optional explicitly linked order being discussed
    linked_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    # Keep track of the actual dialog history
    history = Column(JSON, default=list, nullable=False)
    
    # AI Analysis Results
    summary = Column(Text, nullable=True)
    outcome = Column(String, nullable=True) # e.g., "SOLVED", "CANCELLED", "NO_ANSWER"
    
    # Stats
    duration_seconds = Column(Integer, default=0)
    
    # WebSocket/chat session key
    session_key = Column(String, unique=True, index=True, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("Customer", back_populates="conversations")


class Campaign(Base):
    """
    Ruleset for automated outbound calls.
    Example: Trigger call when 'orders/create' happens.
    """
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    trigger_event = Column(String, nullable=False) # e.g., "orders/create"
    active = Column(Integer, default=1) # 1 for True, 0 for False (standard SQLite pattern)
    
    # Specific goal for the AI in this campaign
    goal_prompt = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentSettings(Base):
    """
    Global configuration for the Voice Agent.
    """
    __tablename__ = "agent_settings"

    id = Column(Integer, primary_key=True, index=True)
    voice_id = Column(String, nullable=True)
    base_personality = Column(Text, nullable=True)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
