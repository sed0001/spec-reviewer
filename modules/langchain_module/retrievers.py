"""Retrieval over the LangChain docs chunk_map using FAISS + embeddings."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, Iterator, List, Optional

from langchain_core.documents import Document

from .base import get_embeddings


def default_chunk_map_path() -> str:
    # langchain_module/ -> langchain/ -> chunk_map.json
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "chunk_map.json",
    )


def load_chunk_map(path: Optional[str] = None):
    path = path or default_chunk_map_path()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(path))
    return data, base_dir


def iter_chunks(
    chunk_map: Dict[str, Any],
    docs_dir: str,
    chunk_keys: Optional[Iterable[str]] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield chunk dicts with resolved text.

    Each yielded item: {"key", "file", "text", "start_line", "end_line"}.
    """
    want = set(chunk_keys) if chunk_keys else None
    for file_rel, meta in chunk_map.items():
        file_path = os.path.join(docs_dir, file_rel)
        if not os.path.exists(file_path):
            continue
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for ch in meta.get("chunks", []):
            key = ch["key"]
            if want and key not in want:
                continue
            start = int(ch["start_line"])
            end = int(ch["end_line"])
            text = "".join(lines[start - 1 : end])
            yield {
                "key": key,
                "file": file_rel,
                "text": text,
                "start_line": start,
                "end_line": end,
            }


def build_index(
    chunk_keys: Optional[Iterable[str]] = None,
    chunk_map_path: Optional[str] = None,
    docs_dir: Optional[str] = None,
    embeddings=None,
) -> Any:
    """Build an in-memory FAISS index over (a subset of) documentation chunks."""
    from langchain_community.vectorstores import FAISS

    chunk_map, base_dir = load_chunk_map(chunk_map_path)
    docs_dir = docs_dir or base_dir
    embeddings = embeddings or get_embeddings()

    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    for c in iter_chunks(chunk_map, docs_dir, chunk_keys):
        texts.append(c["text"])
        metas.append(
            {
                "key": c["key"],
                "file": c["file"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
            }
        )
    if not texts:
        raise ValueError("No chunks selected/built (check chunk_keys and docs_dir).")
    return FAISS.from_texts(texts, embeddings, metadatas=metas)


def retrieve(
    query: str,
    k: int = 4,
    index=None,
    chunk_keys: Optional[Iterable[str]] = None,
    chunk_map_path: Optional[str] = None,
    docs_dir: Optional[str] = None,
    embeddings=None,
) -> List[Document]:
    """Retrieve the top-k relevant chunks as LangChain Documents."""
    if index is None:
        index = build_index(
            chunk_keys=chunk_keys,
            chunk_map_path=chunk_map_path,
            docs_dir=docs_dir,
            embeddings=embeddings,
        )
    return index.similarity_search(query, k=k)
