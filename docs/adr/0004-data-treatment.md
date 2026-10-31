# ADR-0004: Data treatment — immutable sources, reproducible generated store
- Status: Accepted
- Date: 2026-10-31
- Decided by: Emanoel (delegated to Claude Code, reviewed by Emanoel)

## Context
The CSVs contain status/stock contradictions, order totals that differ from items, several
promotions per product (only one may be active), personal data, and categories with no
products; the manual has contradictory contact details and ambiguous rules
(`docs/data-findings.md`). Evaluators should see the original files, and treatment must be
reproducible.

## Decision
- `data/` holds the files exactly as delivered (read-only permissions). Nothing writes there.
- `tools/prepare_data.py` loads them with strict typing, runs data-quality checks and, only
  with `--apply`, builds `var/emporio.db` (SQLite) and `var/policies.json`. Default is dry-run.
  Every run prints row counts, transformations and findings; `--apply` also writes
  `var/prepare_report.json` with source SHA-256 hashes.
- Transformations are limited to types and derived keys: prices in integer cents, JSON specs
  validated, accent-free search keys, phone digits / normalized e-mail for identification.
- **No value is corrected.** Anomalies are findings; services handle them with explicit, tested
  rules (status wins over stock, recorded order total is reported, etc.).
- Checks that break an invariant the services rely on (duplicate ids, broken references, more
  than one active promotion per product, invalid status) are errors and block the build.
- The build writes to a temporary file and swaps it in atomically.
- SQLite rather than pandas-in-memory: indexed queries and pagination behave the same at 65 or
  30,000 products, and the catalog is opened read-only by the agent.

## Consequences
+ Reproducible from a clean clone; source integrity verifiable by hash.
+ The agent physically cannot alter store data (read-only connection).
− One extra setup command in the README.

## Where
`src/emporio_agent/ingest/`, `tools/prepare_data.py`, `docs/data-findings.md`.

## Origin
Challenge brief ("Tratamento dos dados"); Principle item 7 in `CLAUDE.md`.
