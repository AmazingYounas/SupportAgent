from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.services.order_service import OrderService
from typing import Optional, Type, Dict, Any

#
# 1. Check Order Status Tool
#
class CheckOrderStatusInput(BaseModel):
    shopify_order_id: str = Field(description="The unique Shopify ID for the order to check")

class CheckOrderStatusTool(BaseTool):
    name: str = "check_order_status"
    description: str = "Retrieves the current status and local DB state of an existing Shopify Order."
    args_schema: Type[BaseModel] = CheckOrderStatusInput
    order_service: Optional[OrderService] = None

    def _run(self, shopify_order_id: str) -> str:
        """Sync fallback — not used when async is available."""
        return "Error: Use _arun for async tool invocation."

    async def _arun(self, shopify_order_id: str) -> str:
        if not self.order_service:
            return "Error: Order Service not initialized in tool context."

        success, message, data = await self.order_service.get_order_details(shopify_order_id)
        if not success:
            return f"Order not found or an error occurred: {message}"

        # Include customer email prominently so the LLM can verify identity
        customer = data.get('customer', {})
        customer_email = customer.get('email', 'no email on file')

        formatted_output = f"Order ID: {shopify_order_id}\n"
        formatted_output += f"Customer Email on Order: {customer_email}\n"
        formatted_output += f"Customer Name on Order: {customer.get('first_name', '')} {customer.get('last_name', '')}\n"
        formatted_output += f"Total Price: {data.get('total_price')} {data.get('currency')}\n"

        financial = data.get('financial_status', 'pending')
        fulfillment = data.get('fulfillment_status') or 'unfulfilled'
        formatted_output += f"Payment Status: {financial}\n"
        formatted_output += f"Fulfillment Status: {fulfillment}\n"

        # Include tracking if available
        fulfillments = data.get('fulfillments', [])
        if fulfillments:
            tracking = fulfillments[0].get('tracking_number')
            tracking_company = fulfillments[0].get('tracking_company', '')
            if tracking:
                formatted_output += f"Tracking: {tracking_company} {tracking}\n"

        formatted_output += (
            "\nIMPORTANT: Before sharing any of the above details with the customer, "
            "verify that the email they provided matches 'Customer Email on Order' above. "
            "If it does not match, do NOT share this data."
        )

        return formatted_output

#
# 2. Cancel Order Tool
#
class CancelOrderInput(BaseModel):
    shopify_order_id: str = Field(description="The unique Shopify ID for the order to cancel")
    reason: str = Field(
        default="customer",
        description="The reason for cancellation. Valid enum values are usually 'customer', 'inventory', 'fraud', 'declined', or 'other'."
    )

class CancelOrderTool(BaseTool):
    name: str = "cancel_order"
    description: str = (
        "Cancels an order directly securely in Shopify and updates the local database. "
        "WARNING: You should confirm with the user before invoking this action."
    )
    args_schema: Type[BaseModel] = CancelOrderInput
    order_service: Optional[OrderService] = None

    def _run(self, shopify_order_id: str, reason: str = "customer") -> str:
        """Sync fallback — not used when async is available."""
        return "Error: Use _arun for async tool invocation."

    async def _arun(self, shopify_order_id: str, reason: str = "customer") -> str:
        if not self.order_service:
            return "Error: Order Service not initialized in tool context."

        success, message = await self.order_service.cancel_order(shopify_order_id, reason)
        return message
