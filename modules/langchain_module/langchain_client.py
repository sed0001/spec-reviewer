"""Top-level convenience client bundling the module's capabilities."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from . import chains, llms, rag


class LangChainClient:
    """A single object exposing the module's features with shared defaults."""

    def __init__(self, **defaults: Any):
        self.defaults = defaults

    def chat(self, messages, **kw: Any):
        return llms.chat(messages, **{**self.defaults, **kw})

    def complete(self, prompt: str, system: Optional[str] = None, **kw: Any) -> str:
        return llms.complete(prompt, system=system, **{**self.defaults, **kw})

    def ask_docs(self, query: str, **kw: Any) -> Dict[str, Any]:
        return rag.ask_langchain_docs(query, **{**self.defaults, **kw})

    def run_chain(self, template: str, values: Dict[str, str], **kw: Any) -> str:
        return chains.run_chain(template, values, **{**self.defaults, **kw})
