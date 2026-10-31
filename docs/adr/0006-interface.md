# ADR-0006: Interface — terminal chat
- Status: Accepted
- Date: 2026-10-31
- Decided by: Emanoel (delegated to Claude Code, reviewed by Emanoel)

## Context
The brief prioritizes a working agent over UI. Evaluators must run it quickly, and the example
conversations must be reproducible.

## Decision
- Interactive CLI (`uv run emporio-chat`) using only the standard library: `--debug` shows tool
  calls and results, `--session` resumes, `--now` simulates a date/time (useful to check opening
  hours or return windows).
- `tools/record_conversation.py` runs scripted scenarios through the same agent to produce the
  transcripts in `examples/`.
- The CLI is a thin entry point over `app.build_application`; an HTTP API (FastAPI) or a
  WhatsApp webhook would be another thin adapter over the same object.

## Consequences
+ Zero extra dependencies; works over SSH; transcripts reproducible.
− No web UI. A FastAPI endpoint is listed under "With more time".

## Where
`src/emporio_agent/interfaces/cli.py`, `src/emporio_agent/app.py`, `tools/record_conversation.py`.

## Origin
Challenge brief ("Interface de interação").
