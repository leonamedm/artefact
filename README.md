# Empório da Música — Customer Service Agent

Prototype of a text-based customer-service agent for **Empório da Música**, a fictional
musical-instrument store in Campo Grande/MS, built for the Artefact AI Engineer technical
challenge.

The agent chats in Brazilian Portuguese with the store's tone (informal but professional,
"a friend who knows music") and:

- queries **live data** for prices, promotions, stock and order status, and **policies** for
  returns, hours, payment, shipping and warranty — choosing by itself which tool to call;
- applies the store's rules **in tested code, not in the prompt**: installment tiers, PIX
  discount vs. promotions, shipping threshold, 7/30/90-day return windows, opening hours with
  holidays;
- never states a price, stock level or deadline without querying the system;
- only shows order data to the identified customer (LGPD);
- politely declines what is out of scope (the store sells instruments only — no strings,
  picks, cables, cases, pedals or amplifiers) and hands off to a human when it doesn't know.

---

## Quick start

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
No paid API: the default model is Google Gemini's **free tier** (no credit card).

```bash
git clone https://github.com/leonamedm/artefact.git
cd artefact
uv sync
```

1. **Get a free API key** at <https://aistudio.google.com/apikey> and configure it:

   ```bash
   cp .env.example .env
   # edit .env and set LLM_API_KEY=<your key>
   ```

   Prefer Groq or a fully local Ollama model? Uncomment the matching block in `.env.example` —
   it is only configuration. Several providers can be registered with **automatic fallback**
   (if one fails, the next answers) and managed from the terminal admin panel:

   ```bash
   uv run emporio-admin list                  # providers in fallback order (keys masked)
   uv run emporio-admin test                  # health check of every enabled provider
   uv run emporio-admin add ollama --base-url http://localhost:11434/v1 \
       --model qwen3:4b --api-key ollama --timeout 300
   uv run emporio-admin set ollama --model qwen3:8b    # switch model
   uv run emporio-admin move ollama 1 | disable NAME | enable NAME | remove NAME
   ```

   `uv run emporio-chat --provider NAME` forces a single provider for one run.

2. **Build the store data** from the original files (dry-run first, then apply):

   ```bash
   uv run python tools/prepare_data.py           # validates, prints findings, writes nothing
   uv run python tools/prepare_data.py --apply   # builds var/emporio.db and var/policies.json
   ```

3. **Chat:**

   ```bash
   uv run emporio-chat            # add --debug to see every tool call and result
   ```

   Other options: `--session <id>` resumes a saved conversation; `--now 2026-11-03T10:00`
   simulates the current date/time (e.g. to test opening hours or return windows).

4. **Run the tests** (offline, no API key needed):

   ```bash
   uv run pytest
   uv run ruff check . && uv run ruff format --check .
   ```

Try: *"Quais violões vocês têm até R$ 1000?"*, *"Quanto custa o Takamine GD20?"*,
*"Quero saber do meu pedido 8"* (phone `(67) 99654-7821`), *"Me arrependi da compra, posso
devolver?"*, *"Vocês vendem amplificador?"*.

---

## Project layout

```
data/                 original CSVs + policy PDF, untouched (read-only)
tools/                prepare_data.py · record_conversation.py · build_submission_pdf.py
src/emporio_agent/
  ingest/             typed loading, data-quality checks, PDF section extraction, build
  repositories/       SQL only (catalog opened read-only; conversations DB)
  services/           business rules: catalog, pricing, payment, shipping, returns, store, orders
  agent/              system prompt, tool schemas, tool-calling loop, LLM adapter
  interfaces/cli.py   terminal chat (thin)
  app.py              composition root
tests/                84 tests on the real data, incl. every data trap
examples/             recorded conversations (+ scenarios/ that generate them)
docs/                 architecture.md · data-findings.md · adr/
```

Details: [docs/architecture.md](docs/architecture.md).

---

## Technical decisions

Full reasoning, alternatives and trade-offs are in the ADRs ([index](docs/adr/README.md)).

| Decision | Choice | Why (short) |
|---|---|---|
| Agent approach | Native **function calling** + deterministic services, hand-written loop, no framework — [ADR-0001](docs/adr/0001-agent-approach.md) | The model routes and phrases; code computes. Rules become testable, the model can't promise what the services don't return, and 8 tools don't justify LangChain's abstractions. Text-to-SQL rejected (LGPD, bypasses rules). |
| Model & provider | **Gemini free tier** (`gemini-3.5-flash-lite`) via the **OpenAI-compatible API**; Groq / Ollama by config — [ADR-0002](docs/adr/0002-model-and-provider.md) | Zero cost, strong tool calling and Portuguese, generous token limits for a tool-heavy prompt; no lock-in. |
| Policy retrieval | **Topic-indexed manual sections**, no vector store — [ADR-0003](docs/adr/0003-policy-retrieval.md) | 8 pages, 10 clean sections: exact section retrieval is deterministic and testable; embeddings would add infra and risk returning half a rule. |
| Data treatment | Immutable sources → **reproducible SQLite build** with checks, dry-run by default — [ADR-0004](docs/adr/0004-data-treatment.md) | Evaluators see the original data; anomalies are reported, never silently "fixed"; indexed queries scale past the 65-product CSV. |
| Persistence | **SQLite sessions** (resumable), bounded history window — [ADR-0005](docs/adr/0005-conversation-persistence.md) | Multi-turn flows (identify → ask) and asynchronous customer service; audit trail of hand-offs. |
| Interface | **Terminal chat** + transcript recorder — [ADR-0006](docs/adr/0006-interface.md) | Focus on the agent; zero UI dependencies; API/WhatsApp would be another thin adapter. |
| Provider fallback | **Numbered providers in `.env`**, tried in order per request; terminal admin panel `emporio-admin` — [ADR-0007](docs/adr/0007-provider-fallback-and-admin.md) | No single point of failure (rate limits, outages, a local model that does not fit); switching models is one command; secrets stay in `.env`. |

### Prompt strategy

- **The prompt holds persona and guardrails; numbers live in code.** The system prompt
  ([agent/prompt.py](src/emporio_agent/agent/prompt.py)) defines voice, scope, grounding rules,
  privacy and hand-off. It contains no prices, fees or deadlines to memorize.
- **Grounding by construction.** Tools return amounts already formatted (`R$ 1.234,56`) and
  computed (promotional price, PIX price, installments, return deadline); the prompt tells the
  model to copy them and never do arithmetic.
- **Rules the model can't break are enforced in tools,** not only stated in the prompt:
  identification before order data, no price for discontinued/coming-soon items, expired
  promotions explicitly labelled as ended, page-size caps.
- **Tool descriptions are part of the prompt**: each says when to use it ("call it before
  stating any price"), and the category enum is built from the database.
- **Current date/time** (Campo Grande time zone) is injected each turn, so "are you open?"
  and return windows are answered from a clock the tests can fix.
- **Low temperature (0.2)** and a **tool-round limit** with a hand-off fallback.

---

## Data treatment and assumptions

The data and the manual contain traps and contradictions. Each one is detected by
`prepare_data.py`, handled by a tested rule or a documented convention, and listed in
**[docs/data-findings.md](docs/data-findings.md)**. Highlights:

- **Status wins over stock**: discontinued product 136 still has 13 units and coming-soon 130
  has 2 — neither is offered; out-of-stock items get alternatives.
- **Only 4 of 25 promotions are active**; expired ones are never applied and are reported as
  ended. Promotional prices always come with original price and %. PIX 5% never stacks on a
  promotion.
- **Orders**: 20 orders, 12 without tracking (not dispatched); order 8 is `shipped` and past its
  ETA → flagged and handed off; totals of orders 3 and 20 differ from items at current prices →
  the recorded total is reported, never recomputed.
- **Contact details conflict in the manual** → convention: phone (67) 3341-4444, WhatsApp
  (67) 3321-4500, e-mail `contato@emporiodamusica.com.br` (rationale in data-findings, C1/C2).
- **Ambiguous rules** resolved by numbered conventions (e.g. C4: 2–3x installments must be
  ≥ R$ 50 each; C5: only the city of Campo Grande counts as metropolitan region; C6: exactly
  R$ 500 does not get free shipping) and listed as open items to confirm with the store.
- **Assumptions**: orders in the system are online purchases (regret right applies); the
  receipt date is asked to the customer (the ETA is never used as receipt date).
- **LGPD**: order data only with order id + phone/e-mail on file (or phone + e-mail); failures
  are indistinguishable; no query lists customers.

---

## Example conversations

Five transcripts in [examples/](examples/README.md), generated by
`tools/record_conversation.py` from the scripts in `examples/scenarios/` — answers are not
edited. They cover catalog search with a price filter, price with an expired promotion and
payment conditions, order status with identification and a delay hand-off, a return request
applying the 7/30/90-day rules, and out-of-scope requests plus opening hours.

---

## Verification

- `uv run pytest`: **84 tests pass** offline — rules on the real data (pricing, installments,
  shipping, returns, hours/holidays, identification), ingestion and source immutability, tool
  validation/formatting, and the agent loop with a scripted fake model (including echoing
  provider-specific tool-call fields).
- `ruff check` and `ruff format --check` clean.
- Fresh-clone run of the README steps: `uv sync` → `prepare_data.py` → `--apply` →
  `emporio-chat`.
- Provider registry, fallback order and the admin panel's `.env` editing are covered by
  `tests/test_providers.py` with fake models (no network); `emporio-admin add/set/list` were
  also run directly against a real `.env`.
- End-to-end with a real model on the owner's machine (Apple M1, 8 GB RAM, Ollama 0.40):
  - **Ollama `qwen3:8b` failed:** the 5 GB model did not fit the free memory (30/37 layers on
    the GPU, no swap); Ollama aborted with `timed out waiting for llama-server to start`, and
    the agent's former fixed 60 s timeout cancelled each load attempt. Not used.
  - **Ollama `qwen3:4b`** loads fully on the GPU (3.2 GB, ~16 tokens/s, ~40 s for the first
    tool call with thinking on). It is configured as the provider (timeout 300 s), but the
    example conversations have **not yet been re-recorded with it**; the transcripts'
    "Model served" line shows which model produced each one.
  - Gemini and Groq are supported by configuration but were not exercised.

---

## Known limitations

- **LLM behaviour is validated by recorded examples, not by an automated evaluation suite.**
  Routing mistakes (wrong tool, unnecessary questions) are possible, especially on small models.
- **Free tiers rate-limit** (requests/tokens per minute); long sessions can hit a 429. The SDK
  retries with backoff, then the CLI asks to resend.
- **Shipping outside Campo Grande** has no price (the store quotes by CEP; no carrier API).
- **Identification is knowledge-based** (order id + phone/e-mail), adequate for a prototype,
  not strong authentication.
- **No retention policy / erasure endpoint** for stored conversations (LGPD right to erasure).
- Text search is `LIKE`-based on accent-free keys (fine for hundreds of products; FTS5 or a
  search engine for much larger catalogs). No plural/synonym handling ("violões" vs "violão" is
  covered by the category filter, not by text search).
- Holidays: national + Mato Grosso do Sul only; municipal holidays and extended special-date
  hours are not in the data.
- Single-process SQLite; one CLI user at a time.

## What I would do with more time

1. **Automated agent evals**: a scenario suite run against the real model in CI, with
   assertions on tool calls (right tool, right arguments) and on the answer (amounts match tool
   output, promo shown with original + %, no invented contact), plus an LLM-as-judge for tone.
2. **FastAPI endpoint + WhatsApp webhook** as thin adapters over `build_application`; PostgreSQL
   behind the same repositories for concurrent sessions. A web version of the provider admin
   panel would be another thin adapter over `providers.py`.
3. **Real shipping quotes** (Correios/Jadlog APIs by CEP) and stock reservation in the cart.
4. **Stronger identification** (one-time code via WhatsApp/e-mail) and LGPD tooling: retention
   window, erasure on request, PII redaction in logs.
5. **Observability**: structured logs per turn (latency, tokens, tools, hand-off rate) and a
   dashboard of unanswered questions to feed the catalog and the manual.
6. **Hybrid retrieval** (BM25 + embeddings) only if the policy corpus grows beyond one manual.
7. Resolve the open items with the store (O1–O5 in data-findings).

---

## Use of AI coding assistants

I used **Claude Code** (Anthropic's agentic CLI) as a pair-programmer under explicit
engineering rules, not as free-form "vibe coding". My workflow:

1. **Rules first.** Before any code I wrote a `CLAUDE.md` with the project map and a binding
   engineering principle: layered architecture, deterministic rules in tested code (not in the
   prompt), immutable source data with dry-run-by-default scripts, no invented business rules,
   and no commits without my approval. `.claude/settings.json` enforces part of it (writes to
   `data/` and reading `.env` are denied; commits/pushes require confirmation).
2. **Data audit before design.** I listed the traps I had found in the data and asked Claude Code
   to inspect everything independently; it corrected my count (20 orders, not 19) and found
   issues I had missed — order totals that don't match their items, a discontinued product with
   stock, a coming-soon product in a delivered order, empty categories, and contradictions
   inside the manual (minimum installment, defect window counted from purchase vs receipt).
   These became `docs/data-findings.md` with numbered conventions.
3. **Proposal → review → decision.** Claude Code proposed the repository structure and the full
   content of each file before writing; decisions were recorded as ADRs. I set the constraints
   (e.g. no paid LLM API) and delegated the technical choices, reviewing the reasoning.
4. **Tests as the acceptance criterion.** Every rule has a test on the real case; the suite runs
   offline. When a test failed, the rule was checked against the data before deciding whether
   the code or the test was wrong (one test assertion was wrong — a product priced R$ 1.899 is
   not inside a R$ 1.900–2.000 filter — and the test was fixed, not the code).
5. **Repeated procedures as skills.** Recording example conversations became a Claude Code
   skill (`.claude/skills/record-example-conversation`), so transcripts are always generated by
   the real agent and checked against the data, never hand-edited.
6. **Small commits** with real progress history, made only when I asked.

What I corrected or steered: keeping the agent provider-agnostic, keeping LGPD identification in
code instead of trusting the prompt, and refusing to guess undefined rules (they are listed as
conventions and open questions instead).

---

## Documentation

- [docs/architecture.md](docs/architecture.md) — layers, request flow, tools, scale.
- [docs/data-findings.md](docs/data-findings.md) — every data/manual trap and how it is handled.
- [docs/adr/](docs/adr/README.md) — architecture decision records.
- [CLAUDE.md](CLAUDE.md) — instructions and engineering principle used with Claude Code.
