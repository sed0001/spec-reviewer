"""Backend switch + env config for langchain_module.

Public entry points (no heavy imports at module load, so the package can be
imported even before langchain is installed):

    from langchain_module.base import get_llm, get_embeddings
    llm = get_llm()          # backend from LC_LLM_BACKEND (default proxyapi)
    embeddings = get_embeddings()
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------- #
# Env config
# --------------------------------------------------------------------------- #

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v


def _float_env(name: str, default: float) -> float:
    v = _env(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# LLM backend
# --------------------------------------------------------------------------- #
def get_llm(model: Optional[str] = None, temperature: Optional[float] = None,
            backend: Optional[str] = None, **params: Any):
    """Return a LangChain chat model for the configured backend.

    Supported backends:
      * "proxyapi" -> ProxyAPIChatModel (uses the PROJECT-ROOT ``proxyapi_module``,
        OpenAI-compatible endpoint). Model names with gpt/o1/o3... prefixes are
        routed to the OpenAI provider automatically by that client.
      * "openai"    -> langchain_openai.ChatOpenAI (direct OpenAI).

    Any extra ``params`` are forwarded to the model constructor / calls.
    """
    backend = backend or _env("LC_LLM_BACKEND", "proxyapi")
    model = model or _env("LC_MODEL", "gpt-4o-mini")
    temperature = temperature if temperature is not None else _float_env("LC_TEMPERATURE", 0.0)

    if backend == "proxyapi":
        from .bridges.proxyapi import ProxyAPIChatModel
        return ProxyAPIChatModel(
            model=model,
            temperature=temperature,
            proxyapi_key=_env("PROXYAPI_KEY"),
            extra_params=params,
        )
    if backend == "genapi":
        from .bridges.genapi import GenAPIChatModel
        return GenAPIChatModel(
            model=model,
            temperature=temperature,
            genapi_key=_env("GENAPI_KEY"),
            extra_params=params,
        )
    if backend == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, **params)
    raise ValueError(f"Unknown LC_LLM_BACKEND: {backend!r} (use 'proxyapi', 'genapi' or 'openai')")


# --------------------------------------------------------------------------- #
# Embeddings backend
# --------------------------------------------------------------------------- #
def get_embeddings(model: Optional[str] = None, backend: Optional[str] = None,
                   **params: Any):
    """Return a LangChain embeddings object for the configured backend."""
    backend = backend or _env("LC_LLM_BACKEND", "proxyapi")
    model = model or _env("LC_EMBED_MODEL", "text-embedding-3-small")

    if backend == "proxyapi":
        from .bridges.proxyapi import ProxyAPIEmbeddings
        return ProxyAPIEmbeddings(
            model=model,
            proxyapi_key=_env("PROXYAPI_KEY"),
            extra_params=params,
        )
    if backend == "genapi":
        from .bridges.genapi import GenAPIEmbeddings
        return GenAPIEmbeddings(
            model=model,
            genapi_key=_env("GENAPI_KEY"),
            extra_params=params,
        )
    if backend == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model, **params)
    raise ValueError(f"Unknown LC_LLM_BACKEND: {backend!r} (use 'proxyapi', 'genapi' or 'openai')")
