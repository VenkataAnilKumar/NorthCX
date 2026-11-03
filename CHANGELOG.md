# Changelog

All notable changes. The format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [Semantic Versioning](https://semver.org/). Detailed design decisions are numbered in `docs/09-project/NorthCX_Decision-Log.md`.

## [Unreleased]

### Added
- Monitoring page in Studio: active alerts, rules, recent alert events with delivery status, a test-alert button, and the conversations flagged by the always-on checks.

### Added (knowledge)
- Import PDF, HTML, Markdown and text files into the knowledge base; crawl listed websites (robots.txt, sitemap, limits, pruning) from the API or Studio.

### Changed
- Connectors can read paged lists (cursor, page number, offset, Link header) and sign in with OAuth 2 (client credentials, refresh token).
- Alert webhook deliveries are retried (three attempts) and each event records whether it was delivered.

## [1.0.0-rc.1] - 2026-11-03

First release candidate: the planned feature set (phases 1 to 6, minus the items listed under "Not in this release") is built and tested. Before 1.0.0: an independent penetration test and a run against a real model.

### Added
- **Runtime and safety**: typed tools; reply, tool, input and output guardrails; personal-data masking and takeover-phrase checks; fail-closed supervision; human approval with exactly-once execution and expiry; always-to-a-person topics; token budgets; model fallback and retries; conversation summarising; customer facts, company context and long-term memory; skills with enforced step order; brand voice; per-customer tool scopes.
- **Agents as data**: YAML specs with immutable versions, diffs, environments (dev, staging, production), a release gate tied to the exact version, publish checklist, staged rollouts, one-step rollback; journeys (goal, steps, rules, hand-off conditions, progress metrics, generated tests, drafts from plain language); languages with automatic detection; specialist agents and in-turn transfers; attachments (pictures, PDFs, text) enabled per agent.
- **Proof**: scenario simulations with personas and attack suites, regression scenarios drafted from real conversations, release gating in CI, load testing and token-cost estimates with a CI baseline.
- **Channels**: web chat with streaming and a browser SDK with a drop-in `<northcx-chat>` widget; email; SMS; phone calls through a provider-neutral WebSocket bridge with disclosure, consent, barge-in, keypad and language switching.
- **People**: hand-off queues with hours and after-hours routing, hand-off package, suggested replies, person replies and hand-back to the agent, helpdesk and webhook inbox delivery, conversation review with failure tagging and quality metrics.
- **Studio**: a web console for editing and testing agents, scenarios, knowledge, versions, rollouts, reviews, hand-offs, approvals, insights, conversations, access and audit.
- **Insight and operations**: metrics with numerators and denominators, alerts, search and tags, trace export, privacy export/erasure/retention, hash-chained audit log, roles and hashed API keys, single sign-on (OpenID Connect), rate limits, request size caps, safe response headers.
- **Docs**: product, architecture, security (threat model, review report), deployment, performance and cost, SDK and voice guides.

### Security
- Review findings fixed before this release: request size caps, voice stream flood limits, default security headers, a crash on malformed identity tokens, explicit no-redirect HTTP clients. See `docs/06-security/NorthCX_Security-Review.md`.

### Not in this release
Native iOS and Android SDKs; outbound calls; agent-assisted building (A8); natural-language analytics (O8); data residency options (P6); messaging apps beyond SMS; knowledge crawling and meaning-based search; per-agent scoping of roles; multi-tenancy and metering.

### Known limits
Rate limits and daily budgets are per process; pictures and PDFs reach the model unmasked; backend dependencies are not locked; real-model and long-run (soak) results are unmeasured. The full list is in the threat model.
