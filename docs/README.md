# NorthCX Documentation

NorthCX is an open-source, self-hosted platform for supervised customer-experience agents, built on the Claude API. Every document starts with one line: **Status** (Built, Partly built, Designed, Plan, Reference or Archive), **Updated** and **Master for** (what it is the source of truth for).

## Start here
1. **What it is and who it is for:** `01-product/NorthCX_Product-Definition.md`, then `01-product/NorthCX_Personas.md`.
2. **Where the project stands:** `08-implementation/NorthCX_Project-Status.md` (one page).
3. **What is built:** `03-specs/NorthCX_Feature-Catalog.md` (every feature with its state) and `05-technical/NorthCX_System-Architecture.md`.
4. **What is designed next (the staff platform):** `07-design/NorthCX_Platform-Features-and-Tabs.md`, then the four specifications in `03-specs/` (Workspace, Pilot, Personal Intelligence, Automations) and `05-technical/NorthCX_Staff-Platform-Architecture.md`.
5. **How it will be built:** `08-implementation/NorthCX_Implementation-Plan.md` (the master plan) and `08-implementation/NorthCX_Roadmap.md` (one page).
6. **Why things are the way they are:** `09-project/NorthCX_Decision-Log.md`.

## Which document is the master for what
| Topic | Master document |
|---|---|
| Vision, scope, market | `01-product/NorthCX_Product-Definition.md` |
| Requirements (FR1 to FR41) | `01-product/NorthCX_PRD.md` |
| Feature list and state | `03-specs/NorthCX_Feature-Catalog.md` |
| Staff platform tabs, names and screens | `07-design/NorthCX_Platform-Features-and-Tabs.md` |
| Agent run loop | `04-ai-architecture/NorthCX_Agent-Runtime.md` |
| Guardrails | `04-ai-architecture/NorthCX_Guardrails-and-Supervisors.md` |
| Memory | `04-ai-architecture/NorthCX_Knowledge-and-Memory.md` |
| Knowledge retrieval | `05-technical/NorthCX_Knowledge-Design.md` |
| Tenancy | `05-technical/NorthCX_Tenancy-ADR.md` (partly built) |
| Models | `04-ai-architecture/NorthCX_Model-Providers.md` (built) and `NorthCX_Hybrid-Model-Selection.md` (partly built) |
| Simulations and release gate | `04-ai-architecture/NorthCX_Simulation-and-Evals.md` |
| Channels and voice | `05-technical/NorthCX_Channels-and-Voice.md` and `NorthCX_Voice.md` (bridge protocol) |
| API | `05-technical/NorthCX_API-Design.md` and the generated reference in `api/` |
| Database tables | `05-technical/NorthCX_Database-Schema.md` (checked by a test) |
| Security | `06-security/NorthCX_Threat-Model.md` and `NorthCX_Security-and-Compliance.md` |
| Deployment and every setting | `08-implementation/NorthCX_Deployment-Guide.md` (checked by a test) |
| Testing | `08-implementation/NorthCX_Testing-Strategy.md` |
| Epic designs and plan decisions D1 to D11 | `08-implementation/NorthCX_Gap-Closure-Plan.md` |
| Terms | `09-project/NorthCX_Glossary.md` |

## Folders
| Folder | Documents |
|---|---|
| `00-reference/` | Reference, North-Gap-Analysis, Feature-Research-2026-11. The only folder where other companies' products are named. |
| `01-product/` | Product-Definition, PRD, Personas, Success-Metrics, Pricing-Model (blocked on D1), Templates, Product-Overview (snapshot) |
| `02-market/` | Competitive-Analysis |
| `03-specs/` | Feature-Catalog, Feature-Spec, Handoff-and-Approvals-Spec, Release-Management, Non-Functional-Requirements, User-Stories, User-Journey, Workspace-Spec, Pilot-Spec, Personal-Intelligence-Spec, Automations-Spec |
| `04-ai-architecture/` | Agent-Runtime, Guardrails-and-Supervisors, Knowledge-and-Memory, Simulation-and-Evals, Data-Flow, Model-Providers, Hybrid-Model-Selection |
| `05-technical/` | System-Architecture, Staff-Platform-Architecture, Tech-Stack-Decisions, Build-vs-Adopt, Code-Reuse-Policy, Channels-and-Voice, Voice, Client-SDK, Integrations, API-Design, Database-Schema, Observability, Repo-Structure, Reliability-and-Cost, Knowledge-Design |
| `06-security/` | Security-and-Compliance, Threat-Model, Security-Review, Licenses |
| `07-design/` | Platform-Features-and-Tabs, Admin-Platform-Design, Agent-Hub-Design, Design-System, UI-UX-Design-Proposal (the approved glass look: colour, surfaces, type, layout, motion, navigation modes, tab icons), Studio; `mockups/` holds the HTML sources of the screens in `assets/design/` |
| `08-implementation/` | Implementation-Plan, Gap-Closure-Plan, Roadmap, Project-Status, Release-Checklist, Deployment-Guide, Testing-Strategy, Performance |
| `09-project/` | Decision-Log, Glossary, Docs-Completion-Checklist, Contributing (the short version is `CONTRIBUTING.md` at the repository root; see also `CHANGELOG.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`) |
| `99-archive/` | Superseded documents, each with a pointer to its replacement: the finished 1.0 phase, sprint and next-features plans, the 1.0 implementation checklist, the capability matrix, the memory design, simulation testing, the Studio UI spec and the Admin design rounds |
| `api/` | Generated API reference: `openapi.json` and `index.html` (do not edit; run `python scripts/gen_api_reference.py`) |

## Conventions
- File names: `NorthCX_<Name>.md` inside `NN-folder/`.
- The first line under the title is the header: Status, Updated, Master for.
- Documents outside `00-reference/` do not name other companies' products.
- A change to behaviour updates its master document and adds a decision to the decision log in the same commit.
- Mockups use invented sample data and say so.
