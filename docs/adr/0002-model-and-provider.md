# ADR-0002: Model and provider — free tier via an OpenAI-compatible API
- Status: Accepted (amended 2026-11-02: default model)
- Date: 2026-10-31
- Decided by: Emanoel (requirement: no paid API) / Claude Code (provider choice)

## Context
Requirements: no paid API (owner's constraint), reliable tool calling, good Brazilian
Portuguese, and evaluators able to run it in minutes. Free options in late 2026:
- **Google Gemini API free tier** — no credit card, Flash models with strong tool calling and
  Portuguese; generous tokens-per-minute; OpenAI-compatible endpoint. Free-tier prompts may be
  used by Google to improve products.
- **Groq free tier** — no credit card, fast open models (Llama 3.3 70B); tokens-per-minute limits
  are tight for a tool-calling prompt (~3–4k tokens per request).
- **Ollama (local)** — free, offline, private; needs a multi-GB download and a decent machine,
  and small local models are weaker at tool calling in Portuguese.

## Decision
Talk to the model through the OpenAI Chat Completions protocol with the official `openai`
SDK, configured only by environment variables (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`).
Default: Gemini free tier with the pinned `gemini-3.5-flash-lite` model. Groq and Ollama are documented
alternatives in `.env.example` — switching is configuration, not code.

The adapter keeps the assistant message exactly as returned (including provider-specific fields
such as Gemini thought signatures on tool calls) because they must be echoed back in the next
request. SDK retries with backoff handle free-tier 429s; persistent failures surface as a
friendly message and the turn is not persisted.

Temperature 0.2: answers must follow tool results, not be creative.

## Consequences
+ Zero cost; any evaluator can get a key in a minute, or run fully offline with Ollama.
+ Provider lock-in avoided: one adapter, three documented providers selected by configuration.
− Pinned model, because the `gemini-flash-latest` alias returned 403 for a new free-tier key
  (2026-11-02) and `gemini-3.5-flash` returned 503 under load. Pinned versions get retired, so
  `LLM_MODEL` stays configurable; transcripts record the model actually served.
− Free-tier calls occasionally fail with 403/503; the SDK retries 429/5xx, and a failed turn is
  not persisted so it can be resent.
− Free tiers have rate limits and, for Gemini, data-usage terms: fine for fictional data, not
  for real customers — production would use a paid tier or a self-hosted model.
− Which providers were actually exercised end-to-end is stated in the README ("Verification").

## Where
`src/emporio_agent/agent/llm.py`, `src/emporio_agent/config.py`, `.env.example`.

## Origin
Challenge brief ("Modelo e Provedor"); owner requirement of no paid API.
