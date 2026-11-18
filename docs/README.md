# NorthCX Documentation

NorthCX is an open-source, self-hosted platform for supervised customer-experience agents, built on the Claude API. Every document starts with one line: **Status** (Built, Partly built, Designed, Plan, Reference or Archive), **Updated** and **Master for** (what it is the source of truth for).

## Start here
1. **What it is and who it is for:** `00-platform/NorthCX_Product-Definition.md`, then `00-platform/NorthCX_Personas.md`.
2. **Where the project stands:** `12-project/NorthCX_Project-Status.md` (one page).
3. **What is built:** `12-project/NorthCX_Feature-Catalog.md` (every feature with its state) and `00-platform/NorthCX_System-Architecture.md`.
4. **What is designed next (the staff platform):** `02-studio/NorthCX_Platform-Features-and-Tabs.md`, then the specifications in `13-workspace/` (Workspace, Pilot, Personal Intelligence) and `03-automations/` (Automations), and `13-workspace/NorthCX_Staff-Platform-Architecture.md`.
5. **How it will be built:** `12-project/NorthCX_Implementation-Plan.md` (the master plan) and `12-project/NorthCX_Roadmap.md` (one page).
6. **Why things are the way they are:** `12-project/NorthCX_Decision-Log.md`.

## Which document is the master for what
| Topic | Master document |
|---|---|
| Vision, scope, market | `00-platform/NorthCX_Product-Definition.md` |
| Requirements (FR1 to FR41) | `00-platform/NorthCX_PRD.md` |
| Feature list and state | `12-project/NorthCX_Feature-Catalog.md` |
| Staff platform tabs, names and screens | `02-studio/NorthCX_Platform-Features-and-Tabs.md` |
| Agent run loop | `00-platform/NorthCX_Agent-Runtime.md` |
| Guardrails | `08-governance-safety/NorthCX_Guardrails-and-Supervisors.md` |
| Memory | `05-knowledge-memory/NorthCX_Knowledge-and-Memory.md` |
| Knowledge retrieval | `05-knowledge-memory/NorthCX_Knowledge-Design.md` |
| Tenancy | `08-governance-safety/NorthCX_Tenancy-ADR.md` (partly built) |
| Models | `09-models/NorthCX_Model-Providers.md` (built) and `NorthCX_Hybrid-Model-Selection.md` (partly built) |
| Simulations and release gate | `06-testing-evaluation/NorthCX_Simulation-and-Evals.md` |
| Channels and voice | `01-chat/NorthCX_Channels-and-Voice.md` and `NorthCX_Voice.md` (bridge protocol) |
| API | `04-integrations/NorthCX_API-Design.md` and the generated reference in `api/` |
| Database tables | `11-operations/NorthCX_Database-Schema.md` (checked by a test) |
| Security | `08-governance-safety/NorthCX_Threat-Model.md` and `NorthCX_Security-and-Compliance.md` |
| Deployment and every setting | `11-operations/NorthCX_Deployment-Guide.md` (checked by a test) |
| Testing | `06-testing-evaluation/NorthCX_Testing-Strategy.md` |
| Epic designs and plan decisions D1 to D11 | `12-project/NorthCX_Gap-Closure-Plan.md` |
| Terms | `12-project/NorthCX_Glossary.md` |

## Folders
| Folder | Documents |
|---|---|
| `00-platform/` | What NorthCX is and how it fits together: Product-Definition, Product-Overview (snapshot), PRD, Personas, Success-Metrics, Pricing-Model (blocked on D1), Competitive-Analysis, Agent-Platform-Design, System-Architecture, Agent-Runtime |
| `00-reference/` | Reference, North-Gap-Analysis, Feature-Research-2026-11, Reference-Sources. The only folder where other companies' products are named. |
| `01-chat/` | Channels-and-Voice, Voice (bridge protocol), Client-SDK, Handoff-and-Approvals-Spec |
| `02-studio/` | Studio, Admin-Platform-Design, Agent-Hub-Design, Platform-Features-and-Tabs, UI-UX-Design-Proposal (the approved glass look: colour, surfaces, type, layout, motion, navigation modes, tab icons), Design-System, Templates; `mockups/` holds the HTML sources of the screens in `assets/design/` |
| `03-automations/` | Automations-Spec |
| `04-integrations/` | Integrations, API-Design |
| `05-knowledge-memory/` | Knowledge-Design, Knowledge-and-Memory |
| `06-testing-evaluation/` | Simulation-and-Evals, Testing-Strategy |
| `07-observability/` | Observability, Reliability-and-Cost |
| `08-governance-safety/` | Guardrails-and-Supervisors, Data-Flow, Tenancy-ADR, Code-Reuse-Policy, Threat-Model, Security-and-Compliance, Security-Review, Tenant-Isolation-Threat-Model, Penetration-Test-Brief, Licenses |
| `09-models/` | Model-Providers, Hybrid-Model-Selection |
| `10-releases/` | Release-Management, Release-Checklist |
| `11-operations/` | Deployment-Guide, Owner-Runbooks, Performance, Database-Schema, Repo-Structure |
| `12-project/` | Project-Status, Roadmap, Implementation-Plan, Gap-Closure-Plan, Feature-Catalog, Feature-Spec, User-Stories, User-Journey, Non-Functional-Requirements, Tech-Stack-Decisions, Build-vs-Adopt, Decision-Log, Glossary, Docs-Completion-Checklist, Session-Prompts, Contributing (the short version is `CONTRIBUTING.md` at the repository root; see also `CHANGELOG.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`) |
| `13-workspace/` | The later staff product: Workspace-Spec, Pilot-Spec, Personal-Intelligence-Spec, Staff-Platform-Architecture |
| `99-archive/` | Superseded documents, each with a pointer to its replacement: the finished 1.0 phase, sprint and next-features plans, the 1.0 implementation checklist, the capability matrix, the memory design, simulation testing, the Studio UI spec and the Admin design rounds |
| `api/` | Generated API reference: `openapi.json` and `index.html` (do not edit; run `python scripts/gen_api_reference.py`) |

## Conventions
- File names: `NorthCX_<Name>.md` inside `NN-folder/`.
- The first line under the title is the header: Status, Updated, Master for.
- Documents outside `00-reference/` do not name other companies' products.
- A change to behaviour updates its master document and adds a decision to the decision log in the same commit.
- Mockups use invented sample data and say so.
