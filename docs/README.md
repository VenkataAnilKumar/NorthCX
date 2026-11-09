# NorthCX Documentation

NorthCX is an open-source customer-experience agent platform built on the Claude API. Documents are organized in numbered phase folders.

> All external research, benchmarks and third-party component selections live only in `00-reference/NorthCX_Reference.md`. Other documents describe NorthCX and point to the Reference where needed.

## Reading order
| Folder | Documents |
|---|---|
| `00-reference/` | `NorthCX_Reference.md` (all external research and component selections), `NorthCX_North-Gap-Analysis.md` (comparison with Cohere North and build plan for a "North for CX"), `NorthCX_Feature-Research-2026-11.md` (market research on agent, user and admin platform features) |
| `01-product/` | Product-Definition, PRD, Personas, Success-Metrics, Pricing-Model, Templates, Product-Overview |
| `02-market/` | Competitive-Analysis |
| `03-specs/` | Feature-Catalog, Feature-Spec, Handoff-and-Approvals-Spec, Release-Management, Non-Functional-Requirements, User-Stories, User-Journey, Workspace-Spec, Pilot-Spec, Personal-Intelligence-Spec, Automations-Spec (the four after-1.0 staff-platform specifications) |
| `04-ai-architecture/` | Agent-Runtime, Agent-Capability-Matrix, Guardrails-and-Supervisors, Knowledge-and-Memory, Simulation-and-Evals, Data-Flow, Memory-Design, Model-Providers, Hybrid-Model-Selection (proposed), Simulation-Testing |
| `05-technical/` | System-Architecture, Tech-Stack-Decisions, Build-vs-Adopt, Code-Reuse-Policy, Channels-and-Voice, Voice, Client-SDK, Integrations, API-Design, Database-Schema, Observability, Repo-Structure, Reliability-and-Cost, Knowledge-Design, Staff-Platform-Architecture (proposed) |
| `06-security/` | Security-and-Compliance, Threat-Model, Security-Review, Licenses |
| `07-design/` | Studio, Studio-UI-Spec, Design-System, Agent-Hub-Design (proposed Agent Hub and predefined agents), Platform-Features-and-Tabs (the consolidated specification of tabs and features), Admin-Platform-Design (proposed screens and navigation for the admin platform and staff workspace; `mockups/` holds the HTML sources) |
| `08-implementation/` | Implementation-Phases, Sprint-Plan, Roadmap, Phase-Plan, Implementation-Checklist, Deployment-Guide, Testing-Strategy, Performance, Next-Features-Plan, Release-Checklist, Gap-Closure-Plan, Project-Status, Implementation-Plan |
| `09-project/` | Glossary, Decision-Log, Contributing (the short version is `CONTRIBUTING.md` at the repository root; see also `CHANGELOG.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`) |
| `api/` | Generated API reference: `openapi.json` and `index.html` (do not edit; run `python scripts/gen_api_reference.py`) |

All documents are drafts. Each is named `NorthCX_<Name>.md`.

## Conventions
- File names: `NorthCX_<Name>.md` inside `NN-folder/`.
- Each doc starts with a status line (Draft / Review / Final) and lists its open decisions.
- Documents outside `00-reference/` do not name external products or projects.
