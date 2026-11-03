# NorthCX Knowledge — Design

Covers features K4 (retrieval with citations), K5 (sources and freshness), K8 (retention and deletion). Summarisation (K6) and business-system context (K7) follow.

## Goals
- An agent answers policy and product questions from the company's own documents and shows where each answer came from.
- Documents can be added, updated and removed through the API; unchanged documents cost nothing to re-submit.
- People can see what is stale, and the agent can see it too.
- Everything works with only Postgres (no extra services) and has an in-memory version for tests and development.

## Model
- **Source**: a named collection (for example "Help centre") with a `stale_after_days` setting.
- **Document**: belongs to a source; has an `external_id` (the caller's own id, so re-submitting updates in place), title, optional URL, text, content hash, `source_updated_at` (when the company last changed it), `ingested_at`, and a deleted flag.
- **Chunk**: a passage of a document, split at headings and paragraphs (about 800 characters, no overlap), each carrying its heading path so a passage reads on its own.

## Search
Keyword search with Postgres full-text ranking (in memory: a simple BM25-style score). Results are passages with: document title, URL, heading, text, score, `updated` time and `stale` flag. A meaning-based (embedding) ranker can be added behind the same interface later; the interface returns ranked passages and does not assume how ranking is done.

## Agent tool
`search_knowledge` (a read tool) returns up to five passages, each with a citation number, title, URL and last-updated date, and a note when a source is stale. Passages are third-party text, so they pass through the tool-output screens like any other tool result, and the tool description tells the agent to answer only from them and to cite by number, or hand off when nothing relevant is found.

## API
`knowledge:read` (every internal role except `channel`) and `knowledge:write` (`developer`, `admin`).
- `GET/POST /v1/knowledge/sources`
- `PUT /v1/knowledge/sources/{id}/documents/{external_id}` upsert (skipped when the hash is unchanged); `DELETE` removes the document and its passages
- `GET /v1/knowledge/documents?source=&stale=` listing with freshness
- `GET /v1/knowledge/search?q=&source=` for testing retrieval

## Retention and deletion
Deleting a document removes its passages immediately and leaves an audit entry. Per-customer export and deletion of conversation data (K8) is a separate step.

## As built
- Migration 0010; Postgres full-text search with English stemming, any query word may match and the best passages rank first; the in-memory version matches whole words only (no stemming), so very small differences in ranking between the two are expected.
- The tool is `search_knowledge`; a deployment lists it in an agent's `tools`. It is added to the registry automatically unless the deployment's own registry already defines a tool of that name.
- Every document write is audited (`knowledge.source.*`, `knowledge.document.*`); an unchanged re-submit is not an event.
- Document text is limited to 500,000 characters; ids are letters, digits and `. _ : / -`.

## Not in this step
URL crawling and connectors, file-type parsing (PDF, Word), embeddings, a web page. Documents are submitted as text or Markdown.
