"""Prompt construction helpers."""

from __future__ import annotations

from typing import Dict, List, Optional


def build_prompt(template: str, **values: str) -> str:
    """Fill a ``{name}``-style template with the given values."""
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template


def few_shot(examples: List[Dict[str, str]], question: str) -> str:
    """Build a few-shot prompt from example Q/A pairs plus a final question."""
    parts: List[str] = []
    for ex in examples:
        parts.append(f"Q: {ex['question']}\nA: {ex['answer']}")
    parts.append(f"Q: {question}\nA:")
    return "\n\n".join(parts)


def system_user(system: str, user: str) -> List[Dict[str, str]]:
    """Return a simple [system, user] message list for raw clients."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
