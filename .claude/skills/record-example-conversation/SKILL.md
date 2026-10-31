---
name: record-example-conversation
description: Record a sample conversation with the real agent into examples/ as Markdown. Use when creating or refreshing the 3–5 example conversations required by the challenge.
---

# Record an example conversation

Purpose: reproducible, real transcripts — never hand-written or edited answers.

## Steps
1. Pick a scenario not yet covered (see coverage below). Write it as
   `examples/scenarios/NN-slug.txt`: `# title:`, `# scenario:`, optional `# now: <ISO>` to fix
   the agent clock, then one customer message per line.
2. Make sure `var/` is built (`uv run python tools/prepare_data.py --apply`) and `.env` has a
   working provider.
3. Run `uv run python tools/record_conversation.py examples/scenarios/NN-slug.txt`.
4. Check the transcript against the data: every price, promotion, stock level and order status
   must match the source; every policy statement must match the manual; no invented facts.
5. If an answer is wrong, fix the cause (service, tool or prompt), run `uv run pytest`, and
   re-record. Never edit the agent's text by hand.
6. Update the table in `examples/README.md`.

## Coverage to keep (at least one non-trivial)
- Catalog search with a price filter.
- Price with promotion rules (original + % + promo; expired promotion; PIX not stacking).
- Order status with identification (LGPD), tracking only after dispatch.
- Return request applying the 7-day / 30-day / 90-day rules.
- Out-of-scope request (accessories, unrelated topics) politely declined.
