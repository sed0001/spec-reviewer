"""Build a chunk_map.json from a project's own documentation (portable).

A project supplies its OWN knowledge base: run ``build_chunk_map`` once over the
project's docs folder, then point the module at the produced ``chunk_map.json``
via ``LC_CHUNK_MAP`` / ``chunk_map_path=``. This is what makes the module
reusable across projects without copying the LangChain corpus around.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Optional


def build_chunk_map(
    docs_dir: str,
    out_path: Optional[str] = None,
    chunk_size: int = 120,
    overlap: int = 24,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """Walk ``docs_dir`` for ``*.md`` files and produce a chunk_map.

    Each file is split line-wise into overlapping windows of ``chunk_size`` lines
    with ``overlap`` lines of context, mirroring the schema consumed by
    ``retrievers.iter_chunks`` / ``rag.ask_langchain_docs``.
    """
    result: Dict[str, Any] = {}
    docs_dir = os.path.abspath(docs_dir)

    for root, _, files in os.walk(docs_dir):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, docs_dir).replace(os.sep, "/")
            with open(full, "r", encoding=encoding, errors="replace") as f:
                lines = f.read().splitlines()
            total = len(lines)
            chunks: list = []
            start = 1
            idx = 0
            while start <= total:
                idx += 1
                end = min(start + chunk_size - 1, total)
                chunks.append(
                    {
                        "key": f"{rel}_chunk{idx}",
                        "start_line": start,
                        "end_line": end,
                        "lines_count": end - start + 1,
                    }
                )
                if end >= total:
                    break
                nxt = end - overlap + 1
                if nxt <= start:
                    nxt = end + 1
                start = nxt
            result[rel] = {
                "total_lines": total,
                "total_chunks": len(chunks),
                "chunk_size": chunk_size,
                "overlap": overlap,
                "chunks": chunks,
            }

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build chunk_map.json from a docs folder.")
    ap.add_argument("docs_dir", help="Folder with project .md documentation")
    ap.add_argument("--out", default="chunk_map.json")
    ap.add_argument("--chunk-size", type=int, default=120)
    ap.add_argument("--overlap", type=int, default=24)
    a = ap.parse_args()
    build_chunk_map(a.docs_dir, a.out, a.chunk_size, a.overlap)
    print(f"wrote {a.out}")
