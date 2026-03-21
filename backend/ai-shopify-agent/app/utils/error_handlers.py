"""
Comprehensive error handling utilities for the AI Agent.
"""
from typing import Callable, Any
from functools import wraps
import traceback


class AgentError(Exception):
    """Base exception for agent errors."""
    pass


class ShopifyAPIError(AgentError):
    """Raised when Shopify API calls fail."""
    pass


class ElevenLabsError(AgentError):
    """Raised when ElevenLabs API calls fail."""
    pass


class DatabaseError(AgentError):
    """Raised when database operations fail."""
    pass


class ToolExecutionError(AgentError):
    """Raised when tool execution fails."""
    pass


def safe_execute(fallback_message: str = "I apologize, but I encountered an error. Please try again."):
    """
    Decorator for safe execution with error handling and fallback.
    Returns a conversational error message instead of crashing.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except ShopifyAPIError as e:
                print(f"[ShopifyAPIError] {str(e)}")
                return f"I'm having trouble connecting to the store system right now. {fallback_message}"
            except ElevenLabsError as e:
                print(f"[ElevenLabsError] {str(e)}")
                return f"I'm experiencing voice service issues. {fallback_message}"
            except DatabaseError as e:
                print(f"[DatabaseError] {str(e)}")
                return f"I'm having trouble accessing customer information. {fallback_message}"
            except ToolExecutionError as e:
                print(f"[ToolExecutionError] {str(e)}")
                return f"I couldn't complete that action. {fallback_message}"
            except Exception as e:
                print(f"[UnexpectedError] {type(e).__name__}: {str(e)}")
                print(traceback.format_exc())
                return fallback_message
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except ShopifyAPIError as e:
                print(f"[ShopifyAPIError] {str(e)}")
                return f"I'm having trouble connecting to the store system right now. {fallback_message}"
            except ElevenLabsError as e:
                print(f"[ElevenLabsError] {str(e)}")
                return f"I'm experiencing voice service issues. {fallback_message}"
            except DatabaseError as e:
                print(f"[DatabaseError] {str(e)}")
                return f"I'm having trouble accessing customer information. {fallback_message}"
            except ToolExecutionError as e:
                print(f"[ToolExecutionError] {str(e)}")
                return f"I couldn't complete that action. {fallback_message}"
            except Exception as e:
                print(f"[UnexpectedError] {type(e).__name__}: {str(e)}")
                print(traceback.format_exc())
                return fallback_message
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def handle_shopify_error(response: dict) -> None:
    """
    Checks Shopify API response for errors and raises appropriate exception.
    """
    if response.get("error"):
        error_msg = response.get("message", "Unknown Shopify API error")
        raise ShopifyAPIError(f"Shopify API Error: {error_msg}")


def handle_elevenlabs_error(error: Exception) -> str:
    """
    Handles ElevenLabs errors and returns user-friendly message.
    """
    print(f"[ElevenLabs Error] {str(error)}")
    return "I'm having trouble with the voice service. Let me respond with text instead."


def validate_order_id(order_id: str) -> bool:
    """
    Validates order ID format.
    """
    if not order_id or not isinstance(order_id, str):
        return False
    # Basic validation - can be enhanced
    return len(order_id) > 0


def validate_customer_id(customer_id: str) -> bool:
    """
    Validates customer ID format.
    """
    if not customer_id or not isinstance(customer_id, str):
        return False
    return len(customer_id) > 0
