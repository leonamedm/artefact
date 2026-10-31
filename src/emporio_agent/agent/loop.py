"""Tool-calling loop: model -> tools -> model, until a text answer or the round limit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from emporio_agent.agent.llm import ChatModel
from emporio_agent.agent.prompt import build_system_prompt
from emporio_agent.agent.tools import ToolRegistry
from emporio_agent.clock import Clock

FALLBACK_REPLY = (
    "Putz, não consegui concluir sua solicitação agora. Posso te encaminhar para um dos nossos "
    "atendentes, tudo bem?"
)


@dataclass(frozen=True)
class ToolTrace:
    name: str
    arguments: str
    result: dict[str, Any]


@dataclass
class TurnResult:
    reply: str
    messages: list[dict[str, Any]]  # new messages of this turn, to persist
    traces: list[ToolTrace] = field(default_factory=list)
    model: str | None = None


def trim_history(history: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    """Keep the most recent messages, starting at a user message so no tool result is orphaned
    from the assistant call that produced it."""
    if len(history) <= max_messages:
        return list(history)
    window = history[-max_messages:]
    for index, message in enumerate(window):
        if message.get("role") == "user":
            return window[index:]
    return []


class Agent:
    def __init__(
        self,
        model: ChatModel,
        tools: ToolRegistry,
        clock: Clock,
        *,
        max_tool_rounds: int = 6,
        max_history_messages: int = 40,
    ) -> None:
        self._model = model
        self._tools = tools
        self._clock = clock
        self._max_tool_rounds = max_tool_rounds
        self._max_history = max_history_messages

    def respond(self, history: list[dict[str, Any]], user_text: str) -> TurnResult:
        system = {"role": "system", "content": build_system_prompt(self._clock.now())}
        context = trim_history(history, self._max_history)
        new: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
        traces: list[ToolTrace] = []
        model_name: str | None = None
        schemas = self._tools.schemas()

        for _ in range(self._max_tool_rounds):
            turn = self._model.complete([system, *context, *new], schemas)
            model_name = turn.model or model_name
            new.append(turn.message)
            if not turn.tool_calls:
                reply = turn.content.strip() or FALLBACK_REPLY
                return TurnResult(reply, new, traces, model_name)
            for call in turn.tool_calls:
                result = self._tools.execute(call.name, call.arguments)
                traces.append(ToolTrace(call.name, call.arguments, result))
                new.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        # Too many tool rounds: stop instead of looping and spending quota.
        new.append({"role": "assistant", "content": FALLBACK_REPLY})
        return TurnResult(FALLBACK_REPLY, new, traces, model_name)
