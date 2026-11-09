# NorthCX Project Status and Plan

Status: Snapshot (2026-11-08). A one-page summary of where the project stands and what is planned. The detail lives in `NorthCX_Release-Checklist.md` (finishing 1.0) and `NorthCX_Gap-Closure-Plan.md` (after 1.0). Update this page when a wave ships or a decision is made.

## Product documentation (2026-11-09)
The product documents now cover the whole designed platform: vision and requirements (FR1 to FR41), personas, stories and journeys, the feature catalog (section 12), four after-1.0 specifications, the staff platform architecture, threat model and security, non-functional requirements, testing, design system, roadmap and decision log (to #171). What remains is listed in `../09-project/NorthCX_Docs-Completion-Checklist.md`. No design-phase feature is built.

## Done
- **Phases 1 to 6 are complete:** the agent engine, safety, approvals, simulations and releases, Studio, six channels (web, email, SMS, WhatsApp, Telegram, voice), knowledge, analytics, identity checks, abuse detection, status events and data residency.
- **The follow-up gaps are closed** (marked built in `NorthCX_Next-Features-Plan.md`): Office files, scheduled crawls, the approximate-nearest-neighbour index, per-source embedding models, analytics filters and charts, agent test scenarios, refinement and audio transcription, WhatsApp media, templates and several numbers, and Telegram.
- **Presentation and release readiness:** the README is a landing page with real screenshots; the release checklist and CI fixes are in; the commits are authored as the project owner.
- **Verification:** more than 1,300 backend tests plus Studio and SDK tests; a clean-checkout run of the install, tests and builds.

## Wave 0: finish 1.0 (started)
**Done so far in Wave 0 (2026-11-08):** WP0.1 router, bootstrap and store split (guarded by a golden route-dispatch snapshot and a layout test); WP0.2 design tokens in the shared UI package; WP0.3 hash-pinned backend dependencies with an audit job; WP0.4 shared rate limits, burst check and token budget (`NORTHCX_LIMITS_BACKEND=postgres`); WP0.5 several processes (`NORTHCX_ROLE`, job leases, shared alert and crawl state); WP0.6 PDFs as masked text; WP0.7 generated API reference; WP0.8 webhook tester; WP0.9 confirmed from GitHub CI; WP0.10 provisional resolution rate and post-1.0 scope wording.

**CI (checked 2026-11-08):** GitHub Actions has run on every push; the latest run (WP0.8) passed all seven jobs, including the container build and compose smoke test and the dependency audit, so WP0.9 is done.

**Still to do in Wave 0:**
- WP0.11 live-model pass (needs an Anthropic API key).
- WP0.12 penetration test, the `v1.0.0-rc.1` tag and the 1.0.0 release (you).

Items only the owner or an outside party can do:
- The live-model pass (needs an API key) and judge calibration.
- The independent penetration test.
- Pushing the `v1.0.0-rc.1` tag.
- Cutting 1.0.0.

## Wave 1 (started 2026-11-08)
E1 model providers: WP1.1 (provider layer, `provider:model` names, capability checks) and WP1.2 (Claude as an adapter, SDK and direct HTTPS clients) are done; next WP1.3 (OpenAI-compatible adapter). The backend suite has 1,413 tests.

## After 1.0 (from the gap analysis)
| Release | Contents |
|---|---|
| **1.1** | Model providers and currency budgets; multi-tenancy (the biggest item: 38 tables, 30 store classes, 118 routes); identity (agent-scoped keys, groups, SCIM, SAML behind a flag, publish approval); MCP client and server |
| **1.2** | Staff workspace (chat, staff memory, permission-aware search); team libraries and generated outputs; QA scoring |
| **1.3** | Automations; connector SDK and native connectors |
| **1.4** | Metering and plans; deployment kit (Helm, Terraform, ops console); compliance documents and developer portal |
| **Later** | Marketing site; Slack, Teams and helpdesk surfaces; native mobile apps; a marketplace |

## Portals and surfaces
The ten target portals and surfaces (marketing site, workspace, builder, admin portal, developer portal, analytics, trust and legal centers, ops console, back office, embedded surfaces) are mapped to epics in section 10 of the gap-closure plan, including eight additions (E14 to E21) and what can be verified here.

## Decisions made
- **Web layout (D10, decision 140), decided and started:** several apps plus shared packages in one repository; back office on an internal network under `/platform/v1`; marketing, trust, legal and developer portal under `src/site`. Studio now lives in `src/apps/studio` with shared packages in `src/packages`. See `05-technical/NorthCX_Repo-Structure.md`.

## Decisions waiting on the owner
Open model (open versus commercial), naming of the staff product, tenancy model, first staff surface, SAML approach, first connectors, MCP approach, billing unit, first model providers. The first two should be settled first because they shape billing and the staff product. Recommendations are in section 3 of the gap-closure plan.

## Small corrections still to apply
- The gap analysis says "only knowledge re-crawls run on a schedule"; it should say "the only user-defined schedule" (alerts, retention, approvals and exports already run in the background).
- The index row for the gap analysis in `docs/README.md` names an external product; reword it.
- Add a naming note to the gap analysis about the proposed positioning phrases.

## Outside what can be built or verified in this repository
SOC 2 and ISO audits, a hosted managed cloud, vendor connector verification (needs sandbox accounts), native iOS and Android apps, and the penetration test. The plans say so and label every deliverable as verified here, partly verified, or needing outside verification.

## Detailed plan
`NorthCX_Implementation-Plan.md` breaks every wave into work packages with steps, tests, gates, sizes, verification labels and a living checklist (section 14), plus the register of actions only the owner or an outside party can take.

## Where to start
Take the first slice of Wave 0 (split `server.py`, lock dependencies, shared rate limits), then the model-provider layer; or settle the open-model and naming decisions first and record them in the decision log.
