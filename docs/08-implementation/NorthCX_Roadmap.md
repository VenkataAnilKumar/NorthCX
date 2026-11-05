# NorthCX Roadmap

Status: Draft

| Horizon | Phases | Themes |
|---|---|---|
| Now | 1 (complete) | Tested runtime, HTTP API, widget, example agent |
| Next | 2 | Simulation testing, persistence, approval resume, versions and rollback, roles and audit |
| Later | 3 | Email and messaging, knowledge, safety extensions, environments, trace export |
| Future | 4-5 | Studio, insights, experiments, voice, agent assist |
| Exploring | 6+ | Agent-assisted building, natural-language analytics, multi-tenancy, metering and outcome billing |

Detail: `NorthCX_Phase-Plan.md`.

## Principles
Safety and testability before reach; reach before polish; Studio after the definition format is stable.

## Open decisions
Studio build vs adopt, initial vertical focus, connector scope.

## After 1.0
The detailed plan for the work that follows 1.0 (model providers, multi-tenancy, identity, the staff workspace, automations, connectors, metering and deployment) is `NorthCX_Gap-Closure-Plan.md`. It reorders the stages proposed in `00-reference/NorthCX_North-Gap-Analysis.md` so that tenancy comes before anything that stores per-customer credentials or workspace data.
