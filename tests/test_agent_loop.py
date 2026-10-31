from __future__ import annotations

import json
from typing import Any

from emporio_agent.agent.llm import AssistantTurn, ToolCall
from emporio_agent.agent.loop import FALLBACK_REPLY, Agent, trim_history
from emporio_agent.clock import FixedClock
from tests.conftest import NOW


class ScriptedModel:
    """Fake chat model returning pre-defined turns, recording what it was sent."""

    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = list(turns)
        self.requests: list[list[dict[str, Any]]] = []

    def complete(self, messages, tools):
        self.requests.append(messages)
        return self._turns.pop(0)


def tool_turn(call_id: str, tool: str, **arguments) -> AssistantTurn:
    raw = json.dumps(arguments)
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": tool, "arguments": raw},
                "extra_content": {"google": {"thought_signature": "opaque"}},
            }
        ],
    }
    return AssistantTurn(message, [ToolCall(call_id, tool, raw)], "fake-model")


def text_turn(text: str) -> AssistantTurn:
    return AssistantTurn({"role": "assistant", "content": text}, [], "fake-model")


def test_tool_result_is_fed_back_and_reply_returned(tools):
    model = ScriptedModel(
        [
            tool_turn("c1", "get_product", name="Takamine GD20"),
            text_turn("O Takamine GD20 sai por R$ 2.199,00."),
        ]
    )
    result = Agent(model, tools, FixedClock(NOW)).respond([], "Quanto custa o Takamine GD20?")

    assert result.reply == "O Takamine GD20 sai por R$ 2.199,00."
    assert [m["role"] for m in result.messages] == ["user", "assistant", "tool", "assistant"]
    tool_message = result.messages[2]
    assert tool_message["tool_call_id"] == "c1"
    assert json.loads(tool_message["content"])["price"] == "R$ 2.199,00"
    # Provider-specific fields on tool calls are sent back untouched.
    second_request = model.requests[1]
    assert second_request[2]["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
    assert second_request[0]["role"] == "system"
    assert "31/10/2026" in second_request[0]["content"]


def test_tool_errors_do_not_break_the_turn(tools):
    model = ScriptedModel(
        [
            tool_turn("c1", "lookup_orders", order_id=8),  # missing identification
            text_turn("Preciso do e-mail ou telefone da compra."),
        ]
    )
    result = Agent(model, tools, FixedClock(NOW)).respond([], "Cadê meu pedido 8?")
    assert "error" in result.traces[0].result
    assert result.reply.startswith("Preciso")


def test_round_limit_returns_fallback(tools):
    model = ScriptedModel([tool_turn(f"c{i}", "get_store_info") for i in range(3)])
    agent = Agent(model, tools, FixedClock(NOW), max_tool_rounds=3)
    result = agent.respond([], "Oi")
    assert result.reply == FALLBACK_REPLY
    assert result.messages[-1] == {"role": "assistant", "content": FALLBACK_REPLY}


def test_empty_model_reply_falls_back(tools):
    result = Agent(ScriptedModel([text_turn("  ")]), tools, FixedClock(NOW)).respond([], "Oi")
    assert result.reply == FALLBACK_REPLY


def test_trim_history_never_starts_with_orphan_tool_message():
    history = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "tool_call_id": "x", "content": "{}"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b"},
    ]
    trimmed = trim_history(history, 4)
    assert trimmed[0] == {"role": "user", "content": "2"}
    assert trim_history(history, 10) == history
