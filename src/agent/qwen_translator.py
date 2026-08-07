"""
NL → AgentTurn via Hugging Face Inference API (Qwen2.5-7B-Instruct).

Requires HF_TOKEN (or HUGGING_FACE_HUB_TOKEN). Optional HF_AGENT_MODEL override.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from agent.prompts import CONTRIBUTION_NARRATIVE_PROMPT, EXPLAIN_SYSTEM_PROMPT, SYSTEM_PROMPT
from agent.schemas import AgentTurn

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-72B-Instruct"


class TranslationError(Exception):
    """Raised when the model output cannot be parsed or validated."""


def _hf_token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise TranslationError(
            "Set HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) for Hugging Face Inference API"
        )
    return token


def _model_id() -> str:
    return os.environ.get("HF_AGENT_MODEL", DEFAULT_MODEL_ID)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _completion_content(response: Any) -> str:
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as exc:
        raise TranslationError(f"unexpected Inference API response: {response!r}") from exc


def generate_narrative(context_json: str) -> str:
    """Call Qwen to produce a plain-text narrative summary of contribution analysis output."""
    from huggingface_hub import InferenceClient

    client = InferenceClient(model=_model_id(), token=_hf_token())
    prompt = CONTRIBUTION_NARRATIVE_PROMPT.format(context_json=context_json)
    messages = [{"role": "user", "content": prompt}]
    logger.info("HF inference narrative model=%s", _model_id())
    response = client.chat_completion(messages=messages, max_tokens=256, temperature=0)
    return _completion_content(response).strip()


def answer_explain_question(question: str, live_context_json: str) -> str:
    """Call Qwen to answer a conceptual duration/swaps/optimization question.

    Grounded in the reference docs (src/agent/duration-swaps-reference.md and
    optimization-reference.md) plus whatever live run context the caller supplies.
    """
    from huggingface_hub import InferenceClient
    from agent.reference_docs import load_reference_docs

    client = InferenceClient(model=_model_id(), token=_hf_token())
    prompt = EXPLAIN_SYSTEM_PROMPT.format(
        reference_docs=load_reference_docs(),
        live_context_json=live_context_json,
        question=question,
    )
    messages = [{"role": "user", "content": prompt}]
    logger.info("HF inference explain model=%s", _model_id())
    # 250 tokens is generous headroom over the prompt's 180-word hard cap (roughly
    # 240 tokens at ~1.3 tokens/word) — enough that a compliant answer never
    # truncates mid-sentence, tight enough that a non-compliant one gets capped
    # fast rather than rambling for hundreds of tokens before cutting off.
    response = client.chat_completion(messages=messages, max_tokens=250, temperature=0)
    return _completion_content(response).strip()


def translate_with_qwen(
    user_message: str,
    *,
    history: Optional[list[dict[str, str]]] = None,
    retry: bool = True,
) -> AgentTurn:
    """
    Call Qwen on the HF Inference API and return a validated AgentTurn.
    """
    from huggingface_hub import InferenceClient

    client = InferenceClient(model=_model_id(), token=_hf_token())
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    def _call(msgs: list[dict[str, str]]) -> str:
        logger.info("HF inference model=%s", _model_id())
        response = client.chat_completion(
            messages=msgs,
            max_tokens=512,
            temperature=0,
        )
        return _completion_content(response)

    raw = _call(messages)
    try:
        data = _extract_json(raw)
        data.setdefault("user_message", user_message)
        return AgentTurn.model_validate(data)
    except (json.JSONDecodeError, ValueError) as first_err:
        if not retry:
            raise TranslationError(f"model returned invalid JSON: {raw!r}") from first_err
        repair_msgs = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "That was not valid JSON for AgentTurn. "
                    "Reply with only a single JSON object, no markdown."
                ),
            },
        ]
        raw2 = _call(repair_msgs)
        try:
            data = _extract_json(raw2)
            data.setdefault("user_message", user_message)
            return AgentTurn.model_validate(data)
        except (json.JSONDecodeError, ValueError) as second_err:
            raise TranslationError(
                f"could not parse AgentTurn after retry: {raw2!r}"
            ) from second_err
