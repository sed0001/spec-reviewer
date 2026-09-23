"""Automatic artifact logging — stays inside the project folder.

Artifacts are findings/notes discovered while the module is used or tested in a
project. They are written to ``ARTIFACTS.md`` next to this file, which travels
with the module when copied back to docs — so knowledge is never lost even if the
user forgets to ask for it.

Usage:
    from langchain_module.artifacts import record
    record("model X ignores temperature", tag="test")
"""

from __future__ import annotations

import datetime
import os
from typing import Optional

_ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ARTIFACTS.md")

_HEADER = (
    "# ARTIFACTS\n\n"
    "Заметки и находки, выявленные при работе модуля в проекте.\n"
    "Файл копируется вместе с модулем обратно в docs — переносимые знания.\n\n"
)


def record(note: str, *, tag: Optional[str] = None) -> str:
    """Append a timestamped note to ARTIFACTS.md (creates the file if missing)."""
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    prefix = f"[{tag}] " if tag else ""
    line = f"- [{ts}] {prefix}{note}\n"
    if not os.path.exists(_ARTIFACTS):
        with open(_ARTIFACTS, "w", encoding="utf-8") as f:
            f.write(_HEADER)
    with open(_ARTIFACTS, "a", encoding="utf-8") as f:
        f.write(line)
    return line
