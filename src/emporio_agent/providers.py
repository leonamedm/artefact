"""LLM provider registry kept in `.env` (ADR-0007).

Providers are numbered environment variables; the number is the fallback order:

    LLM_1_NAME=gemini            LLM_2_NAME=ollama-qwen3-4b
    LLM_1_BASE_URL=...           LLM_2_BASE_URL=http://localhost:11434/v1
    LLM_1_MODEL=...              LLM_2_MODEL=qwen3:4b
    LLM_1_API_KEY=...            LLM_2_API_KEY=ollama
                                 LLM_2_TIMEOUT=300
                                 LLM_2_ENABLED=false

Without numbered variables the single legacy set (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY) is used,
so existing `.env` files keep working. Secrets stay in `.env` (CLAUDE.md convention): this module
is the only place that reads or rewrites provider entries, for both the agent and `emporio-admin`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from emporio_agent.config import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT,
    LLMSettings,
)

_NUMBERED = re.compile(r"^LLM_(\d+)_(NAME|BASE_URL|MODEL|API_KEY|TIMEOUT|ENABLED)$")
_LEGACY_KEYS = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
_MANAGED_HEADER = "# LLM providers, in fallback order (managed by `uv run emporio-admin`)"
_FALSE = {"0", "false", "no", "off"}


class ProviderConfigError(RuntimeError):
    """Provider configuration is missing or invalid."""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str
    timeout: float = DEFAULT_LLM_TIMEOUT
    enabled: bool = True

    def settings(self, temperature: float) -> LLMSettings:
        return LLMSettings(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            temperature=temperature,
            timeout=self.timeout,
            name=self.name,
        )

    @property
    def masked_key(self) -> str:
        key = self.api_key
        return key if len(key) <= 8 else f"{key[:4]}…{key[-4:]}"


def _float(value: str, key: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ProviderConfigError(f"{key} must be a number, got {value!r}.") from exc


def providers_from_env(env: Mapping[str, str]) -> list[Provider]:
    """All configured providers (enabled or not), in fallback order."""
    default_timeout = _float(env.get("LLM_TIMEOUT", str(DEFAULT_LLM_TIMEOUT)), "LLM_TIMEOUT")
    numbered: dict[int, dict[str, str]] = {}
    for key, value in env.items():
        match = _NUMBERED.match(key)
        if match:
            numbered.setdefault(int(match[1]), {})[match[2]] = value.strip()

    if not numbered:
        api_key = env.get("LLM_API_KEY", "").strip()
        if not api_key:
            return []
        return [
            Provider(
                name="default",
                base_url=env.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip(),
                model=env.get("LLM_MODEL", DEFAULT_LLM_MODEL).strip(),
                api_key=api_key,
                timeout=default_timeout,
            )
        ]

    providers = []
    for number in sorted(numbered):
        fields = numbered[number]
        missing = [f for f in ("BASE_URL", "MODEL", "API_KEY") if not fields.get(f)]
        if missing:
            raise ProviderConfigError(
                f"Provider LLM_{number}_* is missing: "
                + ", ".join(f"LLM_{number}_{f}" for f in missing)
            )
        providers.append(
            Provider(
                name=fields.get("NAME") or f"provider-{number}",
                base_url=fields["BASE_URL"],
                model=fields["MODEL"],
                api_key=fields["API_KEY"],
                timeout=(
                    _float(fields["TIMEOUT"], f"LLM_{number}_TIMEOUT")
                    if fields.get("TIMEOUT")
                    else default_timeout
                ),
                enabled=fields.get("ENABLED", "true").lower() not in _FALSE,
            )
        )
    return providers


def temperature_from_env(env: Mapping[str, str]) -> float:
    # Low temperature: answers must stick to tool results, not be creative.
    return _float(env.get("LLM_TEMPERATURE", "0.2"), "LLM_TEMPERATURE")


def select(providers: list[Provider], wanted: str | None = None) -> list[Provider]:
    """Fallback chain: enabled providers in order, or only `wanted` (name or 1-based number)."""
    if wanted:
        chosen = find(providers, wanted)
        return [chosen]
    chain = [p for p in providers if p.enabled]
    if not chain:
        raise ProviderConfigError(
            "No enabled LLM provider. Copy .env.example to .env and fill it in, "
            "or add one with `uv run emporio-admin add`."
        )
    return chain


def find(providers: list[Provider], wanted: str) -> Provider:
    if wanted.isdigit() and 1 <= int(wanted) <= len(providers):
        return providers[int(wanted) - 1]
    for provider in providers:
        if provider.name == wanted:
            return provider
    names = ", ".join(f"{i}={p.name}" for i, p in enumerate(providers, 1)) or "none"
    raise ProviderConfigError(f"Unknown provider {wanted!r} (configured: {names}).")


def load_chain(wanted: str | None = None) -> list[LLMSettings]:
    """Settings for the fallback chain from the process environment."""
    env = dict(os.environ)
    temperature = temperature_from_env(env)
    return [p.settings(temperature) for p in select(providers_from_env(env), wanted)]


# --- .env editing (used by emporio-admin) -------------------------------------------------


def _key_of(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].removeprefix("export ").strip()


def read_env_file(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    if not path.exists():
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def write_providers(path: Path, providers: list[Provider]) -> None:
    """Rewrite the provider entries of `path`, keeping every other line untouched.

    Numbered entries are renumbered 1..n in the given order; legacy single-provider keys are
    dropped because numbered entries take precedence (they would be silently ignored).
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [
        line
        for line in lines
        if line.strip() != _MANAGED_HEADER
        and not ((key := _key_of(line)) and (_NUMBERED.match(key) or key in _LEGACY_KEYS))
    ]
    while kept and not kept[-1].strip():
        kept.pop()

    block = [_MANAGED_HEADER]
    for number, p in enumerate(providers, 1):
        block += [
            f"LLM_{number}_NAME={p.name}",
            f"LLM_{number}_BASE_URL={p.base_url}",
            f"LLM_{number}_MODEL={p.model}",
            f"LLM_{number}_API_KEY={p.api_key}",
            f"LLM_{number}_TIMEOUT={p.timeout:g}",
            f"LLM_{number}_ENABLED={'true' if p.enabled else 'false'}",
        ]
    path.write_text("\n".join([*kept, "", *block]).lstrip("\n") + "\n", encoding="utf-8")


def load_file_providers(path: Path) -> list[Provider]:
    return providers_from_env(read_env_file(path))
