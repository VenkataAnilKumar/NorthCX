# NorthCX Roadmap

Status: **Plan**. Updated: 2026-11-18. Master for: the one-page order of releases.

**Update (2026-11-18).** The order of work after 1.0 now follows `../00-platform/NorthCX_Agent-Platform-Design.md` (phasing in section 10, priorities in section 13): the tool gateway and MCP with the first connectors, then guided Studio for non-engineers and shadow mode, then operator experience. The table below is the plan of 2026-11-09 and has not been re-sequenced yet.

| Horizon | Release | Themes | State |
|---|---|---|---|
| Done | 1.0 phases 1 to 6 | Runtime, safety, approvals, simulations and releases, Studio, six channels, knowledge, analytics | Built; release candidate 1.0.0-rc.1 |
| Now | Wave 0 (finish 1.0) | Live-model pass, independent penetration test, tagging 1.0.0 | Code work done; owner actions outstanding |
| Next | 1.1 (Wave 1) | Model providers and cost governance (E1), identity (E3), MCP (E4) | Started: WP1.1 and WP1.2 built |
| Then | 1.2 (Wave 2) | Multi-tenancy (E2), staff Workspace backend (E5), outputs (E6), Agent Hub (E22, proposed), guardrail policies, support access | Designed |
| Then | 1.3 (Wave 3) | Automations (E8, E14), connectors (E9), QA scoring (E7), workspace analytics (E15) | Designed |
| Later | 1.4 (Wave 4) and beyond | Metering and plans (E10, needs D1), deployment kit (E11), trust pack and developer portal (E12), surfaces in other apps | Planned |

Detail of the finished 1.0 phases: `../99-archive/NorthCX_Phase-Plan.md`.

The seven implementation phases that order this work are in section 3a of `NorthCX_Implementation-Plan.md` (decision 176).

## Principles
Safety and testability before reach; reach before polish; tenancy before anything that stores per-customer credentials or workspace data.

## Open decisions
D1, open versus commercial: deferred on purpose; needed before metering and billing (Phase 6) or earlier if a sale or hosted service is planned (decision 176). Settled: the Studio was built; the first connectors are a ticketing pack, then Slack, then Salesforce (D6, decision 170); the initial vertical focus is as in the Product Definition, still to be confirmed by pilots.

## After 1.0
The step-by-step work packages, gates and owner actions are in `NorthCX_Implementation-Plan.md`.

The detailed plan for the work that follows 1.0 (model providers, multi-tenancy, identity, the staff workspace, automations, connectors, metering and deployment) is `NorthCX_Gap-Closure-Plan.md`. It reorders the stages proposed in `00-reference/NorthCX_North-Gap-Analysis.md` so that tenancy comes before anything that stores per-customer credentials or workspace data.

## After 1.0: the staff platform (designed 2026-11-09)
The order is: providers and cost governance (E1), tenancy (E2), identity (E3), the staff backend (E5) with libraries and outputs (E6), the Agent Hub (E22), then automations (E8, E14), connectors (E9), QA scoring (E7) and metering (E10). First Workspace release (decided, decision 162): Inbox, Approvals, Pilot, Assistants, Search and Library. Customers is a second-release tab; web search for assistants is later and off by default. Details: `NorthCX_Implementation-Plan.md`; screens and rules: `../02-studio/NorthCX_Platform-Features-and-Tabs.md`.
