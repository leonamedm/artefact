# ADR-0002: Model and provider — free tier via an OpenAI-compatible API
- Status: Accepted
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
Default: Gemini free tier with the `gemini-flash-latest` alias. Groq and Ollama are documented
alternatives in `.env.example` — switching is configuration, not code.

The adapter keeps the assistant message exactly as returned (including provider-specific fields
such as Gemini thought signatures on tool calls) because they must be echoed back in the next
request. SDK retries with backoff handle free-tier 429s; persistent failures surface as a
friendly message and the turn is not persisted.

Temperature 0.2: answers must follow tool results, not be creative.

## Consequences
+ Zero cost; any evaluator can get a key in a minute, or run fully offline with Ollama.
+ Provider lock-in avoided: one adapter, three documented providers selected by configuration.
− `-latest` alias trades reproducibility for availability (pinned versions get retired);
  transcripts record the model actually served. Pin a version in `.env` for stable runs.
− Free tiers have rate limits and, for Gemini, data-usage terms: fine for fictional data, not
  for real customers — production would use a paid tier or a self-hosted model.
− Which providers were actually exercised end-to-end is stated in the README ("Verification").

## Where
`src/emporio_agent/agent/llm.py`, `src/emporio_agent/config.py`, `.env.example`.

## Origin
Challenge brief ("Modelo e Provedor"); owner requirement of no paid API.
