# NorthCX Documentation

NorthCX is an open-source, self-hosted platform for supervised customer-experience agents that run local and cloud models side by side (decision 198). Every document starts with one line: **Status** (Built, Partly built, Designed, Plan, Reference or Archive), **Updated** and **Master for** (what it is the source of truth for).

The documents are organised by **platform area**. Each area folder starts with a one-page overview (`NorthCX_<Area>-Overview.md`): what the area covers, what is built, the gaps, and links to every document in it.

## Start here
1. **What it is and who it is for:** `00-platform/NorthCX_Product-Definition.md`, then `00-platform/NorthCX_Personas.md`.
2. **Where it is going:** `00-platform/NorthCX_Agent-Platform-Design.md`, the build direction from 2026-11-18 (re-platform in place: an Agent API and a tool gateway, then Chat, Agent Studio, Integrations and Automations). Its section 13 sets the priorities.
3. **Where the project stands:** `12-project/NorthCX_Project-Status.md` (one page).
4. **One area at a time:** the overview in each area folder below.
5. **Why things are the way they are:** `12-project/NorthCX_Decision-Log.md`.

## The areas
| Folder | Area | Start with |
|---|---|---|
| `00-platform/` | What NorthCX is, how it fits together, where it is going | [`NorthCX_Product-Definition.md`](00-platform/NorthCX_Product-Definition.md), [`NorthCX_Agent-Platform-Design.md`](00-platform/NorthCX_Agent-Platform-Design.md) |
| `01-chat/` | Channels, SDK and widget, streaming, hand-off to people | [`NorthCX_Chat-Overview.md`](01-chat/NorthCX_Chat-Overview.md) |
| `02-studio/` | Building, testing and releasing agents in the admin console; its design | [`NorthCX_Studio-Overview.md`](02-studio/NorthCX_Studio-Overview.md) |
| `03-automations/` | Staff routines: triggers, steps, approval by a person | [`NorthCX_Automations-Overview.md`](03-automations/NorthCX_Automations-Overview.md) |
| `04-integrations/` | Connectors, webhooks, the HTTP API | [`NorthCX_Integrations-Overview.md`](04-integrations/NorthCX_Integrations-Overview.md) |
| `05-knowledge-memory/` | Knowledge sources and retrieval; history, facts and memory | [`NorthCX_Knowledge-Memory-Overview.md`](05-knowledge-memory/NorthCX_Knowledge-Memory-Overview.md) |
| `06-testing-evaluation/` | Simulations, judge, regression, release gate; product testing | [`NorthCX_Testing-Overview.md`](06-testing-evaluation/NorthCX_Testing-Overview.md) |
| `07-observability/` | Traces, metrics, analytics, alerts, reliability and cost | [`NorthCX_Observability-Overview.md`](07-observability/NorthCX_Observability-Overview.md) |
| `08-governance-safety/` | Guardrails, approvals, access, audit, data controls, tenancy, security | [`NorthCX_Governance-Overview.md`](08-governance-safety/NorthCX_Governance-Overview.md) |
| `09-models/` | Providers, fallbacks, budgets, model selection | [`NorthCX_Models-Overview.md`](09-models/NorthCX_Models-Overview.md) |
| `10-releases/` | Agent versions and rollouts; releasing NorthCX itself | [`NorthCX_Releases-Overview.md`](10-releases/NorthCX_Releases-Overview.md) |
| `11-operations/` | Deployment, network needs, settings, runbooks, database, performance | [`NorthCX_Operations-Overview.md`](11-operations/NorthCX_Operations-Overview.md) |
| `12-project/` | Status, roadmap, plans, catalog, stories, decisions, glossary | [`NorthCX_Project-Status.md`](12-project/NorthCX_Project-Status.md) |
| `13-workspace/` | The later staff product (Workspace, Pilot, personal intelligence) | [`NorthCX_Workspace-Spec.md`](13-workspace/NorthCX_Workspace-Spec.md) |
| `00-reference/` | Named research: other companies' products and reference projects | [`NorthCX_Reference.md`](00-reference/NorthCX_Reference.md), [`NorthCX_Agent-Platform-Research.md`](00-reference/NorthCX_Agent-Platform-Research.md) |
| `99-archive/` | Superseded documents, each pointing to its replacement | |

## Which document is the master for what
| Topic | Master document |
|---|---|
| Vision, scope, market | `00-platform/NorthCX_Product-Definition.md` |
| Build direction and module design | `00-platform/NorthCX_Agent-Platform-Design.md` |
| Requirements (FR1 to FR41) | `00-platform/NorthCX_PRD.md` |
| Feature list and state | `12-project/NorthCX_Feature-Catalog.md` (section 12 states are out of date; see its correction) |
| Staff platform tabs, names and screens | `02-studio/NorthCX_Platform-Features-and-Tabs.md` |
| Agent run loop | `00-platform/NorthCX_Agent-Runtime.md` |
| Channels and voice | `01-chat/NorthCX_Channels-and-Voice.md` and `01-chat/NorthCX_Voice.md` (bridge protocol) |
| Hand-offs and approvals | `01-chat/NorthCX_Handoff-and-Approvals-Spec.md` |
| Studio as built | `02-studio/NorthCX_Studio.md` |
| Automations | `03-automations/NorthCX_Automations-Spec.md` |
| Connectors and integrations | `04-integrations/NorthCX_Integrations.md` |
| API | `04-integrations/NorthCX_API-Design.md` and the generated reference in `api/` |
| Knowledge retrieval | `05-knowledge-memory/NorthCX_Knowledge-Design.md` |
| Memory | `05-knowledge-memory/NorthCX_Knowledge-and-Memory.md` |
| Simulations and release gate | `06-testing-evaluation/NorthCX_Simulation-and-Evals.md` |
| Testing | `06-testing-evaluation/NorthCX_Testing-Strategy.md` |
| Observability | `07-observability/NorthCX_Observability.md` |
| Guardrails | `08-governance-safety/NorthCX_Guardrails-and-Supervisors.md` |
| Security | `08-governance-safety/NorthCX_Threat-Model.md` and `08-governance-safety/NorthCX_Security-and-Compliance.md` |
| Tenancy | `08-governance-safety/NorthCX_Tenancy-ADR.md` (partly built) |
| Models | `09-models/NorthCX_Model-Providers.md` (built) and `09-models/NorthCX_Hybrid-Model-Selection.md` (partly built) |
| Agent versions and rollout | `10-releases/NorthCX_Release-Management.md` |
| Finishing 1.0 | `10-releases/NorthCX_Release-Checklist.md` |
| Deployment and every setting | `11-operations/NorthCX_Deployment-Guide.md` (checked by a test) |
| Database tables | `11-operations/NorthCX_Database-Schema.md` (checked by a test) |
| Phases, work packages and the seven-stage process | `12-project/NorthCX_Agent-Platform-Plan.md` |
| Epic designs and plan decisions D1 to D11 | `12-project/NorthCX_Gap-Closure-Plan.md` |
| Prompts for Claude Code sessions | `12-project/NorthCX_Session-Prompts.md` |
| Terms | `12-project/NorthCX_Glossary.md` |

## Folders
| Folder | Documents |
|---|---|
| `00-platform/` | Product-Definition, Product-Overview (snapshot), PRD, Personas, Success-Metrics, Pricing-Model (blocked on D1), Competitive-Analysis, Agent-Platform-Design, System-Architecture, Agent-Runtime |
| `00-reference/` | Reference, North-Gap-Analysis, Feature-Research-2026-11, Reference-Sources, Agent-Platform-Research, Competitor-Landscape, Agent-UI-References. The only folder where other companies' products are named. |
| `01-chat/` | Chat-Overview, Channels-and-Voice, Voice (bridge protocol), Client-SDK, Handoff-and-Approvals-Spec, AG-UI-Check, AG-UI-Endpoint, Test-Console |
| `02-studio/` | Studio-Overview, Studio, Admin-Platform-Design, Agent-Hub-Design, Platform-Features-and-Tabs, UI-UX-Design-Proposal (the approved glass look: colour, surfaces, type, layout, motion, navigation modes, tab icons), Design-System, Templates; `mockups/` holds the HTML sources of the screens in `assets/design/` |
| `03-automations/` | Automations-Overview, Automations-Spec |
| `04-integrations/` | Integrations-Overview, Integrations, Tool-Gateway, MCP-Integration, Integration-Catalogue, API-Design |
| `05-knowledge-memory/` | Knowledge-Memory-Overview, Knowledge-Design, Knowledge-and-Memory |
| `06-testing-evaluation/` | Testing-Overview, Simulation-and-Evals, Testing-Strategy |
| `07-observability/` | Observability-Overview, Observability, Reliability-and-Cost |
| `08-governance-safety/` | Governance-Overview, Guardrails-and-Supervisors, Data-Flow, Tenancy-ADR, Code-Reuse-Policy, Threat-Model, Security-and-Compliance, Security-Review, Tenant-Isolation-Threat-Model, Penetration-Test-Brief, Licenses |
| `09-models/` | Models-Overview, Model-Providers, Hybrid-Model-Selection, Local-Models-Guide |
| `10-releases/` | Releases-Overview, Release-Management, Release-Checklist |
| `11-operations/` | Operations-Overview, Deployment-Guide, Owner-Runbooks, Network-Needs, Performance, Database-Schema, Repo-Structure |
| `12-project/` | Project-Status, Roadmap, Agent-Platform-Plan, Implementation-Plan, Gap-Closure-Plan, Feature-Catalog, Feature-Spec, User-Stories, User-Journey, Non-Functional-Requirements, Tech-Stack-Decisions, Build-vs-Adopt, Decision-Log, Glossary, Docs-Completion-Checklist, Session-Prompts, Contributing (the short version is `CONTRIBUTING.md` at the repository root; see also `CHANGELOG.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`) |
| `13-workspace/` | The later staff product: Workspace-Spec, Pilot-Spec, Personal-Intelligence-Spec, Staff-Platform-Architecture |
| `99-archive/` | Superseded documents, each with a pointer to its replacement: the finished 1.0 phase, sprint and next-features plans, the 1.0 implementation checklist, the capability matrix, the memory design, simulation testing, the Studio UI spec and the Admin design rounds |
| `api/` | Generated API reference: `openapi.json` and `index.html` (do not edit; run `python scripts/gen_api_reference.py`) |

## Conventions
- File names: `NorthCX_<Name>.md` inside `NN-folder/`; each area folder has a `NorthCX_<Area>-Overview.md`.
- The first line under the title is the header: Status, Updated, Master for.
- Documents outside `00-reference/` do not name other companies' products.
- A change to behaviour updates its master document and adds a decision to the decision log in the same commit.
- A change to an area updates that area's overview when what is built or the gaps change.
- Mockups use invented sample data and say so.
