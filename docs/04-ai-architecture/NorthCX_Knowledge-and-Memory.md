# NorthCX Knowledge and Memory

Status: Draft

## Memory
`MemoryStore` interface:
- `loadMessages / saveMessages(sessionId)` for conversation history
- `getFacts / setFact(customerId)` for durable customer facts

Facts are injected into the system prompt. Adapters: in-memory (built), Postgres (Phase 2), external memory service (optional).

## Rules
- Store facts only with a purpose and retention period.
- Never store secrets or full card data.
- Facts carry provenance (which run wrote them).
- Deleting a customer removes history and facts.

## Knowledge
Retrieval is a tool: `search_knowledge({query})` returns passages with source references. The agent must cite sources in its reasoning and not assert beyond them. The retrieval service is external and replaceable (selection in the Reference).

## Open questions
Fact extraction (automatic vs explicit tool), history summarisation for long sessions, and freshness policy for knowledge.
