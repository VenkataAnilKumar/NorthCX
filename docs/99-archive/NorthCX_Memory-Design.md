# NorthCX Long-term Memory — Design

> **Archived 2026-11-09.** Merged into `../05-knowledge-memory/NorthCX_Knowledge-and-Memory.md`. Kept for history; not maintained.

Feature K2/K6 follow-on (W12). Customer facts (key/value, set by tools or the company's systems) already exist; this adds free-text **memories**: short notes an agent learns in one conversation and can use in later ones, such as "prefers email over phone" or "ships to the office on weekdays".

## Behaviour
- **Saving:** the agent calls `remember` with one short note (5-300 characters). Notes are for the current known customer only; anonymous visitors cannot be remembered. The same fact saved again refreshes its date instead of duplicating (comparison ignores case and spacing). Each customer keeps at most 200 notes; the least recently confirmed are dropped first.
- **Refused notes:** wording that reads like an instruction to the model, payment card numbers, and passwords, PINs or keys are refused with a reason the agent can read. Configured secrets are redacted before storing.
- **Recalling:** at the start of every turn with a known customer, the five notes most relevant to the customer's message are added to the agent's context as untrusted data (not saved facts, not instructions); the trace records how many, never the text. The agent can also call `recall_memory` to look something up. Ranking is by keyword relevance, then recency.
- **Failure:** if memory cannot be read, the conversation goes on without it.
- **Not recalled for:** anonymous visitors, platform messages, and simulation runs. In simulations `remember` is a write tool and is not executed.

## Control and privacy
- People with `memory:read` (admin, developer, release manager, reviewer) can list a customer's notes; only admins (`memory:manage`) can delete one or all. Reads and deletions are audited with a one-way customer reference.
- Customer export includes memories, and customer erasure removes them (privacy API, retention sweeps do not age out memories because they belong to the customer, not a conversation).
- `NORTHCX_MEMORY=0` turns the feature off entirely.

## Interface
`MemoryService` has five methods (`remember`, `recall`, `list`, `forget`, `forget_all`). The built-in service stores notes in Postgres with full-text search (in memory for development). Another memory system can replace it by implementing the same methods; nothing else in the platform depends on how it ranks.

## Limits
Keyword ranking only (no meaning-based search), no automatic extraction of notes from transcripts (the agent decides what to save), no per-note expiry, and no web page yet.
