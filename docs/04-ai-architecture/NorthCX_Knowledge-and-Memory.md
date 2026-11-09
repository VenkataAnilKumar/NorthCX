# NorthCX Knowledge and Memory

Status: **Built**. Updated: 2026-11-09. Master for: conversation history, customer facts and long-term memories (knowledge retrieval is in 05-technical/NorthCX_Knowledge-Design.md).

## Memory
`MemoryStore` interface (`northcx/store.py`):
- `load_messages` / `save_messages(session_id)` for conversation history
- `get_facts` / `set_fact(customer_id, key, value)` for durable customer facts

Facts are injected into the system prompt as untrusted data. Stores: in-memory (development) and Postgres (built).

**Known limitation:** a run loads history, works, then saves the whole history. Saves are serialised and atomic, but two simultaneous runs on the same session can overwrite each other's turn (last save wins). Channels normally deliver one message at a time per conversation; a per-session lock or optimistic version check is planned before multi-worker deployment.

## Rules
- Store facts only with a purpose and retention period.
- Never store secrets or full card data.
- Facts record when they were last updated, but not which run wrote them (provenance is a gap; the trace of the run that set a fact shows it).
- Deleting a customer removes history, facts and long-term memories.

## Knowledge
Retrieval is a tool, `search_knowledge`, that returns passages with numbered source references; the agent must not assert beyond them. Retrieval is built into the platform (keyword search, optional meaning-based ranking through a configured embeddings service). Full detail: `../05-technical/NorthCX_Knowledge-Design.md`.

## Customer context at start (K7)
Optionally pull a customer profile from business systems when a conversation starts and add it as labelled, untrusted context.

## Lifecycle (K6, K8)
Summarise long histories to keep prompts small without losing commitments made. Retention periods, export and deletion are configured per deployment and applied to history, facts and traces together.

## Freshness (K5)
Knowledge sources record last update; stale sources are flagged, and a change triggers simulation re-runs (Q7).

## Open questions
Automatic extraction of notes from transcripts (today the agent decides what to save) and meaning-based recall for memories. Summarisation (K6) and freshness flags (K5) are built.

## Long-term memories (built; formerly NorthCX_Memory-Design.md)
Feature K2/K6 follow-on (workstream W12 of the finished 1.0 plan). Customer facts (key/value, set by tools or the company's systems) already exist; this adds free-text **memories**: short notes an agent learns in one conversation and can use in later ones, such as "prefers email over phone" or "ships to the office on weekdays".

### Behaviour
- **Saving:** the agent calls `remember` with one short note (5-300 characters). Notes are for the current known customer only; anonymous visitors cannot be remembered. The same fact saved again refreshes its date instead of duplicating (comparison ignores case and spacing). Each customer keeps at most 200 notes; the least recently confirmed are dropped first.
- **Refused notes:** wording that reads like an instruction to the model, payment card numbers, and passwords, PINs or keys are refused with a reason the agent can read. Configured secrets are redacted before storing.
- **Recalling:** at the start of every turn with a known customer, the five notes most relevant to the customer's message are added to the agent's context as untrusted data (not saved facts, not instructions); the trace records how many, never the text. The agent can also call `recall_memory` to look something up. Ranking is by keyword relevance, then recency.
- **Failure:** if memory cannot be read, the conversation goes on without it.
- **Not recalled for:** anonymous visitors, platform messages, and simulation runs. In simulations `remember` is a write tool and is not executed.

### Control and privacy
- People with `memory:read` (admin, developer, release manager, reviewer) can list a customer's notes; only admins (`memory:manage`) can delete one or all. Reads and deletions are audited with a one-way customer reference.
- Customer export includes memories, and customer erasure removes them (privacy API, retention sweeps do not age out memories because they belong to the customer, not a conversation).
- `NORTHCX_MEMORY=0` turns the feature off entirely.

### Interface
`MemoryService` has five methods (`remember`, `recall`, `list`, `forget`, `forget_all`). The built-in service stores notes in Postgres with full-text search (in memory for development). Another memory system can replace it by implementing the same methods; nothing else in the platform depends on how it ranks.

### Limits
Keyword ranking only (no meaning-based search), no automatic extraction of notes from transcripts (the agent decides what to save), no per-note expiry, and no web page yet.

## Staff memory (designed, not built)
Personal, space and team memory for staff assistants is specified in `../03-specs/NorthCX_Personal-Intelligence-Spec.md` (epic E5.5). Customer messages and customers' personal details never enter staff memory.
