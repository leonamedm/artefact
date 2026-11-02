"""Provider registry, fallback chain and admin panel (ADR-0007). No network: fake models."""

from __future__ import annotations

from pathlib import Path

import pytest

from emporio_agent.agent.llm import AssistantTurn, FallbackChatModel, LLMError
from emporio_agent.interfaces import admin
from emporio_agent.providers import (
    ProviderConfigError,
    load_file_providers,
    providers_from_env,
    select,
)

OLLAMA = {
    "LLM_2_NAME": "ollama",
    "LLM_2_BASE_URL": "http://localhost:11434/v1",
    "LLM_2_MODEL": "qwen3:4b",
    "LLM_2_API_KEY": "ollama",
    "LLM_2_TIMEOUT": "300",
}
GEMINI = {
    "LLM_1_NAME": "gemini",
    "LLM_1_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "LLM_1_MODEL": "gemini-flash-latest",
    "LLM_1_API_KEY": "AIzaSECRETKEY1234",
}


def test_legacy_single_provider_still_works():
    providers = providers_from_env(
        {"LLM_BASE_URL": "http://x/v1", "LLM_MODEL": "m", "LLM_API_KEY": "k"}
    )
    assert [(p.name, p.model, p.timeout) for p in providers] == [("default", "m", 60.0)]


def test_no_key_means_no_provider_and_a_clear_error():
    assert providers_from_env({}) == []
    with pytest.raises(ProviderConfigError, match="emporio-admin add"):
        select([])


def test_numbered_providers_ordered_and_override_legacy():
    env = {**OLLAMA, **GEMINI, "LLM_MODEL": "ignored", "LLM_API_KEY": "ignored"}
    providers = providers_from_env(env)
    assert [p.name for p in providers] == ["gemini", "ollama"]
    assert providers[0].timeout == 60.0 and providers[1].timeout == 300.0


def test_disabled_provider_left_out_of_chain_but_selectable_by_name():
    providers = providers_from_env({**GEMINI, **OLLAMA, "LLM_1_ENABLED": "false"})
    assert [p.name for p in select(providers)] == ["ollama"]
    assert [p.name for p in select(providers, "gemini")] == ["gemini"]
    assert [p.name for p in select(providers, "2")] == ["ollama"]
    with pytest.raises(ProviderConfigError, match="Unknown provider"):
        select(providers, "groq")


def test_incomplete_numbered_provider_is_reported():
    with pytest.raises(ProviderConfigError, match="LLM_3_API_KEY"):
        providers_from_env({"LLM_3_BASE_URL": "http://x", "LLM_3_MODEL": "m"})


class FakeModel:
    def __init__(self, name: str, fail: bool) -> None:
        self.label = self.model_name = name
        self.fail = fail
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.fail:
            raise LLMError(f"{self.label} is down")
        return AssistantTurn({"role": "assistant", "content": "oi"}, [], self.label)


def test_fallback_uses_next_provider_when_first_fails():
    first, second = FakeModel("a", fail=True), FakeModel("b", fail=False)
    turn = FallbackChatModel([first, second]).complete([], [])
    assert turn.model == "b" and first.calls == second.calls == 1


def test_fallback_retries_primary_on_every_request():
    first, second = FakeModel("a", fail=False), FakeModel("b", fail=False)
    chain = FallbackChatModel([first, second])
    chain.complete([], [])
    chain.complete([], [])
    assert first.calls == 2 and second.calls == 0


def test_fallback_reports_every_failure():
    chain = FallbackChatModel([FakeModel("a", fail=True), FakeModel("b", fail=True)])
    with pytest.raises(LLMError, match="All LLM providers failed.*a is down.*b is down"):
        chain.complete([], [])


def test_admin_edits_env_keeping_other_lines(tmp_path: Path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "# my settings\nLLM_BASE_URL=http://localhost:11434/v1\nLLM_MODEL=qwen3:8b\n"
        "LLM_API_KEY=ollama\nLLM_TEMPERATURE=0.2\n",
        encoding="utf-8",
    )
    run = lambda *a: admin.main(["--env-file", str(env), *a])  # noqa: E731

    # The legacy entry becomes provider 1; a hosted one is added in front as primary.
    assert (
        run(
            "add",
            "gemini",
            "--base-url",
            "https://g/",
            "--model",
            "gf",
            "--api-key",
            "AIzaSECRETKEY1234",
            "--position",
            "1",
        )
        == 0
    )
    assert run("set", "default", "--model", "qwen3:4b", "--timeout", "300") == 0
    assert run("disable", "gemini") == 0
    assert run("move", "default", "1") == 0

    providers = load_file_providers(env)
    assert [(p.name, p.model, p.enabled) for p in providers] == [
        ("default", "qwen3:4b", True),
        ("gemini", "gf", False),
    ]
    assert providers[0].timeout == 300.0
    text = env.read_text(encoding="utf-8")
    assert "# my settings" in text and "LLM_TEMPERATURE=0.2" in text
    # Legacy keys are dropped: numbered entries would silently override them.
    assert not any(line.startswith("LLM_MODEL=") for line in text.splitlines())

    assert run("list") == 0
    out = capsys.readouterr().out
    assert "AIzaSECRETKEY1234" not in out and "AIza…1234" in out

    assert run("remove", "gemini") == 0
    assert [p.name for p in load_file_providers(env)] == ["default"]
    assert run("remove", "nope") == 2
