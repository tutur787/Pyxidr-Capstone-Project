"""
POST /api/agent/chat — natural-language interface over the FABN optimizer.

NL text -> Qwen2.5 (HF Inference API) -> AgentTurn -> run optimizer / query
last result. See backend/services/agent_service.py for the adaptation of
src/agent/'s orchestration design onto our working optimizer_service.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel

from services import agent_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str


@router.get("/status")
def agent_status():
    return {"hf_token_configured": agent_service.hf_token_configured()}


@router.post("/context")
def set_context(result: dict[str, Any] = Body(...)):
    """Adopt the dashboard's already-computed GET /api/optimize result as the
    chat session's context, so SELECT queries (trades, RBC drivers, ...)
    reflect exactly what's on screen without a redundant re-solve via chat."""
    adopted = agent_service.set_context(result)
    return {"adopted": adopted}


@router.post("/chat")
async def chat(req: ChatRequest):
    session = agent_service.get_session()

    if not agent_service.hf_token_configured():
        return {
            "ok": False,
            "message": (
                "Natural-language chat needs an HF_TOKEN (Hugging Face Inference API) "
                "configured in .env — get one at huggingface.co/settings/tokens and "
                "restart the backend."
            ),
            "data": {},
        }

    try:
        turn = await asyncio.to_thread(
            agent_service.translate_user_message, req.message, history=session.chat_history
        )
    except Exception as exc:  # noqa: BLE001 — surface translator errors to the chat UI
        return {"ok": False, "message": f"Couldn't understand that: {exc}", "data": {}}

    response = await asyncio.to_thread(agent_service.handle_turn, turn, session=session)
    session.record_chat(req.message, response.message)

    return {"ok": response.ok, "message": response.message, "data": response.data}
