"""RAG over the LangChain documentation (ask_langchain_docs)."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.messages import HumanMessage

from . import retrievers
from .base import get_embeddings, get_llm


def ask_langchain_docs(
    query: str,
    k: int = 4,
    chunk_keys: Optional[Iterable[str]] = None,
    chunk_map_path: Optional[str] = None,
    docs_dir: Optional[str] = None,
    llm=None,
    embeddings=None,
) -> Dict[str, Any]:
    """Answer a question using only the documentation context.

    Cost control: pass ``chunk_keys`` to limit the embedded subset (the full
    corpus is ~9888 chunks — do not embed all of them on every run). The same
    ``chunk_keys`` list should be reused so the index is consistent.

    Returns a dict: {"answer", "sources", "context", "error"}.
    """
    embeddings = embeddings or get_embeddings()
    llm = llm or get_llm()

    chunk_map, base_dir = retrievers.load_chunk_map(chunk_map_path)
    docs_dir = docs_dir or base_dir

    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    for c in retrievers.iter_chunks(chunk_map, docs_dir, chunk_keys):
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
        return {"answer": "", "sources": [], "context": "", "error": "no chunks selected"}

    from langchain_community.vectorstores import FAISS

    index = FAISS.from_texts(texts, embeddings, metadatas=metas)
    docs = index.similarity_search(query, k=min(k, len(texts)))

    context = "\n\n".join(
        f"[src: {d.metadata.get('file')}#{d.metadata.get('start_line')}]\n{d.page_content}"
        for d in docs
    )
    prompt = (
        "You are a documentation assistant. Use ONLY the context below to answer.\n"
        "If the answer is not in the context, say you don't know.\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {query}\n\nANSWER:"
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    answer = getattr(resp, "content", str(resp))

    return {
        "answer": answer,
        "sources": [d.metadata for d in docs],
        "context": context,
        "error": None,
    }
