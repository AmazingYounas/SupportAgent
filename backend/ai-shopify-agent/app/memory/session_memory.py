from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from typing import List

# Message type → class mapping for deserialization
_MSG_TYPES = {
    "human": HumanMessage,
    "ai": AIMessage,
    "system": SystemMessage,
}

class SessionMemory:
    """
    Manages short-term conversation history for a specific active session.
    It formats messages specifically for LangChain/LangGraph context injection.
    """
    def __init__(self):
        self._messages = []

    def set_system_prompt(self, prompt_text: str):
        """
        Sets or replaces the foundational system prompt for the session.
        This must always remain the first message.
        """
        sys_msg = SystemMessage(content=prompt_text)
        if self._messages and isinstance(self._messages[0], SystemMessage):
            self._messages[0] = sys_msg
        else:
            self._messages.insert(0, sys_msg)

    def add_user_message(self, content: str):
        self._messages.append(HumanMessage(content=content))

    def add_ai_message(self, content: str):
        self._messages.append(AIMessage(content=content))
        
    def add_raw_message(self, message: BaseMessage):
        """
        Directly appends a LangChain message object (e.g., ToolMessage).
        """
        self._messages.append(message)

    def get_messages(self, limit: int = 20) -> list[BaseMessage]:
        """
        Retrieves the conversation history.
        Ensures the system prompt is always included regardless of the limit.
        Trims internal list to prevent unbounded memory growth.
        """
        if not self._messages:
            return []

        system_prompt = [m for m in self._messages if isinstance(m, SystemMessage)]
        other_messages = [m for m in self._messages if not isinstance(m, SystemMessage)]

        # Trim internal list to at most limit*2 entries to prevent OOM
        max_stored = limit * 2
        if len(other_messages) > max_stored:
            other_messages = other_messages[-max_stored:]
            self._messages = system_prompt + other_messages

        # Return system prompt + the last N non-system messages
        recent_messages = other_messages[-min(limit, len(other_messages)):]
        return system_prompt + recent_messages
        
    def clear(self):
        self._messages = []

    # ------------------------------------------------------------------
    # Persistence helpers — used by routes.py for Fix 4 (session restore)
    # ------------------------------------------------------------------

    def serialize(self) -> List[dict]:
        """
        Convert _messages to a JSON-serializable list.
        Only serializes Human/AI/System messages (skips ToolMessage etc.
        which contain raw API data not useful to restore).
        """
        result = []
        for msg in self._messages:
            if isinstance(msg, HumanMessage):
                result.append({"type": "human", "content": msg.content})
            elif isinstance(msg, AIMessage):
                # Only persist the text content, not tool_calls (those are transient)
                content = msg.content if isinstance(msg.content, str) else ""
                if content:
                    result.append({"type": "ai", "content": content})
            elif isinstance(msg, SystemMessage):
                result.append({"type": "system", "content": msg.content})
        return result

    def restore_from(self, history: List[dict]) -> None:
        """
        Restore _messages from a serialized history list (from DB).
        Skips unknown types silently.
        """
        self._messages = []
        for entry in history:
            msg_type = entry.get("type")
            content = entry.get("content", "")
            cls = _MSG_TYPES.get(msg_type)
            if cls and content:
                self._messages.append(cls(content=content))
