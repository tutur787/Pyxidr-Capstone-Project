"""Smoke test: the explain intent's reference docs must exist and load."""

from __future__ import annotations

from agent.reference_docs import DURATION_SWAPS_DOC, OPTIMIZATION_DOC, load_reference_docs


def test_reference_doc_paths_exist() -> None:
    assert DURATION_SWAPS_DOC.is_file()
    assert OPTIMIZATION_DOC.is_file()


def test_load_reference_docs_contains_both() -> None:
    text = load_reference_docs()
    assert "Duration & Swaps Reference" in text
    assert "Optimization Reference" in text
