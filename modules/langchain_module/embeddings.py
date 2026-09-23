"""Embedding helpers."""

from __future__ import annotations

from typing import Any, List

from .base import get_embeddings


def embed(texts: List[str], **params: Any) -> List[List[float]]:
    """Embed a list of documents/strings."""
    return get_embeddings(**params).embed_documents(texts)


def embed_query(text: str, **params: Any) -> List[float]:
    """Embed a single query string."""
    return get_embeddings(**params).embed_query(text)
