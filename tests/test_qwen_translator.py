"""Unit tests for JSON extraction (no live HF API calls)."""

from __future__ import annotations

import pytest

from agent.qwen_translator import TranslationError, _extract_json


def test_extract_json_plain() -> None:
    data = _extract_json('{"intent": "unsupported", "run": null}')
    assert data["intent"] == "unsupported"


def test_extract_json_markdown_fence() -> None:
    raw = 'Here you go:\n```json\n{"intent": "select"}\n```'
    assert _extract_json(raw)["intent"] == "select"


def test_hf_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    from agent import qwen_translator

    with pytest.raises(TranslationError, match="HF_TOKEN"):
        qwen_translator._hf_token()
