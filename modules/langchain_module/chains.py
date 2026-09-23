"""Simple composable chains (prompt + LLM)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from . import prompts as prompt_utils
from .base import get_llm


def run_chain(
    template: str,
    values: Dict[str, str],
    system: Optional[str] = None,
    **params: Any,
) -> str:
    """Fill ``template`` with ``values`` and run it through the LLM."""
    text = prompt_utils.build_prompt(template, **values)
    msgs = []
    if system:
        msgs.append(SystemMessage(content=system))
    msgs.append(HumanMessage(content=text))
    llm = get_llm(**params)
    result = llm.invoke(msgs)
    return getattr(result, "content", str(result))
