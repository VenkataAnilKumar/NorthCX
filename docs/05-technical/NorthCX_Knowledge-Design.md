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

## File import and website crawling
**Importing files.** `POST /v1/knowledge/sources/{id}/import?filename=...` (the file is the request body; Studio has an "Upload files" button) turns a PDF, HTML, Markdown or plain-text file into a document. Files are recognised by their content: programs, archives, Office files and pictures are refused. HTML keeps only what a reader sees (headings, paragraphs, lists and tables become Markdown-style text; scripts, styles, navigation, headers, footers, forms and anything hidden by `hidden`, `aria-hidden` or inline `display:none`/`visibility:hidden`/zero font size are dropped). A PDF contributes its text layer; a PDF with no text (a scan), a password-protected PDF and one with more than 300 pages are refused with a reason, and reading is cut off after 25 seconds. Limits: 10 MB for PDF, 2 MB for HTML and text. The document id defaults to `file:<name>`, so importing the same file again updates it.

**Crawling a site.** `POST /v1/knowledge/sources/{id}/crawl` with `{url, maxPages, maxDepth, delaySeconds, includePaths, excludePaths, useSitemap, prune}` starts a background crawl and returns a job id; `GET /v1/knowledge/crawls[/{id}]` shows progress (pages read, created/updated/unchanged, skipped by reason, removed). It is off unless the operator lists hosts in `NORTHCX_CRAWL_HOSTS`; nobody else can aim it at anything. It is built to be a good guest and a safe one:
- https only (http for localhost), the host must be listed, and the address it resolves to must not be inside a private network (loopback, link-local such as cloud metadata addresses, private ranges) unless `NORTHCX_CRAWL_ALLOW_PRIVATE=1`; every address is checked again on every request and every redirect hop, and a redirect to another host is never followed.
- It reads `robots.txt` (an unreachable or erroring one means the site is not crawled; a missing one means everything is allowed), obeys `Disallow` and `Crawl-delay`, waits between requests (at least 0.25 s, default 1 s), identifies itself as `NorthCXBot`, and sends no cookies or credentials.
- It starts from the address and the site's sitemap (one level of sitemap index, up to 1,000 addresses), follows links on the same host to the depth given (at most 4), skips addresses with a query string, files that are not pages, and anything outside `includePaths` or inside `excludePaths`.
- Bounds: at most 200 pages, 2 MB per page (10 MB for a PDF), 40 MB in total, 15 minutes by default, 5 crawl starts a minute per key, one crawl per source at a time.
- Each page becomes one document with id `web:<host><path>` and its address as the URL; `Last-Modified` or the sitemap's `lastmod` is the "last reviewed" date, so freshness flags work. A re-crawl updates only pages whose text changed. With `prune`, documents from an earlier crawl whose pages the site now reports gone (404/410) are removed; a page that merely failed to load is kept, hand-written documents are never touched, and pruning is skipped when the crawl stopped at a limit.
- Crawled text is untrusted data like everything an agent reads. Give agents that answer from crawled pages the `tool_output_injection` output check (the shipped templates do). Text hidden from readers by style sheets (rather than inline styles) is not recognised.
- Crawl history is kept in memory per process (the last 20); the documents are the permanent result. To refresh regularly, call the crawl endpoint from a scheduler.

## Not in this step
Word and other Office formats, connectors to document systems, embeddings (meaning-based ranking is planned next).
