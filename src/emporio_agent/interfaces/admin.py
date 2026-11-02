"""Terminal admin panel for LLM providers (ADR-0007).

uv run emporio-admin list                       # providers in fallback order
uv run emporio-admin test [NAME|N]              # health check (all enabled when omitted)
uv run emporio-admin add NAME --base-url URL --model M --api-key K [--timeout S] [--position N]
uv run emporio-admin set NAME|N [--model M] [--base-url URL] [--api-key K] [--timeout S]
uv run emporio-admin enable|disable NAME|N
uv run emporio-admin move NAME|N POSITION       # change the fallback order
uv run emporio-admin remove NAME|N

Entries live in `.env` (secrets never leave it); every other line of the file is preserved.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

from emporio_agent.agent.llm import LLMError, OpenAICompatibleChatModel
from emporio_agent.config import DEFAULT_LLM_TIMEOUT, PROJECT_ROOT
from emporio_agent.providers import (
    Provider,
    ProviderConfigError,
    find,
    load_file_providers,
    read_env_file,
    temperature_from_env,
    write_providers,
)


def _print_table(providers: list[Provider]) -> None:
    if not providers:
        print("Nenhum provedor configurado. Use `emporio-admin add`.")
        return
    print(f"{'#':>2}  {'ativo':5}  {'nome':18}  {'modelo':26}  {'timeout':>7}  {'chave':11}  url")
    for number, p in enumerate(providers, 1):
        print(
            f"{number:>2}  {'sim' if p.enabled else 'não':5}  {p.name:18}  {p.model:26}  "
            f"{p.timeout:>6g}s  {p.masked_key:11}  {p.base_url}"
        )
    print("\nOrdem de fallback: os ativos, de cima para baixo.")


def _check(provider: Provider, temperature: float) -> tuple[bool, str]:
    # No retries: the panel reports the provider's real state, not a backed-off success.
    model = OpenAICompatibleChatModel(provider.settings(temperature), max_retries=0)
    started = time.monotonic()
    try:
        turn = model.complete([{"role": "user", "content": "Responda apenas: ok"}], [])
    except LLMError as exc:
        return False, f"{exc} ({time.monotonic() - started:.1f}s)"
    served = turn.model or provider.model
    return True, f"{served} respondeu em {time.monotonic() - started:.1f}s"


def _test(env_file: Path, providers: list[Provider], target: str | None) -> int:
    temperature = temperature_from_env(read_env_file(env_file))
    selected = [find(providers, target)] if target else [p for p in providers if p.enabled]
    if not selected:
        print("Nenhum provedor ativo para testar.")
        return 1
    failures = 0
    for provider in selected:
        ok, detail = _check(provider, temperature)
        failures += not ok
        print(f"{'OK   ' if ok else 'FALHA'}  {provider.name}: {detail}")
    return 1 if failures else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emporio-admin", description="Painel administrativo dos provedores de LLM"
    )
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="lista os provedores na ordem de fallback")
    test = sub.add_parser("test", help="testa um provedor (ou todos os ativos)")
    test.add_argument("provider", nargs="?")

    add = sub.add_parser("add", help="cadastra um provedor")
    add.add_argument("name")
    add.add_argument("--base-url", required=True)
    add.add_argument("--model", required=True)
    add.add_argument("--api-key", required=True)
    add.add_argument("--timeout", type=float, default=DEFAULT_LLM_TIMEOUT)
    add.add_argument("--position", type=int, help="posição na ordem (padrão: última)")
    add.add_argument("--disabled", action="store_true")

    edit = sub.add_parser("set", help="altera um provedor (ex.: trocar o modelo)")
    edit.add_argument("provider")
    edit.add_argument("--name")
    edit.add_argument("--base-url")
    edit.add_argument("--model")
    edit.add_argument("--api-key")
    edit.add_argument("--timeout", type=float)

    for command in ("enable", "disable", "remove"):
        sub.add_parser(command).add_argument("provider")
    move = sub.add_parser("move", help="muda a posição na ordem de fallback")
    move.add_argument("provider")
    move.add_argument("position", type=int)
    return parser


def _insert(providers: list[Provider], provider: Provider, position: int | None) -> None:
    index = len(providers) if position is None else max(0, min(position - 1, len(providers)))
    providers.insert(index, provider)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    env_file: Path = args.env_file
    try:
        providers = load_file_providers(env_file)
        if args.command == "list":
            _print_table(providers)
            return 0
        if args.command == "test":
            return _test(env_file, providers, args.provider)

        if args.command == "add":
            if any(p.name == args.name for p in providers):
                raise ProviderConfigError(f"Já existe um provedor chamado {args.name!r}.")
            new = Provider(
                name=args.name,
                base_url=args.base_url,
                model=args.model,
                api_key=args.api_key,
                timeout=args.timeout,
                enabled=not args.disabled,
            )
            _insert(providers, new, args.position)
        else:
            target = find(providers, args.provider)
            index = providers.index(target)
            if args.command == "set":
                changes = {
                    field: value
                    for field in ("name", "base_url", "model", "api_key", "timeout")
                    if (value := getattr(args, field)) is not None
                }
                if not changes:
                    raise ProviderConfigError("Nada para alterar (use --model, --timeout, ...).")
                providers[index] = replace(target, **changes)
            elif args.command in ("enable", "disable"):
                providers[index] = replace(target, enabled=args.command == "enable")
            elif args.command == "remove":
                providers.pop(index)
            elif args.command == "move":
                providers.pop(index)
                _insert(providers, target, args.position)

        write_providers(env_file, providers)
        _print_table(providers)
        return 0
    except ProviderConfigError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
