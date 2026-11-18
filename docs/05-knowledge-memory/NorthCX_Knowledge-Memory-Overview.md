# NorthCX Knowledge and memory: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** What agents know and remember: knowledge sources and retrieval, conversation history, customer facts and long-term memory.

## Built
- Import of PDF, Word, PowerPoint, Excel, HTML, Markdown and text; a polite website crawler with schedules
- Passage search with citations and freshness; optional meaning-based search with per-source embedding models
- Customer memory with remember, recall and erase; summarising long conversations

## Gaps and next steps
- A "test my knowledge" check that shows questions the sources cannot answer (design section 13)
- Permission-aware staff search over tickets and CRM data (later)
- A trial of a graph-based memory store behind the existing interface

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Knowledge-Design.md`](NorthCX_Knowledge-Design.md) | Knowledge sources, ingestion, retrieval, citations (master) |
| [`NorthCX_Knowledge-and-Memory.md`](NorthCX_Knowledge-and-Memory.md) | History, customer facts and long-term memory (master) |
