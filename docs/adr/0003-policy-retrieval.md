# ADR-0003: Policy retrieval — topic-indexed manual sections, no vector store
- Status: Accepted
- Date: 2026-10-31
- Decided by: Emanoel (delegated to Claude Code, reviewed by Emanoel)

## Context
The policy manual has 8 pages and 10 numbered sections with clear boundaries (hours, payment,
returns, shipping, promotions, warranty, privacy…). Questions map naturally to one section.
Embedding-based RAG would add an embedding model, an index and chunking choices, and can return
the wrong chunk for short, rule-dense text (e.g. "7 dias" appears in two different rules).

## Decision
- `ingest/policies.py` extracts the PDF with pypdf (layout mode), strips page headers/footers
  and splits it by the expected table of contents, in order. If a heading is missing,
  extraction fails loudly instead of producing wrong sections.
- Sections are stored in `var/policies.json` with a topic key. The `get_policy(topic)` tool
  returns the exact section text with its source ("Manual v2.1, seção 4").
- Internal-only sections (§7 service guidelines, §10 final provisions) are not exposed as
  tools; their content shaped the system prompt instead.
- Numeric rules from these sections are also implemented in services, so the model cites the
  policy while code computes the outcome (e.g. `check_return_eligibility`).
- Contact details come from `get_store_info` (convention C1/C2), because the manual is
  inconsistent.

## Consequences
+ Deterministic, auditable retrieval; trivial to test; no extra infrastructure or cost.
+ The model always sees the whole relevant section, never half a rule.
− Does not scale to large or frequently changing document sets. Then: hybrid retrieval
  (BM25 + embeddings, re-ranking) over chunked sections, keeping `get_policy` as the interface.

## Where
`src/emporio_agent/ingest/policies.py`, `src/emporio_agent/services/policies.py`,
`src/emporio_agent/agent/tools.py`.

## Origin
`data/políticas_da_loja.pdf` v2.1; challenge brief ("arquitetura de retrieval").
