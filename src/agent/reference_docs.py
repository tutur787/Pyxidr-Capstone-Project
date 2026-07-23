"""Loads the duration/swaps and optimization reference docs for the explain intent.

Source of truth is the .md files themselves, not a copy pasted into prompts.py —
edit the docs and the explain intent picks it up automatically.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent

DURATION_SWAPS_DOC = _DOCS_DIR / "duration-swaps-reference.md"
OPTIMIZATION_DOC = _DOCS_DIR / "optimization-reference.md"


@lru_cache(maxsize=1)
def load_reference_docs() -> str:
    """Concatenates both reference docs into a single context block."""
    parts = []
    for path in (DURATION_SWAPS_DOC, OPTIMIZATION_DOC):
        parts.append(path.read_text())
    return "\n\n---\n\n".join(parts)
