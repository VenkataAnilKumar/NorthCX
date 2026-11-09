# NorthCX Non-Functional Requirements

Status: **Plan**. Updated: 2026-11-09. Master for: non-functional requirements. Numbers are proposals to validate.

| Area | Requirement |
|---|---|
| Availability | Reference deployment 99.9%; graceful degradation when the model provider fails (escalate, never silent failure) |
| Latency | Targets set after a baseline with a real model (streaming is built; figures so far use an offline model, see Performance); supervisor adds bounded overhead; voice has a stricter budget |
| Scalability | Several processes with `api` and `worker` roles share state through Postgres (built); scale horizontally; per-key, per-session and per-address rate limits; two simultaneous messages in the same conversation can still overwrite each other's turn (see Knowledge-and-Memory) |
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

## After 1.0: Workspace and Admin apps (proposals to validate)
| Area | Requirement |
|---|---|
| Accessibility | Both web apps meet WCAG 2.1 AA in every theme: keyboard operation, visible focus, labelled controls, no colour-only meaning, text size and density options, high contrast, reduced motion, and solid surfaces when transparency is unwanted |
| Responsiveness | Usable from a 1280 px laptop to a large monitor; the Workspace is readable on a tablet; a phone view is not a first-release goal |
| Performance | Time to a first streamed token and page-load budgets are set after the first slice is measured (Performance gate approach as in the implementation plan); lists page and filter on the server |
| Latency of steering | Pause, redirect and stop take effect at the next step boundary and are acknowledged within 2 seconds |
| Durability | A closed browser never stops a background task or automation; a worker restart resumes from the last finished step |
| Privacy | Customer personal data is masked outside the live conversation; erasing a person's memory and history completes within a stated time and is audited |
| Isolation | One tenant's tasks, spaces, outputs and memory are invisible to another, proved by the generated isolation sweep |
| Browser support | The two latest versions of Chrome, Edge, Firefox and Safari |
| Internationalisation | Interface text is externalised from the start; the first release ships English; date, number and time zone follow the person's settings |
