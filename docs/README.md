# NorthCX Documentation

NorthCX is an open-source customer-experience agent platform built on the Claude API. Documents are organized in numbered phase folders.

> All external research, benchmarks and third-party component selections live only in `00-reference/NorthCX_Reference.md`. Other documents describe NorthCX and point to the Reference where needed.

## Reading order
| Folder | Status | Documents |
|---|---|---|
| `00-reference/` | Done | `NorthCX_Reference.md` |
| `01-product/` | Draft | `NorthCX_Product-Definition.md`, `NorthCX_PRD.md`, `NorthCX_Personas.md`, `NorthCX_Pricing-Model.md` |
| `02-market/` | Draft | `NorthCX_Competitive-Analysis.md` |
| `03-specs/` | Draft | `NorthCX_Feature-Spec.md`, `NorthCX_User-Stories.md`, `NorthCX_User-Journey.md` |
| `04-ai-architecture/` | Planned | Agent-Runtime, Capability-Matrix, Guardrails, Knowledge-and-Memory, Simulation-and-Evals, Data-Flow |
| `05-technical/` | Draft | `NorthCX_System-Architecture.md`, `NorthCX_Tech-Stack-Decisions.md`, `NorthCX_Build-vs-Adopt.md`; planned: Channels-and-Voice, Integrations, API-Design, Database-Schema, Observability, Repo-Structure |
| `06-security/` | Planned | Security-and-Compliance, Licenses |
| `07-design/` | Planned | Studio-UI-Spec, Design-System |
| `08-implementation/` | Planned | Implementation-Phases, Sprint-Plan, Roadmap, Checklist, Deployment-Guide |

## Conventions
- File names: `NorthCX_<Name>.md` inside `NN-folder/`.
- Each doc starts with a status line (Draft / Review / Final) and lists its open decisions.
- Documents outside `00-reference/` do not name external products or projects.
