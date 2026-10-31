# CLAUDE.md

## Project
Prototype of a text-based customer-service agent for **Empório da Música**, a fictional
musical-instrument store in Campo Grande/MS. Technical challenge for the Artefact AI Engineer
role — brief in `desafio_tecnico_ai_eng_artefact.pdf`. Owner: Emanoel (Kotas).
Deadline: 2026-11-04 23:59 (2nd business day after 31/10; 02/11 is a holiday — confirm in the
e-mail). Nothing is changed in the repository after it.

## Stack
Python 3.12+, uv, OpenAI-compatible chat API (default: Gemini free tier), SQLite, pypdf,
pytest, ruff. Every choice is justified in `docs/adr/` — read the ADR before touching a
decision; change it with a new ADR, not silently.

## Architecture map
- `data/` — original CSVs and policy PDF. **Immutable** (files are read-only).
- `tools/` — scripts: `prepare_data.py`, `record_conversation.py`, `build_submission_pdf.py`.
- `src/emporio_agent/`
  - `ingest/` — load, check and build the generated store (`var/`, git-ignored).
  - `repositories/` — the only layer that runs SQL. Catalog opened read-only.
  - `services/` — business rules (catalog, pricing, payment, shipping, returns, store, orders,
    policies). Deterministic and unit-tested.
  - `agent/` — system prompt, tool schemas (thin adapters over services), tool-calling loop.
  - `interfaces/cli.py` — thin entry point. `app.py` is the composition root.
- `tests/` — pytest on the real data. `examples/` — recorded conversations (deliverable).
- Details: `docs/architecture.md`, `docs/data-findings.md`, `docs/adr/`.

## Commands
```bash
uv sync                                         # install
uv run python tools/prepare_data.py             # dry-run: checks + findings, writes nothing
uv run python tools/prepare_data.py --apply     # build var/emporio.db + var/policies.json
uv run pytest                                   # full suite (no LLM needed)
uv run ruff check . && uv run ruff format --check .
uv run emporio-chat [--debug] [--session ID] [--now 2026-11-03T10:00]   # needs .env
uv run python tools/record_conversation.py examples/scenarios/<file>.txt
uv run --with playwright python tools/build_submission_pdf.py           # needs pandoc
```

## Conventions
- Code, docs and commits in English; the agent speaks Brazilian Portuguese to customers.
- Money is `Decimal`; integer cents in SQL; tools return amounts pre-formatted (`R$ 1.234,56`).
- Time zone `America/Campo_Grande`; "now" comes from an injected `Clock`, never from
  `datetime.now()` inside services.
- Secrets only via environment variables (`.env`, template in `.env.example`).
- Ambiguities in data/manual are resolved by numbered conventions in `docs/data-findings.md`;
  reference them (e.g. "convention C4") in code comments.

## Principle (binding for you and any subagent)
1. **Plan before coding.** Read existing code, ADRs and `git log` first. Fix root causes, not
   symptoms. If the agreed path proves wrong, stop and decide again.
2. **Layers.** Rules in `services/`; entry layer thin; the interface only presents. Use the
   existing official path instead of ad-hoc SQL or copied logic; share functions, never
   duplicate rules. Deterministic rules (installments, shipping, PIX discount, return
   eligibility) live in tested code, never in the prompt.
3. **No hacks.** No "TEMP", "add later" or "works, not sure why". An unavoidable stopgap
   becomes an ADR with the pending item under "Open".
4. **Tests.** Every rule has a test of the real case, including the traps in
   `docs/data-findings.md`. Run the full suite before saying "done". Done means a passing
   test or a direct call — not "the button exists".
5. **Docs.** One ADR per relevant decision. Comments explain *why*, not *what*.
6. **Run/deploy.** Build and run in sequence and verify; report what was not verified.
   "Deploy" here = running from scratch, following the README, in a clean environment.
7. **Data.** `data/` is immutable. Cleaning produces a reproducible copy via script,
   dry-run by default, `--apply` explicit, with a log of what changed. The agent never writes
   to source data.
8. **Scale.** Think about real volume (300+ catalog items, many customers), not only the
   65 products in the CSV.
9. **Git.** Never commit or push unless asked. When asked: small, frequent commits showing
   real progress; no single squashed commit, no force-push, nothing after the deadline.
   Migrations only on explicit request.
10. **Never invent business rules** (price, lead time, policy, legal). If it is not in the
    data or the manual, ask. Same for the agent: without information it says it doesn't
    know and hands off to a human attendant.
