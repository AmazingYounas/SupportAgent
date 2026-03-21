from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage


class ConversationState(TypedDict):
    """
    State structure that flows through LangGraph nodes.

    - messages:         Running dialogue (System, Human, AI, Tool messages).
    - customer_id:      Shopify customer ID, if identified.
    - active_order_id:  Shopify order currently in context, if any.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    customer_id: str | None
    active_order_id: str | None
