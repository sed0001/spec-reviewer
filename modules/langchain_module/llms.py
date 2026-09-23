"""High-level LLM helpers (chat / completion)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from .base import get_llm


def chat(messages: List[BaseMessage], **params: Any) -> str:
    """Send LangChain messages and return the assistant text."""
    llm = get_llm(**params)
    result = llm.invoke(messages)
    if isinstance(result, AIMessage):
        return result.content
    if hasattr(result, "content"):
        return result.content
    return str(result)


def complete(prompt: str, system: Optional[str] = None, **params: Any) -> str:
    """Single-turn completion with an optional system prompt."""
    msgs: List[BaseMessage] = []
    if system:
        msgs.append(SystemMessage(content=system))
    msgs.append(HumanMessage(content=prompt))
    return chat(msgs, **params)
