"""
Repository Layer: Handles all direct database operations.
Services should call repositories instead of directly accessing the database.
"""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database.models import Customer, Order, Conversation, OrderStatus


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
               history: list = None) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            customer_id=customer_id,
            linked_order_id=linked_order_id,
            history=history or []
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
    
    def add_summary(self, conversation_id: int, summary: str) -> Conversation:
        """Add summary to conversation."""
        conversation = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conversation:
            conversation.summary = summary
            self.db.commit()
            self.db.refresh(conversation)
        return conversation

    def get_by_session_key(self, session_key: str) -> Optional[Conversation]:
        """Look up a conversation by its WebSocket/chat session key."""
        try:
            return self.db.query(Conversation).filter(
                Conversation.session_key == session_key
            ).first()
        except Exception:
            # session_key column may not exist on older DBs — fail gracefully
            return None

    def upsert_by_session_key(self, session_key: str, history: list) -> Optional[Conversation]:
        """
        Create or update a Conversation row keyed by session_key.
        Used to persist SessionMemory across server restarts.
        Returns None silently if the column doesn't exist yet (old DB).
        """
        try:
            conversation = self.get_by_session_key(session_key)
            if conversation:
                conversation.history = history
                self.db.commit()
                self.db.refresh(conversation)
            else:
                conversation = Conversation(session_key=session_key, history=history)
                self.db.add(conversation)
                self.db.commit()
                self.db.refresh(conversation)
            return conversation
        except Exception:
            self.db.rollback()
            return None
