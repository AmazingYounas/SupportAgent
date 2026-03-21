from sqlalchemy.orm import Session
from typing import Dict, Any, Tuple, Optional
import re
import logging
from app.services.shopify_service import ShopifyService
from app.database.models import OrderStatus
from app.database.repositories import CustomerRepository, OrderRepository

logger = logging.getLogger(__name__)

class OrderService:
    """
    Business logic layer for order management.
    Coordinates between repositories, local PostgreSQL DB, and external Shopify API.
    All Shopify calls are async to avoid blocking the event loop.
    """

    def __init__(self, db_session: Optional[Session] = None):
        self.db = db_session
        self.shopify = ShopifyService()

        # Only initialize repositories if database is available
        if db_session:
            self.customer_repo = CustomerRepository(db_session)
            self.order_repo = OrderRepository(db_session)
        else:
            self.customer_repo = None
            self.order_repo = None
            logger.warning("[OrderService] Running without database - persistence disabled")

    def _validate_order_id(self, order_id: str) -> Tuple[bool, str]:
        """Validate order ID format."""
        if not order_id or not isinstance(order_id, str):
            return False, "Order ID is required"

        order_id = order_id.strip()
        if not order_id:
            return False, "Order ID cannot be empty"

        # Basic validation - Shopify order IDs are typically numeric
        if not re.match(r'^[0-9]+$', order_id):
            return False, "Invalid order ID format. Order ID should be numeric."

        return True, order_id

    def _sync_or_create_customer(self, shopify_customer_data: Dict[str, Any]):
        """Ensures the customer exists locally via repository (if database available)."""
        if not self.customer_repo:
            return None  # Database not available

        if not shopify_customer_data:
            return None

        try:
            shopify_id = str(shopify_customer_data.get("id"))
            customer = self.customer_repo.get_by_shopify_id(shopify_id)

            email = shopify_customer_data.get("email")
            if not customer and email:
                customer = self.customer_repo.get_by_email(email)

            if not customer:
                name = f"{shopify_customer_data.get('first_name', '')} {shopify_customer_data.get('last_name', '')}".strip()
                customer = self.customer_repo.create(
                    shopify_customer_id=shopify_id,
                    email=email,
                    phone=shopify_customer_data.get("phone"),
                    name=name
                )

            return customer
        except Exception as e:
            logger.error(f"[OrderService] Error syncing customer: {str(e)}")
            return None

    async def get_order_details(self, shopify_order_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Retrieves order details from Shopify and syncs via repository (if database available).
        Returns: (Success Boolean, Message, Order Data Dict)
        """
        is_valid, result = self._validate_order_id(shopify_order_id)
        if not is_valid:
            return False, result, {}

        shopify_order_id = result  # Use cleaned order ID

        # Fetch from Shopify (async)
        response = await self.shopify.get_order(shopify_order_id)

        if response.get("error"):
            error_msg = response.get("message", "Unknown error")
            if response.get("user_friendly"):
                return False, error_msg, {}
            return False, f"Unable to retrieve order: {error_msg}", {}

        order_data = response.get("order", {})

        if not order_data:
            return False, f"Order {shopify_order_id} not found in the store.", {}

        # Sync to database if available
        if self.customer_repo and self.order_repo:
            try:
                customer = self._sync_or_create_customer(order_data.get("customer", {}))

                if customer:
                    local_order = self.order_repo.get_by_shopify_id(str(shopify_order_id))
                    if not local_order:
                        status = OrderStatus.CONFIRMED if order_data.get("financial_status") == "paid" else OrderStatus.PENDING_CONFIRMATION
                        local_order = self.order_repo.create(
                            shopify_order_id=str(shopify_order_id),
                            customer_id=customer.id,
                            status=status,
                            total_price=order_data.get("total_price"),
                            order_data_snapshot=order_data
                        )
                    else:
                        local_order = self.order_repo.update_snapshot(local_order.id, order_data)
            except Exception as e:
                logger.error(f"[OrderService] Database sync error: {str(e)}")
                # Continue anyway - we have the order data from Shopify

        return True, "Order retrieved successfully.", order_data

    async def cancel_order(self, shopify_order_id: str, reason: str = "customer") -> Tuple[bool, str]:
        """
        Attempts to cancel an order via Shopify API and updates via repository (if database available).
        Returns: (Success Boolean, Message String)
        """
        is_valid, result = self._validate_order_id(shopify_order_id)
        if not is_valid:
            return False, result

        shopify_order_id = result  # Use cleaned order ID

        valid_reasons = ["customer", "inventory", "fraud", "declined", "other"]
        if reason not in valid_reasons:
            return False, f"Invalid cancellation reason. Must be one of: {', '.join(valid_reasons)}"

        # Attempt cancellation in Shopify (async)
        response = await self.shopify.cancel_order(shopify_order_id, reason)

        if response.get("error"):
            error_msg = response.get("message", "Unknown error")
            if response.get("user_friendly"):
                return False, error_msg
            return False, f"Failed to cancel order: {error_msg}"

        # Update local DB via repository (if available)
        if self.order_repo:
            try:
                local_order = self.order_repo.get_by_shopify_id(str(shopify_order_id))
                if local_order:
                    self.order_repo.update_status(local_order.id, OrderStatus.CANCELLED)
            except Exception as e:
                logger.error(f"[OrderService] Database update error: {str(e)}")
                # Continue anyway - order was cancelled in Shopify

        return True, f"Successfully cancelled order {shopify_order_id}. Reason: {reason}"
