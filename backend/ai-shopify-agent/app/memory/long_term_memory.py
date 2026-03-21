from sqlalchemy.orm import Session
from app.database.repositories import CustomerRepository
from typing import Optional

class LongTermMemory:
    """
    Manages fetching and saving long-term conversational facts about a Customer via repository.
    """
    def __init__(self, db_session: Session):
        self.db = db_session
        self.customer_repo = CustomerRepository(db_session)

    def get_customer_facts(self, shopify_customer_id: str) -> Optional[str]:
        """
        Retrieves the long term memory string for a specific customer.
        Returns the facts or None if the customer isn't in our DB yet.
        """
        customer = self.customer_repo.get_by_shopify_id(shopify_customer_id)
        return customer.long_term_memory if customer else None

    def update_customer_facts(self, shopify_customer_id: str, new_fact: str):
        """
        Appends a new observational fact to the customer's long_term_memory field via repository.
        Creates the customer record locally if they don't exist yet.
        """
        customer = self.customer_repo.get_by_shopify_id(shopify_customer_id)
        
        if not customer:
            # Create a placeholder if this is the first interaction
            customer = self.customer_repo.create(
                shopify_customer_id=shopify_customer_id
            )
            current_facts = f"- {new_fact}\n"
        else:
            current_facts = customer.long_term_memory or ""
            # Avoid duplicating the same fact 
            if new_fact not in current_facts:
                current_facts = f"{current_facts.strip()}\n- {new_fact}"
        
        self.customer_repo.update_long_term_memory(customer.id, current_facts)
