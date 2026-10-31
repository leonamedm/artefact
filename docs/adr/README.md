# Architecture Decision Records

One file per relevant decision, numbered, never rewritten after acceptance — superseded by a
new ADR instead.

## Template
```
# ADR-NNNN: Title
- Status: Proposed | Accepted | Superseded by ADR-XXXX
- Date: YYYY-MM-DD
- Decided by:
## Context
## Decision
## Consequences
## Where
## Origin
## Open   (only if something is pending)
```

## Index
| # | Title | Status |
|---|---|---|
| [0001](0001-agent-approach.md) | Agent approach — native tool calling over deterministic services | Accepted |
| [0002](0002-model-and-provider.md) | Model and provider — free tier via OpenAI-compatible API | Accepted |
| [0003](0003-policy-retrieval.md) | Policy retrieval — topic-indexed manual sections, no vector store | Accepted |
| [0004](0004-data-treatment.md) | Data treatment — immutable sources, reproducible generated store | Accepted |
| [0005](0005-conversation-persistence.md) | Conversation persistence — SQLite sessions | Accepted |
| [0006](0006-interface.md) | Interface — terminal chat | Accepted |
