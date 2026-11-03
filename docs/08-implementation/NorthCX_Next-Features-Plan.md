# NorthCX Plan: closing the known gaps before 1.0.0

Status: proposed, not started (except a first uncommitted draft of Office-format reading). Each batch is a separate commit pushed to `claude/awesome-brown-o0nk5s` and `main`, with tests, docs, decision-log entries, catalog and CHANGELOG updates, and a real-service check where one can be run here (local Postgres with pgvector; browser smoke for Studio).

Rules that apply to every item: no new dependency on a reference project; new libraries only if ordinary infrastructure (prefer the standard library); every outbound address is operator configuration, https, no redirects, and is added to the residency report; anything a model returns is validated against a fixed list; nothing drafted by a model is saved or made live without a person.

## Batch 1 — Search and knowledge
| Item | Design | Main risks | Tests and checks |
|---|---|---|---|
| Office formats | Read `.docx`, `.pptx`, `.xlsx` with the standard library (zip + XML). Headings, lists and tables become Markdown-style text; hidden sheets and speaker notes are not read. Wired into file import and the crawler's file types | Zip bombs, XML entity expansion: caps on unpacked size and part size, DOCTYPE/ENTITY refused, row and column caps | Generated sample files, malformed and hostile files, fuzz test |
| Scheduled re-crawls | A per-source schedule (daily / weekly, with the crawl settings saved) run by a background loop with one crawl at a time; shown in Studio; survives restarts (stored in the database) | Surprise load on a site: reuse the existing delay, robots and caps; minimum interval 1 hour | Scheduler with a fake clock, restart test, Postgres test |
| ANN index | After the passage count passes a threshold, create a pgvector HNSW index for the embedding size in use; searches use it automatically; below the threshold the exact scan stays | Index build time and memory; models with over 2,000 dimensions are skipped with a note; filtering by model lowers recall slightly (documented) | Real pgvector: results match the exact scan on a sample, index is used (EXPLAIN), rebuild after a model change |
| Per-source embedding models | Optional map of source → model on the same embeddings service. Each source is indexed with its own model; a search embeds the question once per model in play and merges | More complex status and rebuild; mixed vector sizes (already ignored at query time) | In-memory and Postgres contract tests, status per model |

## Batch 2 — Analytics
| Item | Design | Main risks | Tests and checks |
|---|---|---|---|
| More filters | The question plan gains validated filters: language, channel, queue, tag, handed-off yes/no, rating range. Data already recorded per turn; channel needs recording on the turn facts | Filters the data cannot support: refused with the list that can be used | Plan validation, computed answers on fixtures |
| Questions about individual conversations | A second kind of plan: "find conversations where ..." mapped to the existing conversation search (words, status, tag, language, handed off). Returns a masked list with links, never model-written summaries of transcripts | Personal data: results use the existing masking; only staff with trace access can use it | Masking test, role test |
| Charts in answers | The answer carries a series or ranked list; Studio draws an accessible chart (SVG, with a table fallback) | Accessibility, dark mode | Component tests, browser smoke |

## Batch 3 — Agent building
| Item | Design | Main risks | Tests and checks |
|---|---|---|---|
| Automatic test scenarios | From the draft and the typical questions, produce scenario drafts in the existing scenario format (opening message, expected tool use, must-not-say). Validated with the real scenario parser and run once against the draft in dry-run so obviously failing ones are flagged | Scenarios that pass trivially: each must include an assertion; flagged otherwise | Parser round trip, dry-run test |
| Refining a draft by conversation | A follow-up call takes the previous draft and an instruction ("never promise delivery dates") and returns a revised draft with a list of what changed; same validation and field limits; draft history is kept in the browser only | Drift into unsafe changes: same field whitelist and registry checks every round | Diff test, repeated-round safety test |
| Audio transcription | A pluggable transcription endpoint (common JSON/multipart shape, operator configured, like embeddings); audio is sent only there, size and length capped, result is a transcript source that goes through the same masking before the model sees it | Audio is personal data: consent note in the UI, residency report entry, nothing stored | Mock service tests, size caps, error paths |

## Batch 4 — Messaging
| Item | Design | Main risks | Tests and checks |
|---|---|---|---|
| WhatsApp templates | Operator-defined approved template names with parameters; used to start a conversation or to reply after the 24-hour window; an API to send one and a hand-off/follow-up path that uses them | Sending to people who did not opt in: only to numbers with an existing opt-in record or an explicit operator call; STOP respected | Provider mock, window logic, opt-out test |
| WhatsApp media | Receive images and documents into the existing attachment pipeline (content-sniffed, size-limited, optionally scanned, opt-in per agent); send media is out of scope | Untrusted files: same checks as web uploads; media download uses the token only on the provider's address | Mock download, sniffing, scanner hook |
| Several WhatsApp numbers | Configuration becomes a list; each number has its own agent, secret handling and rate limit; routing by the number id in the webhook | Shared state keyed by phone number id: already part of the session key | Two-number tests, isolation test |
| One more messaging app | Needs your choice (see decisions). Same provider interface, signed webhook, shared conversation engine | Per-platform rules (opt-in, windows, formats) | Same suite as WhatsApp |

## Order and size
Batch 1 first (self-contained and testable here), then 2, 3, 4. Rough size: batch 1 about 1,000 lines with tests; batch 2 about 700; batch 3 about 900; batch 4 about 1,200. Test counts grow by roughly 100–150 per batch. Each batch ends with the full backend suite, the web checks, and a push verified against both branches.

## Decisions needed from you
1. **Which other messaging app?** Options: Telegram (simple bot API, no business approval), Facebook Messenger / Instagram (Meta, same webhook family as WhatsApp), Slack or Microsoft Teams (staff-facing more than customer-facing), LINE or WeChat (region specific). Recommendation: Telegram first, then Messenger.
2. **Which transcription service shape?** Recommendation: a pluggable HTTP endpoint (self-hosted or hosted), off by default, as with embeddings.
3. **WhatsApp templates:** confirm templates are only sent to numbers that already messaged us or are on an operator-supplied opt-in list.
4. **Re-crawl schedules:** confirm a minimum interval of 1 hour and that a schedule can only be created for hosts already allowed for crawling.

## Not in this plan
The real-model pass, the independent penetration test, the release candidate tag push and the final 1.0.0 (they need you or a live model), multi-tenancy, billing and metering, and the one-time-code identity check.
