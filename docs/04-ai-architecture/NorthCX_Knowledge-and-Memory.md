# NorthCX Knowledge and Memory

Status: Draft

## Memory
`MemoryStore` interface:
- `loadMessages / saveMessages(sessionId)` for conversation history
- `getFacts / setFact(customerId)` for durable customer facts

Facts are injected into the system prompt. Adapters: in-memory and Postgres (both built), external memory service (optional, Phase 3).

**Known limitation:** a run loads history, works, then saves the whole history. Saves are serialised and atomic, but two simultaneous runs on the same session can overwrite each other's turn (last save wins). Channels normally deliver one message at a time per conversation; a per-session lock or optimistic version check is planned before multi-worker deployment.

## Rules
- Store facts only with a purpose and retention period.
- Never store secrets or full card data.
- Facts carry provenance (which run wrote them).
- Deleting a customer removes history and facts.

## Knowledge
Retrieval is a tool: `search_knowledge({query})` returns passages with source references. The agent must cite sources in its reasoning and not assert beyond them. The retrieval service is external and replaceable (selection in the Reference).

## Customer context at start (K7)
Optionally pull a customer profile from business systems when a conversation starts and add it as labelled, untrusted context.

## Lifecycle (K6, K8)
Summarise long histories to keep prompts small without losing commitments made. Retention periods, export and deletion are configured per deployment and applied to history, facts and traces together.

## Freshness (K5)
Knowledge sources record last update; stale sources are flagged, and a change triggers simulation re-runs (Q7).

## Open questions
Fact extraction (automatic vs explicit tool), history summarisation for long sessions, and freshness policy for knowledge.
