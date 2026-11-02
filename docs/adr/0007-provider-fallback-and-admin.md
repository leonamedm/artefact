# ADR-0007: Several LLM providers with automatic fallback, managed from a terminal admin panel
- Status: Accepted
- Date: 2026-10-31
- Decided by: Emanoel (requirement: register several APIs, fall back when one fails, admin
  panel to switch models) / Claude Code (design)

## Context
ADR-0002 configures exactly one OpenAI-compatible provider. In practice a single provider is a
single point of failure: free tiers rate-limit or go down, and a local model may not fit the
machine (on the owner's 8 GB Apple M1, `qwen3:8b` could not load; `qwen3:4b` loads fully on the
GPU but needs ~40 s per request with thinking on — above the fixed 60 s timeout once the
model has to load). The owner asked for several registered APIs, automatic fallback, and an
admin panel to switch models. The brief accepts CLI, notebook, API or simple UI.

## Decision
- **Registry in `.env`.** Providers are numbered variables `LLM_<n>_NAME|BASE_URL|MODEL|API_KEY|
  TIMEOUT|ENABLED`; `n` is the fallback order. Secrets stay in `.env` (CLAUDE.md convention).
  Without numbered variables the single ADR-0002 set (`LLM_BASE_URL`, `LLM_MODEL`,
  `LLM_API_KEY`) still works unchanged. `emporio_agent/providers.py` is the only code that
  reads or rewrites these entries.
- **Fallback per request.** `FallbackChatModel` tries the enabled providers in order; any
  `LLMError` (network, timeout, auth, rate limit after the SDK's retries, 5xx) moves to the
  next one. Each request starts again from the first provider, so a recovered primary is used
  again without a restart. History is plain OpenAI-format messages, so a turn can continue on
  another provider. When all fail, the error lists every provider's failure and the CLI asks
  the customer to resend (unchanged behaviour).
- **Per-provider timeout** (`LLM_<n>_TIMEOUT`, default `LLM_TIMEOUT` = 60 s): hosted APIs keep a
  short timeout so fallback is quick; local models get a long one.
- **Admin panel in the terminal** (`uv run emporio-admin`): `list`, `test` (health check, no
  retries, shows latency), `add`, `set` (e.g. change model), `enable`/`disable`, `move` (order),
  `remove`. It rewrites only the provider entries and preserves every other line of `.env`;
  keys are masked in the output. `emporio-chat` and the recorder accept `--provider NAME|N` to
  force one provider (no fallback) for a run.
- Transcripts record the model actually served and the provider chain.

## Consequences
+ No single point of failure; a free hosted tier can back up a local model and vice versa.
+ Switching models is one command, persisted, and testable before use (`emporio-admin test`).
+ No new dependencies; same composition root and agent loop.
− A provider that hangs costs its timeout (× SDK retries) before fallback; keep hosted timeouts
  short.
− Answers within one conversation may come from different models after a fallback; the
  transcript/debug output shows which.
− A terminal panel, not a web UI: a web panel would be another thin adapter over
  `providers.py` (see "With more time").

## Where
`src/emporio_agent/providers.py`, `src/emporio_agent/agent/llm.py` (`FallbackChatModel`),
`src/emporio_agent/interfaces/admin.py`, `src/emporio_agent/config.py`, `.env.example`,
`tests/test_providers.py`.

## Origin
Owner request (2026-10-31): register several APIs, fall back automatically, admin panel to
switch models. Extends ADR-0002 (single provider by configuration), which stays valid as the
legacy form.
