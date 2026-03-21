import asyncio
import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# Module-level shared client — one connection pool for all ShopifyService instances.
# Limits: 20 total connections, 10 per host (Shopify's recommended ceiling).
_shared_client: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
    """Return the shared httpx client, creating it lazily on first use."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_client


class ShopifyService:
    """
    Standardized async REST API wrapper for Shopify.
    Uses a shared httpx.AsyncClient connection pool to avoid creating/destroying
    a new client on every request (which caused latency spikes under load).
    """

    def __init__(self):
        self.shop_url = settings.SHOPIFY_SHOP_URL.strip("/")
        self.api_version = settings.SHOPIFY_API_VERSION
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": settings.SHOPIFY_API_SECRET
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Async base method to execute Shopify API calls with retry logic and exponential backoff."""

        url = f"https://{self.shop_url}/admin/api/{self.api_version}/{endpoint.lstrip('/')}"

        retry_count = 0
        backoff_time = 1

        client = _get_client()
        while retry_count < max_retries:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data,
                    params=params,
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", backoff_time))
                    logger.warning(f"[Shopify] Rate limited, retrying after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    retry_count += 1
                    continue

                # Handle service unavailable (503)
                if response.status_code == 503:
                    logger.warning(f"[Shopify] Service unavailable, retry {retry_count + 1}/{max_retries}")
                    await asyncio.sleep(backoff_time)
                    retry_count += 1
                    backoff_time *= 2
                    continue

                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if response.text and content_type.startswith("application/json"):
                    return response.json()
                return {"status": "success", "status_code": response.status_code}

            except httpx.TimeoutException:
                retry_count += 1
                logger.error(f"[Shopify] Request timeout (attempt {retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    return {
                        "error": True,
                        "message": "The store is taking too long to respond. Please try again later.",
                        "user_friendly": True
                    }
                await asyncio.sleep(backoff_time)
                backoff_time *= 2

            except httpx.ConnectError:
                retry_count += 1
                logger.error(f"[Shopify] Connection error (attempt {retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    return {
                        "error": True,
                        "message": "Unable to connect to the store. Please check your internet connection.",
                        "user_friendly": True
                    }
                await asyncio.sleep(backoff_time)
                backoff_time *= 2

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if 400 <= status_code < 500 and status_code != 429:
                    error_detail = ""
                    try:
                        error_detail = e.response.json() if e.response.text else ""
                    except Exception:
                        pass
                    logger.error(f"[Shopify] Client error {status_code}: {error_detail}")
                    return {
                        "error": True,
                        "message": self._get_user_friendly_error(status_code, error_detail),
                        "user_friendly": True
                    }

                retry_count += 1
                logger.error(f"[Shopify] Server error {status_code} (attempt {retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    return {
                        "error": True,
                        "message": "The store is experiencing technical difficulties. Please try again later.",
                        "user_friendly": True
                    }
                await asyncio.sleep(backoff_time)
                backoff_time *= 2

            except Exception as e:
                logger.error(f"[Shopify] Unexpected error: {str(e)}")
                return {
                    "error": True,
                    "message": "An unexpected error occurred. Please try again.",
                    "user_friendly": True
                }

        return {
            "error": True,
            "message": "Maximum retry attempts reached. Please try again later.",
            "user_friendly": True
        }

    def _get_user_friendly_error(self, status_code: int, error_detail: Any) -> str:
        """Convert technical errors to user-friendly messages."""
        error_messages = {
            400: "The request was invalid. Please check the information and try again.",
            401: "Authentication failed. Please contact support.",
            403: "You don't have permission to perform this action.",
            404: "The requested item was not found in the store.",
            422: "The data provided is invalid. Please check and try again.",
        }
        return error_messages.get(status_code, f"An error occurred (Code: {status_code}). Please try again.")

    # -------------------------------------------------------------
    # Order Interactions
    # -------------------------------------------------------------

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        return await self._make_request("GET", f"/orders/{order_id}.json")

    async def cancel_order(self, order_id: str, reason: str = "customer") -> Dict[str, Any]:
        """Cancels an order in Shopify."""
        data = {"reason": reason}
        return await self._make_request("POST", f"/orders/{order_id}/cancel.json", data=data)

    # -------------------------------------------------------------
    # Customer Interactions
    # -------------------------------------------------------------

    async def get_customer(self, customer_id: str) -> Dict[str, Any]:
        return await self._make_request("GET", f"/customers/{customer_id}.json")

    async def search_customer_by_email(self, email: str) -> Dict[str, Any]:
        return await self._make_request("GET", "/customers/search.json", params={"query": f"email:{email}"})

    # -------------------------------------------------------------
    # Product/Inventory Interactions
    # -------------------------------------------------------------

    async def search_products(self, query: str) -> Dict[str, Any]:
        return await self._make_request("GET", "/products.json", params={"title": query})

    async def get_product(self, product_id: str) -> Dict[str, Any]:
        return await self._make_request("GET", f"/products/{product_id}.json")
