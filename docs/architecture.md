# Architecture

## Layers

```
interfaces/cli.py ──► agent/loop.py ──► agent/tools.py ──► services/* ──► repositories/* ──► var/emporio.db (read-only)
   (I/O only)         (LLM ⇄ tools)     (validate, format)   (rules)        (SQL only)       var/policies.json
                           │
                           └──► agent/llm.py ──► any OpenAI-compatible endpoint (Gemini / Groq / Ollama)

tools/prepare_data.py ──► ingest/* : data/ (immutable) ──► checks ──► var/ (generated, git-ignored)
```

| Layer | Responsibility | Must not |
|---|---|---|
| `interfaces/` | Read input, call the agent, print, persist the turn | Contain rules or SQL |
| `agent/loop.py` | Send history + tools to the model, execute tool calls, stop at a round limit | Compute anything about prices or dates |
| `agent/tools.py` | JSON schemas, argument validation, call services, format money/dates for the model | Implement business rules |
| `services/` | Deterministic rules: availability, pricing, installments, shipping, returns, hours, identification | Talk to the LLM or format for chat |
| `repositories/` | Parameterized SQL, indexes, mapping rows to domain records | Contain rules |
| `ingest/` | Typed loading, data-quality checks, PDF section extraction, atomic build | Modify source files |

`app.py` is the composition root: it wires everything, so tests can swap the model (scripted
fake) or the clock (fixed date) without touching code.

## Request flow (example: "Quanto custa o Takamine GD20?")
1. CLI loads the session history and calls `Agent.respond`.
2. The loop sends system prompt (persona, guardrails, current date) + history + 8 tool schemas.
3. The model calls `get_product(name="Takamine GD20")`.
4. The tool resolves the name in `CatalogRepository.find_by_name` (accent/punctuation-insensitive
   key), asks `pricing.quote_price` and `payment.installment_options`, and returns
   `{"price": "R$ 2.199,00", "pix_price": "R$ 2.089,05", "installments": {...},
   "expired_promotions": [...]}`.
5. The model writes the answer in Portuguese copying those strings; the turn is persisted.

## Tools
| Tool | Services | Notes |
|---|---|---|
| `search_products` | catalog | category enum built from the DB, text, price range on the effective price, paginated (max 20) |
| `get_product` | catalog, pricing, payment | by id or name; alternatives when unavailable; expired promotions listed as ended |
| `quote_purchase` | quote → pricing, payment, shipping | cart totals, PIX per item, installments, combined payment, shipping by city |
| `lookup_orders` | orders | identification required (LGPD) |
| `check_return_eligibility` | orders, returns | regret / defect / preference windows |
| `get_policy` | policies | exact manual section by topic |
| `get_store_info` | store | contact convention, hours, open now, next opening (holidays) |
| `handoff_to_human` | conversations | records the case; complaint response time |

## Persistence
- `var/emporio.db` — generated catalog, opened with SQLite `mode=ro`.
- `var/conversations.db` — sessions, messages (OpenAI message format, including tool calls)
  and hand-offs. Separate file so rebuilding the catalog never touches conversations.

## Scale considerations
- Search, filters, ordering and pagination run in SQL with indexes on
  `(category_id, status, price_cents)`; the prompt never receives the catalog. The same code
  serves 65 or 30,000 products. Beyond that, the `LIKE` text match would move to SQLite FTS5
  or a search engine without changing the service interface.
- Customer and order lookups are by indexed key; no full scans, no listings.
- Policies are retrieved by topic, so prompt size does not grow with the manual.
- History sent to the model is bounded (40 messages, cut at a user turn) to keep cost and
  latency predictable in long conversations.
- SQLite fits a single-process prototype. A multi-user API would move to PostgreSQL behind the
  same repository interfaces.
