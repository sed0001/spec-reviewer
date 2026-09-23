"""Minimal conversation memory buffer."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


class ConversationMemory:
    """A small rolling buffer of conversation turns."""

    def __init__(self, system: Optional[str] = None, max_turns: int = 10):
        self.system = system
        self.max_turns = max_turns
        self._history: List[BaseMessage] = []

    def add_user(self, text: str) -> None:
        self._history.append(HumanMessage(content=text))

    def add_ai(self, text: str) -> None:
        self._history.append(AIMessage(content=text))

    def messages(self) -> List[BaseMessage]:
        out: List[BaseMessage] = []
        if self.system:
            out.append(SystemMessage(content=self.system))
        # keep only the last `max_turns` turns
        turns = self._history[-self.max_turns * 2 :]
        out.extend(turns)
        return out

    def clear(self) -> None:
        self._history.clear()

    def as_dicts(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if self.system:
            out.append({"role": "system", "content": self.system})
        for m in self._history:
            if isinstance(m, HumanMessage):
                role = "user"
            elif isinstance(m, AIMessage):
                role = "assistant"
            elif isinstance(m, SystemMessage):
                role = "system"
            else:
                role = "user"
            out.append({"role": role, "content": m.content})
        return out
