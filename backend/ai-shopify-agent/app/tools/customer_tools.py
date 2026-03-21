from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.memory.long_term_memory import LongTermMemory
from typing import Optional, Type

#
# 1. Update Customer Preferences Tool
#
class UpdateCustomerFactsInput(BaseModel):
    shopify_customer_id: str = Field(description="The unique Shopify ID for the customer. Found via context.")
    new_fact: str = Field(description="A concise, declarative sentence capturing a preference, sentiment, or fact. e.g. 'Prefers extra padding in shipping boxes' or 'Was extremely frustrated by a delay in March 2024'.")

class UpdateCustomerFactsTool(BaseTool):
    name: str = "update_customer_facts"
    description: str = (
        "Appends a new observational fact or preference regarding a customer to their long-term memory record."
        "Use this organically during conversation to remember details."
    )
    args_schema: Type[BaseModel] = UpdateCustomerFactsInput
    long_term_memory: Optional[LongTermMemory] = None

    def _run(self, shopify_customer_id: str, new_fact: str) -> str:
        if not self.long_term_memory:
            return "Memory not available in this session."
            
        self.long_term_memory.update_customer_facts(shopify_customer_id, new_fact)
        return f"Successfully recorded the fact '{new_fact}' for customer ID: {shopify_customer_id}."

#
# 2. Retrieve Customer Profile
#
class GetCustomerFactsInput(BaseModel):
    shopify_customer_id: str = Field(description="The unique Shopify ID for the customer.")

class GetCustomerFactsTool(BaseTool):
    name: str = "get_customer_facts"
    description: str = "Retrieves previously stored facts and long-term memory context about a customer."
    args_schema: Type[BaseModel] = GetCustomerFactsInput
    long_term_memory: Optional[LongTermMemory] = None

    def _run(self, shopify_customer_id: str) -> str:
        if not self.long_term_memory:
            return "No prior memory available for this customer."
            
        facts = self.long_term_memory.get_customer_facts(shopify_customer_id)
        if not facts:
            return f"No prior memory found for customer ID: {shopify_customer_id}."
            
        return f"Known Details:\n{facts}"
