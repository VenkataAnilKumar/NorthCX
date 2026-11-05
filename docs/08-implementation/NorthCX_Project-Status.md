# NorthCX Project Status and Plan

Status: Snapshot (2026-11-05). A one-page summary of where the project stands and what is planned. The detail lives in `NorthCX_Release-Checklist.md` (finishing 1.0) and `NorthCX_Gap-Closure-Plan.md` (after 1.0). Update this page when a wave ships or a decision is made.

## Done
- **Phases 1 to 6 are complete:** the agent engine, safety, approvals, simulations and releases, Studio, six channels (web, email, SMS, WhatsApp, Telegram, voice), knowledge, analytics, identity checks, abuse detection, status events and data residency.
- **The follow-up gaps are closed** (marked built in `NorthCX_Next-Features-Plan.md`): Office files, scheduled crawls, the approximate-nearest-neighbour index, per-source embedding models, analytics filters and charts, agent test scenarios, refinement and audio transcription, WhatsApp media, templates and several numbers, and Telegram.
- **Presentation and release readiness:** the README is a landing page with real screenshots; the release checklist and CI fixes are in; the commits are authored as the project owner.
- **Verification:** more than 1,300 backend tests plus Studio and SDK tests; a clean-checkout run of the install, tests and builds.

## Wave 0: finish 1.0 (not started)
Groundwork that can be built and verified here:
- Split the 2,500-line `server.py` into router modules.
- Lock dependencies.
- Make rate limits shared across processes.
- Add a masked-text option for PDFs.
- Publish the API reference.
- Add a webhook tester.

Items only the owner or an outside party can do:
- The live-model pass (needs an API key) and judge calibration.
- The independent penetration test.
- Pushing the `v1.0.0-rc.1` tag.
- Cutting 1.0.0.

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
