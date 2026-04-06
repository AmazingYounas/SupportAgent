from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import logging

from app.config import settings
from app.agent.state import ConversationState
from app.agent.prompts import SYSTEM_PROMPT

from app.tools.customer_tools import UpdateCustomerFactsTool, GetCustomerFactsTool
from app.tools.handoff_tools import HumanHandoffTool

logger = logging.getLogger(__name__)

# Maximum tool-call iterations before the graph forces termination.
_MAX_ITERATIONS = 10


def create_tools():
    """Creates tools that work without Shopify. Order/product tools added on integration."""
    return [
        UpdateCustomerFactsTool(),
        GetCustomerFactsTool(),
        HumanHandoffTool(),
    ]


def create_llm_with_tools(tools):
    """Creates the LLM with tools bound, a 30-second timeout, and a 200-token output cap.
    
    200 tokens ≈ 3-4 sentences — appropriate for a voice agent.
    Without this cap, GPT-4o can generate 4096 tokens (5+ minutes of audio).
    """
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=settings.OPENAI_TEMPERATURE,
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT,
        max_tokens=settings.OPENAI_MAX_TOKENS,
        streaming=True,  # Enable token-level streaming so LangGraph emits on_chat_model_stream events.
    ).bind_tools(tools)


def create_agent_graph(tools, llm):
    """
    Builds a minimal LangGraph workflow:

        [START] → reasoning → (tool_calls?) → tools → reasoning (loop)
                           ↓ (no tool calls)
                         [END]

    Recursion is capped at _MAX_ITERATIONS to prevent runaway tool loops.
    """

    async def reasoning_node(state: ConversationState):
        """Calls the LLM; returns tool calls or a final answer."""
        messages = state["messages"]

        # Prepend system prompt if absent
        if not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: ConversationState) -> Literal["tools", "__end__"]:
        """Route to tool execution if LLM requested tool calls, otherwise finish."""
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    tool_node = ToolNode(tools)

    workflow = StateGraph(ConversationState)
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("reasoning")
    workflow.add_conditional_edges("reasoning", should_continue, {
        "tools": "tools",
        END: END,
    })
    workflow.add_edge("tools", "reasoning")

    # Compile graph (recursion_limit not supported in older LangGraph versions)
    # Tool-call loop protection is handled by LangGraph's default limits
    try:
        return workflow.compile(recursion_limit=_MAX_ITERATIONS * 2)
    except TypeError:
        # Fallback for older LangGraph versions without recursion_limit
        logger.warning("[Graph] recursion_limit not supported - using default limits")
        return workflow.compile()
