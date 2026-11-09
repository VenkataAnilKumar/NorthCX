# NorthCX Roadmap

Status: **Plan**. Updated: 2026-11-09. Master for: the one-page order of releases.

| Horizon | Phases | Themes |
|---|---|---|
| Now | 1 (complete) | Tested runtime, HTTP API, widget, example agent |
| Next | 2 | Simulation testing, persistence, approval resume, versions and rollback, roles and audit |
| Later | 3 | Email and messaging, knowledge, safety extensions, environments, trace export |
| Future | 4-5 | Studio, insights, experiments, voice, agent assist |
| Exploring | 6+ | Agent-assisted building, natural-language analytics, multi-tenancy, metering and outcome billing |

Detail of the finished 1.0 phases: `../99-archive/NorthCX_Phase-Plan.md`.

## Principles
Safety and testability before reach; reach before polish; Studio after the definition format is stable.

## Open decisions
Studio build vs adopt, initial vertical focus, connector scope.

## After 1.0
The step-by-step work packages, gates and owner actions are in `NorthCX_Implementation-Plan.md`.

The detailed plan for the work that follows 1.0 (model providers, multi-tenancy, identity, the staff workspace, automations, connectors, metering and deployment) is `NorthCX_Gap-Closure-Plan.md`. It reorders the stages proposed in `00-reference/NorthCX_North-Gap-Analysis.md` so that tenancy comes before anything that stores per-customer credentials or workspace data.

## After 1.0: the staff platform (designed 2026-11-09)
The order is: providers and cost governance (E1), tenancy (E2), identity (E3), the staff backend (E5) with libraries and outputs (E6), the Agent Hub (E22), then automations (E8, E14), connectors (E9), QA scoring (E7) and metering (E10). First Workspace release (recommended): Inbox, Approvals, Pilot, Assistants, Search and Library. Customers is a second-release tab; web search for assistants is later and off by default. Details: `NorthCX_Implementation-Plan.md`; screens and rules: `../07-design/NorthCX_Platform-Features-and-Tabs.md`.
