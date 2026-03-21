from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.services.shopify_service import ShopifyService
from typing import Optional, Type

class SearchProductsInput(BaseModel):
    query: str = Field(description="The generic title or keyword to search for in the Shopify store catalog.")

class SearchProductsTool(BaseTool):
    name: str = "search_products"
    description: str = "Searches the Shopify store inventory for a product matching the query string."
    args_schema: Type[BaseModel] = SearchProductsInput
    shopify_service: Optional[ShopifyService] = None

    def _run(self, query: str) -> str:
        """Sync fallback — not used when async is available."""
        return "Error: Use _arun for async tool invocation."

    async def _arun(self, query: str) -> str:
        """Async product search — non-blocking, safe for concurrent sessions."""
        if not self.shopify_service:
            return "Error: Shopify Service not initialized."

        response = await self.shopify_service.search_products(query)
        if response.get("error"):
            return f"Failed to search: {response.get('message')}"

        products = response.get("products", [])
        if not products:
            return f"No products found matching '{query}'"

        output = f"Found {len(products)} products:\n"
        for p in products[:5]:  # Cap at 5 to avoid token overflow
            output += f"- {p.get('title')} (ID: {p.get('id')}) | Status: {p.get('status')} | Tags: {p.get('tags')}\n"
            variants = p.get('variants', [])
            if variants:
                output += f"  Price: {variants[0].get('price')} | Inventory: {sum(v.get('inventory_quantity', 0) for v in variants)}\n"

        return output
