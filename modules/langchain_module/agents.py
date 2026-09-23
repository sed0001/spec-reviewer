"""Experimental lightweight agent (ReAct-style). NOT part of round-1 tests.

This is intentionally minimal and may cost multiple LLM calls per run, so it is
excluded from the cost-sensitive first test round. Use only when needed.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage

from .base import get_llm

_THOUGHT_ACTION_RE = None  # placeholder to avoid import cost


def run_agent(
    question: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_steps: int = 4,
    **params: Any,
) -> Dict[str, Any]:
    """Run a tiny ReAct loop.

    ``tools`` is a list of dicts: {"name", "description", "func": Callable[[str], str]}.
    Returns {"answer", "steps": [...]} where each step records thought/action/obs.
    """
    tools = tools or []
    llm = get_llm(**params)
    tool_desc = "\n".join(f"- {t['name']}: {t['description']}" for t in tools) or "(no tools)"

    steps: List[Dict[str, str]] = []
    for _ in range(max_steps):
        prompt = (
            "Solve the task using the tools if needed. Reply in exactly this format:\n"
            "Thought: <your reasoning>\n"
            "Action: <tool_name>|<argument>\n"
            "If done, reply:\nThought: <reasoning>\nAction: Finish|<final answer>\n\n"
            f"TOOLS:\n{tool_desc}\n\nTASK: {question}\n"
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = getattr(resp, "content", str(resp))
        thought = ""
        action = ""
        for line in text.splitlines():
            if line.startswith("Thought:"):
                thought = line[len("Thought:"):].strip()
            elif line.startswith("Action:"):
                action = line[len("Action:"):].strip()
        steps.append({"thought": thought, "action": action})
        if action.startswith("Finish|"):
            return {"answer": action[len("Finish|"):].strip(), "steps": steps}
        if "|" in action:
            name, arg = action.split("|", 1)
            tool = next((t for t in tools if t["name"] == name.strip()), None)
            obs = tool["func"](arg.strip()) if tool else f"unknown tool: {name}"
            question = f"{question}\nObservation: {obs}"
    return {"answer": "", "steps": steps, "note": "max steps reached"}
