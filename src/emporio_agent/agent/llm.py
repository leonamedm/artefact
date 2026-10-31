"""Chat model adapter (ADR-0002).

Any provider exposing the OpenAI Chat Completions API works by changing LLM_BASE_URL/LLM_MODEL:
Google Gemini (default, free tier), Groq (free tier) or a local Ollama server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import openai

from emporio_agent.config import LLMSettings


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
    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        # The SDK retries 429/5xx with exponential backoff; free tiers do rate-limit.
        self._client = openai.OpenAI(
            base_url=settings.base_url, api_key=settings.api_key, max_retries=4, timeout=60
        )

    @property
    def model_name(self) -> str:
        return self._settings.model

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantTurn:
        try:
            response = self._client.chat.completions.create(
                model=self._settings.model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=self._settings.temperature,
            )
        except openai.AuthenticationError as exc:
            raise LLMError("Invalid LLM_API_KEY for the configured provider.") from exc
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
