# ADR-0005: Conversation persistence — SQLite sessions
- Status: Accepted
- Date: 2026-10-31
- Decided by: Emanoel (delegated to Claude Code, reviewed by Emanoel)

## Context
Multi-turn context matters: the customer identifies themselves, then asks follow-ups; a return
flow spans several messages. Customer service is also asynchronous (WhatsApp), so resuming a
conversation later is realistic. Hand-offs to humans need to be recorded somewhere.

## Decision
- `var/conversations.db` (SQLite) with `sessions`, `messages` and `handoffs`. Messages are
  stored in the exact OpenAI message format, including tool calls and tool results, so a
  resumed session gives the model the same context.
- The CLI creates a session per run and prints its id; `--session ID` resumes it.
- The history sent to the model is bounded (last 40 messages, cut at a user message so no tool
  result is orphaned).
- A failed model call is not persisted, so the customer can just resend.
- Identification is not cached between turns: every order lookup carries its own proof
  (LGPD data minimization). The transcript itself does contain what the customer typed.

## Consequences
+ Resumable conversations and an audit trail of what the agent saw and answered.
+ Hand-offs are queryable by the team.
− No retention policy or deletion endpoint yet (LGPD right to erasure, manual §9) — listed in
  "With more time".
− Single-process SQLite; a multi-user deployment would use PostgreSQL.

## Where
`src/emporio_agent/repositories/conversations.py`, `src/emporio_agent/agent/loop.py`
(`trim_history`), `src/emporio_agent/interfaces/cli.py`.

## Origin
Challenge brief ("Persistência do histórico de conversa").
