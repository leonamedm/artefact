"""Interactive terminal chat (ADR-0006).

uv run emporio-chat                 # new conversation
uv run emporio-chat --session ID    # resume a saved conversation
uv run emporio-chat --debug         # also print tool calls
uv run emporio-chat --provider 2    # use only that provider (name or number), no fallback
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from dotenv import load_dotenv

from emporio_agent.agent.llm import LLMError, build_chat_model
from emporio_agent.app import build_application
from emporio_agent.clock import Clock, FixedClock, SystemClock
from emporio_agent.config import PROJECT_ROOT, VAR_DIR
from emporio_agent.providers import load_chain
from emporio_agent.repositories.db import CatalogNotBuiltError

EXIT_WORDS = {"sair", "exit", "quit", "tchau"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Empório da Música — atendimento virtual")
    parser.add_argument("--session", help="resume a saved conversation by id")
    parser.add_argument("--debug", action="store_true", help="print tool calls")
    parser.add_argument(
        "--now",
        type=datetime.fromisoformat,
        help="simulate the current date/time (ISO), e.g. 2026-11-03T10:00",
    )
    parser.add_argument(
        "--provider",
        help="use only this LLM provider (name or number from `emporio-admin list`)",
    )
    args = parser.parse_args(argv)

    load_dotenv(PROJECT_ROOT / ".env")
    clock: Clock = FixedClock(args.now) if args.now else SystemClock()
    try:
        model = build_chat_model(load_chain(args.provider))
        app = build_application(VAR_DIR, model, clock)
    except (RuntimeError, CatalogNotBuiltError) as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    store = app.conversations
    assert store is not None
    if args.session:
        if not store.exists(args.session):
            print(f"Sessão {args.session} não encontrada.", file=sys.stderr)
            return 2
        session_id = args.session
    else:
        session_id = store.create_session(clock.now())
    app.context.session_id = session_id
    history = store.load(session_id)

    print("Empório da Música — atendimento virtual")
    print(f"Sessão: {session_id} (retome com --session {session_id}).")
    print("Digite 'sair' para encerrar.\n")

    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            break
        try:
            result = app.agent.respond(history, text)
        except LLMError as exc:
            # The turn is not persisted, so the customer can simply resend the message.
            print(f"\n[indisponível] {exc}\n", file=sys.stderr)
            continue
        if args.debug:
            for trace in result.traces:
                print(f"  ↳ {trace.name}({trace.arguments})")
                print(f"    {json.dumps(trace.result, ensure_ascii=False)[:500]}")
        store.append(session_id, result.messages, clock.now())
        history.extend(result.messages)
        print(f"\nEmpório: {result.reply}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
