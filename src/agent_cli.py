#!/usr/bin/env python3
"""
FABN agent CLI — structured JSON or natural language (HF Inference API).

Examples:
  python src/agent_cli.py turn --json '{"intent":"run","run":{"optimization_date":"2025-01-15","confirm":false}}'
  python src/agent_cli.py chat --message "Run optimization as of 2025-01-15 with 500 million budget"
  python src/agent_cli.py chat --repl
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from agent.orchestrator import (
    AgentSession,
    format_response,
    handle_turn,
    parse_turn_json,
    translate_user_message,
)
from agent.qwen_translator import TranslationError
from agent.schemas import AgentTurn, RunRequest, SelectRequest
from fabn_pipeline import FabnPipelineParams


def _run_turn(session: AgentSession, turn: AgentTurn) -> int:
    resp = handle_turn(turn, session=session)
    print(format_response(resp))
    return 0 if resp.ok else 1


def _cmd_chat(session: AgentSession, message: str) -> int:
    try:
        turn = translate_user_message(message, history=session.chat_history or None)
    except TranslationError as exc:
        print(f'{{"ok": false, "message": "Translation failed: {exc}"}}')
        return 1
    session.record_chat(message, turn.model_dump_json())
    return _run_turn(session, turn)


def _cmd_chat_repl(session: AgentSession) -> int:
    print("FABN agent (Qwen via HF Inference API). Empty line or Ctrl-D to exit.")
    while True:
        try:
            line = input("you> ").strip()
        except EOFError:
            print()
            break
        if not line:
            break
        code = _cmd_chat(session, line)
        if code != 0:
            continue
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    parser = argparse.ArgumentParser(description="FABN orchestration agent")
    sub = parser.add_subparsers(dest="command", required=True)

    turn_p = sub.add_parser("turn", help="Handle a full AgentTurn JSON object")
    turn_p.add_argument("--json", required=True, help="AgentTurn JSON string")

    run_p = sub.add_parser("run", help="Shorthand for intent=run")
    run_p.add_argument("--json", required=True, help="RunRequest JSON string")

    sel_p = sub.add_parser("select", help="Shorthand for intent=select")
    sel_p.add_argument("--json", required=True, help="SelectRequest JSON string")

    chat_p = sub.add_parser("chat", help="Natural language via HF Inference API (Qwen)")
    chat_p.add_argument("--message", "-m", help="Single user message")
    chat_p.add_argument(
        "--repl",
        action="store_true",
        help="Interactive chat loop (keeps session history)",
    )

    args = parser.parse_args(argv)
    session = AgentSession(base_params=FabnPipelineParams.from_env())

    if args.command == "turn":
        turn = parse_turn_json(args.json)
        return _run_turn(session, turn)
    if args.command == "run":
        turn = AgentTurn(intent="run", run=RunRequest.model_validate_json(args.json))
        return _run_turn(session, turn)
    if args.command == "select":
        turn = AgentTurn(
            intent="select", select=SelectRequest.model_validate_json(args.json)
        )
        return _run_turn(session, turn)

    if args.repl:
        return _cmd_chat_repl(session)
    if not args.message:
        chat_p.error("chat requires --message or --repl")
    return _cmd_chat(session, args.message)


if __name__ == "__main__":
    sys.exit(main())
