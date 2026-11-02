"""Chat model adapter (ADR-0002).

Any provider exposing the OpenAI Chat Completions API works by changing LLM_BASE_URL/LLM_MODEL:
Google Gemini (default, free tier), Groq (free tier) or a local Ollama server.
Several providers can be chained: when one fails the next one answers (ADR-0007).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import openai

from emporio_agent.config import LLMSettings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Provider failure (network, quota, auth). Shown to the user as a friendly message."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AssistantTurn:
    # Exact assistant message to append to the history. Kept as the provider returned it,
    # because some providers attach opaque fields to tool calls (e.g. Gemini thought signatures)
    # that must be sent back unchanged on the next request.
    message: dict[str, Any]
    tool_calls: list[ToolCall]
    model: str | None

    @property
    def content(self) -> str:
        return self.message.get("content") or ""


class ChatModel(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantTurn: ...


class OpenAICompatibleChatModel:
    def __init__(self, settings: LLMSettings, *, max_retries: int = 4) -> None:
        self._settings = settings
        # The SDK retries 429/5xx with exponential backoff; free tiers do rate-limit.
        self._client = openai.OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            max_retries=max_retries,
            timeout=settings.timeout,
        )

    @property
    def model_name(self) -> str:
        return self._settings.model

    @property
    def label(self) -> str:
        return f"{self._settings.name} ({self._settings.model})"

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantTurn:
        try:
            response = self._client.chat.completions.create(
                model=self._settings.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._settings.temperature,
                # Some providers reject an empty tool list (e.g. the admin health check).
                **({"tools": tools, "tool_choice": "auto"} if tools else {}),  # type: ignore[arg-type]
            )
        except openai.AuthenticationError as exc:
            raise LLMError(f"Invalid API key for provider {self.label}.") from exc
        except openai.RateLimitError as exc:
            raise LLMError("The model provider rate limit was reached; try again shortly.") from exc
        except openai.APIError as exc:
            raise LLMError(f"Model provider error: {exc}") from exc

        if not response.choices:
            raise LLMError("Model provider returned no choices.")
        raw = response.choices[0].message
        tool_calls = raw.tool_calls or []
        message: dict[str, Any] = {"role": "assistant", "content": raw.content}
        if tool_calls:
            message["tool_calls"] = [call.model_dump(exclude_none=True) for call in tool_calls]
        return AssistantTurn(
            message=message,
            tool_calls=[
                ToolCall(call.id, call.function.name, call.function.arguments or "{}")
                for call in tool_calls
                if call.type == "function"
            ],
            model=response.model,
        )


class FallbackChatModel:
    """Tries each provider in order; the first one that answers wins (ADR-0007).

    Fallback is per request, not per conversation: the next request starts again from the first
    provider, so a recovered primary is used again without a restart. The history is plain
    OpenAI-format messages, so a turn started on one provider can be continued on another.
    """

    def __init__(self, models: Sequence[OpenAICompatibleChatModel]) -> None:
        if not models:
            raise ValueError("FallbackChatModel needs at least one model.")
        self._models = list(models)

    @property
    def model_name(self) -> str:
        return " → ".join(m.model_name for m in self._models)

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantTurn:
        failures: list[str] = []
        for model in self._models:
            try:
                return model.complete(messages, tools)
            except LLMError as exc:
                logger.warning("LLM provider %s failed: %s", model.label, exc)
                failures.append(f"{model.label}: {exc}")
        if len(failures) == 1:
            raise LLMError(failures[0])
        raise LLMError("All LLM providers failed — " + "; ".join(failures))


def build_chat_model(chain: Sequence[LLMSettings]) -> FallbackChatModel:
    return FallbackChatModel([OpenAICompatibleChatModel(s) for s in chain])
