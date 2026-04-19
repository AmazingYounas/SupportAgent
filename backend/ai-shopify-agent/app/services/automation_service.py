import logging
from sqlalchemy.orm import Session
from app.database.repositories import CampaignRepository, ConversationRepository, CustomerRepository
from app.database.models import CallDirection, CallStatus

logger = logging.getLogger(__name__)

class AutomationService:
    def __init__(self, db: Session):
        self.db = db
        self.campaign_repo = CampaignRepository(db)
        self.conv_repo = ConversationRepository(db)
        self.customer_repo = CustomerRepository(db)

    async def process_webhook(self, topic: str, payload: dict):
        """
        Decide if a webhook event triggers an outbound call.
        """
        logger.info(f"[Automation] Processing webhook topic: {topic}")
        
        # 1. Find active campaigns for this topic
        active_campaigns = self.campaign_repo.get_active_by_event(topic)
        if not active_campaigns:
            logger.info(f"[Automation] No active campaigns for {topic}")
            return

        # 2. Extract customer info
        phone = payload.get("phone") or (payload.get("customer") or {}).get("phone")
        if not phone:
            logger.warning(f"[Automation] No phone number found in payload for {topic}")
            return

        customer_name = (payload.get("customer") or {}).get("first_name", "Valued Customer")
        
        # 3. Extract Order Items for the script
        line_items = payload.get("line_items", [])
        product_list = ", ".join([item.get("title") for item in line_items[:3]])
        if len(line_items) > 3:
            product_list += " and other items"

        # 4. For each campaign, queue an outbound call
        for campaign in active_campaigns:
            logger.info(f"[Automation] Triggering Outbound Call for campaign: {campaign.name}")
            
            # Upsert customer
            customer = self.customer_repo.get_by_shopify_id(str(payload.get("customer", {}).get("id", "")))
            if not customer:
                customer = self.customer_repo.create(
                    shopify_customer_id=str(payload.get("customer", {}).get("id", "")),
                    name=customer_name,
                    phone=phone
                )

            # Build the custom script instruction
            outbound_goal = (
                f"STRICTNESS: Do not offer help or chat. Stick to this script exactly.\n"
                f"OPENING: 'Hello {customer_name}, I'm Alex from Editorsbay. I'm calling to confirm your recent order for the {product_list}. Do you confirm you placed this order?'\n"
                f"CLOSING: 'Great, thank you! Your order is all set. Reach out to us at this number if you need anything. Have a good one!'\n"
                f"ACTION: Say '[HANGUP]' exactly after the closing."
            )

            # Generate a unique session key for the simulator
            import time
            session_key = f"out-order-{payload.get('id')}-{int(time.time())}"

            # Create an OUTBOUND conversation record in PENDING status
            self.conv_repo.create(
                customer_id=customer.id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.PENDING,
                session_key=session_key,
                history=[{"role": "system", "content": f"OUTBOUND GOAL: {outbound_goal}"}],
                linked_order_id=payload.get("id")
            )
            
            logger.info(f"[Automation] Conversation queued for {customer_name} ({phone}) with goal: {outbound_goal[:50]}...")
