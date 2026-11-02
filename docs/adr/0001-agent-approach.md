# ADR-0001: Agent approach — native tool calling over deterministic services
- Status: Accepted
- Date: 2026-10-31
- Decided by: Emanoel (delegated to Claude Code, reviewed by Emanoel)

## Context
The agent must decide between data questions (price, stock, orders) and policy questions, and
must never state prices, stock or deadlines without querying the system (manual §7.1). Many
rules are arithmetic or calendar logic — installment tiers, PIX discount vs promotions,
shipping threshold, 7/30/90-day windows, opening hours with holidays. LLMs are unreliable at
exactly this, and the cost of a wrong answer is "propaganda enganosa" (manual §7.1).

Options considered:
- **Text-to-SQL agent**: flexible, but the model writes queries over personal data (LGPD risk),
  can bypass rules and is hard to test.
- **Pure RAG over everything**: retrieves text, but still leaves arithmetic to the model.
- **Framework agent (LangChain/LlamaIndex/LangGraph)**: adds abstractions and dependencies
  for a single agent with 8 tools; harder to read in a code review.
- **Native function calling + deterministic services** (chosen).

## Decision
A single agent using the provider's native function calling, with a hand-written loop
(~60 lines). Tools are thin adapters over `services/`, which hold every rule in plain,
unit-tested Python. The model routes, asks clarifying questions and phrases the answer; it
never computes money or dates. Tool results return amounts already formatted (`R$ 1.234,56`)
so the model copies instead of reformatting.

Guardrails in depth: identification enforced in code (not only in the prompt), unavailable
products returned without price, expired promotions labelled as ended, a tool-round limit with
a hand-off fallback, and tool errors returned to the model instead of crashing the turn.

## Consequences
+ Rules are testable without an LLM (96 tests run offline in seconds).
+ The model cannot leak data it cannot query, nor promise discounts the services don't return.
+ Few dependencies; the whole loop is readable in one file.
− New capabilities need a new tool, not just a prompt change.
− Quality of routing still depends on the model; covered by recorded example conversations,
  not by automated LLM evaluation (see README, "With more time").

## Where
`src/emporio_agent/agent/`, `src/emporio_agent/services/`.

## Origin
Challenge brief ("Decisões Técnicas"); manual §6.2, §7.1, §7.3.
