# NorthCX Knowledge — Design

Status: **Built**. Updated: 2026-11-09. Master for: knowledge sources, ingestion, retrieval and citations.

Covers features K4 (retrieval with citations), K5 (sources and freshness), K8 (retention and deletion). Summarisation (K6) and business-system context (K7) are built and described in `../04-ai-architecture/NorthCX_Knowledge-and-Memory.md` and `NorthCX_Integrations.md`.

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

## File import and website crawling
**Importing files.** `POST /v1/knowledge/sources/{id}/import?filename=...` (the file is the request body; Studio has an "Upload files" button) turns a PDF, Word, PowerPoint, Excel, HTML, Markdown or plain-text file into a document (Office files were added later; see "Office files" below). Files are recognised by their content: programs, archives, old binary Office formats and pictures are refused. HTML keeps only what a reader sees (headings, paragraphs, lists and tables become Markdown-style text; scripts, styles, navigation, headers, footers, forms and anything hidden by `hidden`, `aria-hidden` or inline `display:none`/`visibility:hidden`/zero font size are dropped). A PDF contributes its text layer; a PDF with no text (a scan), a password-protected PDF and one with more than 300 pages are refused with a reason, and reading is cut off after 25 seconds. Limits: 10 MB for PDF, 2 MB for HTML and text. The document id defaults to `file:<name>`, so importing the same file again updates it.

**Crawling a site.** `POST /v1/knowledge/sources/{id}/crawl` with `{url, maxPages, maxDepth, delaySeconds, includePaths, excludePaths, useSitemap, prune}` starts a background crawl and returns a job id; `GET /v1/knowledge/crawls[/{id}]` shows progress (pages read, created/updated/unchanged, skipped by reason, removed). It is off unless the operator lists hosts in `NORTHCX_CRAWL_HOSTS`; nobody else can aim it at anything. It is built to be a good guest and a safe one:
- https only (http for localhost), the host must be listed, and the address it resolves to must not be inside a private network (loopback, link-local such as cloud metadata addresses, private ranges) unless `NORTHCX_CRAWL_ALLOW_PRIVATE=1`; every address is checked again on every request and every redirect hop, and a redirect to another host is never followed.
- It reads `robots.txt` (an unreachable or erroring one means the site is not crawled; a missing one means everything is allowed), obeys `Disallow` and `Crawl-delay`, waits between requests (at least 0.25 s, default 1 s), identifies itself as `NorthCXBot`, and sends no cookies or credentials.
- It starts from the address and the site's sitemap (one level of sitemap index, up to 1,000 addresses), follows links on the same host to the depth given (at most 4), skips addresses with a query string, files that are not pages, and anything outside `includePaths` or inside `excludePaths`.
- Bounds: at most 200 pages, 2 MB per page (10 MB for a PDF), 40 MB in total, 15 minutes by default, 5 crawl starts a minute per key, one crawl per source at a time.
- Each page becomes one document with id `web:<host><path>` and its address as the URL; `Last-Modified` or the sitemap's `lastmod` is the "last reviewed" date, so freshness flags work. A re-crawl updates only pages whose text changed. With `prune`, documents from an earlier crawl whose pages the site now reports gone (404/410) are removed; a page that merely failed to load is kept, hand-written documents are never touched, and pruning is skipped when the crawl stopped at a limit.
- Crawled text is untrusted data like everything an agent reads. Give agents that answer from crawled pages the `tool_output_injection` output check (the shipped templates do). Text hidden from readers by style sheets (rather than inline styles) is not recognised.
- Crawls and their progress are stored in the database (`crawl_jobs`), readable from any server process; the documents are the permanent result. Regular refreshes are built as scheduled re-crawls (below).

## Not in the first step (later built where marked)
Word and other Office formats (built: import of `.docx`, `.pptx`, `.xlsx`; the crawler still skips Office files), embeddings (built: meaning-based search, below), connectors to document systems (not built; E9).

## Meaning-based search (hybrid)

Keyword search misses a customer who writes "money back" when the policy says "reimbursement". When the operator sets `NORTHCX_EMBEDDINGS_URL` and `NORTHCX_EMBEDDINGS_MODEL`, NorthCX also searches by meaning and merges both rankings. It is off by default and never required.

- **The embedding service is yours to choose.** NorthCX ships no model. It calls `POST <url>/embeddings` with `{"model", "input": [...]}` and expects `{"data": [{"index", "embedding": [...]}]}` (the shape most hosted and self-hosted servers share). Passage text, and each customer question, are sent to that address and nowhere else; self-hosting keeps them inside your network. The address must be https (http for localhost), carry no credentials in the URL, and is never followed through redirects.
- **Storage** is pgvector in the same Postgres: a `knowledge_embeddings` table created on first start (cascade-deleted with its passage). With the in-memory store (development) vectors are kept in memory. The vector size is whatever the model returns; vectors of another size are ignored at query time.
- **Indexing is background work.** Saving a document never waits for, or fails because of, the embedding service. A worker embeds passages that have no vector for the current model (retrying with back-off, at most 10 minutes between tries) and is woken whenever a document changes. Changing the model name makes every passage pending again; `POST /v1/knowledge/index/rebuild` forces a full redo. `GET /v1/knowledge/index` reports model, indexed/pending counts, last run and last error (no addresses or response text).
- **Ranking** runs the keyword and the meaning search in parallel and merges them by reciprocal rank fusion, so exact terms (order numbers, product codes) still win while paraphrases are found. Meaning matches below a similarity of 0.25 are dropped. Each result says how it was found (`keyword`, `meaning` or `both`).
- **Fallback.** If the embedding service is slow (4 s), down or answers badly, the search is keyword-only and the conversation never sees an error.
- **Not done:** re-ranking models.

### Office files
`.docx`, `.pptx` and `.xlsx` can be imported (up to 10 MB each). Word headings, lists and tables become Markdown-style text; slides become sections in order (speaker notes are not read because they are often private); spreadsheets become one section per visible sheet with rows joined by ` | ` (hidden sheets are skipped, at most 3,000 rows and 60 columns per sheet). They are recognised by content, parts are read with size caps and without any DOCTYPE or entity, and the unpacked size is capped, so a zip bomb or an entity-expansion file is refused. The old binary formats (.doc, .xls, .ppt) are not supported. The website crawler does not fetch Office files yet.

### Approximate index, per-source models and scheduled crawls
- **Approximate index.** Searches are exact until the number of passages with a vector of one size passes `NORTHCX_ANN_THRESHOLD` (default 5,000). The indexer then builds a cosine HNSW index in pgvector for that vector size (up to 2,000 dimensions; larger sizes stay exact) and searches use it automatically. Building takes a short write lock on the embeddings table. Results are approximate: with a source or model filter the index may return slightly fewer matches than an exact scan, and the keyword half of the hybrid search still finds exact terms. `GET /v1/knowledge/index` lists the indexed sizes.
- **Per-source models.** `NORTHCX_EMBEDDINGS_SOURCE_MODELS=help=model-a,docs=model-b` makes those sources use another model on the same service; every other source uses `NORTHCX_EMBEDDINGS_MODEL`. Each source is indexed with its own model (status shows indexed/total per model); a search embeds the question once per model in play and merges the results; a search limited to one source uses only that source's model. Changing a source's model makes only that source pending again.
- **Scheduled re-crawls.** `POST /v1/knowledge/sources/{id}/schedule` takes the same body as a crawl plus `everyHours` (1 to 720). It is validated exactly like a crawl (allowed host, https, limits, known source) and again on every run; only hosts in `NORTHCX_CRAWL_HOSTS` can be scheduled, a host removed from the list stops its schedules from running, and a run is skipped (and recorded) if a crawl of that source is still running. At most 20 schedules, one per source and address. Several server processes can share the database; a run is claimed atomically, so each runs once per interval. `GET /v1/knowledge/schedules`, `DELETE /v1/knowledge/schedules/{id}` and `POST /v1/knowledge/schedules/{id}/enabled` manage them; Studio's Knowledge page offers "Repeat" on the crawl form.
