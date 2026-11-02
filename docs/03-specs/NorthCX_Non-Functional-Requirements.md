# NorthCX Non-Functional Requirements

Status: Draft. Numbers are proposals to validate.

| Area | Requirement |
|---|---|
| Availability | Reference deployment 99.9%; graceful degradation when the model provider fails (escalate, never silent failure) |
| Latency | Targets set after streaming exists; supervisor adds bounded overhead; voice has a stricter budget |
| Scalability | Stateless runtime workers; scale horizontally; per-key and per-customer concurrency limits |
| Reliability | Retries with backoff for idempotent operations; no duplicate side effects (idempotency keys) |
| Data integrity | Saved conversation history is always valid; writes are transactional |
| Security | Least privilege tools; secrets outside prompts and traces; hashed API keys; role-based access; audit of every action |
| Privacy | Retention limits; deletion and export per customer; redaction before export; documented data flow |
| Observability | Trace for every run; metrics and alerts; no PII in logs |
| Maintainability | Strict typing; interfaces for every external dependency; tests with no network |
| Portability | Runs in containers; no cloud-specific dependency in the core; model and storage replaceable |
| Accessibility | Studio and widget meet WCAG AA |
| Internationalisation | Unicode throughout; language detection; locale-aware formats |
| Compliance support | Controls to support privacy and security frameworks; certification is the deployer's responsibility |
| Cost | Per-conversation budgets; cost visible per run |
| Licensing | Permissive dependencies in the core |
