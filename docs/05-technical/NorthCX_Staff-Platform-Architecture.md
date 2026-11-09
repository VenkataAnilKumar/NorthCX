# NorthCX Staff Platform Architecture

Status: **Proposed design, 2026-11-09; none of it is built.** How the Workspace, the extended Admin app, the Pilot, automations and personal intelligence fit on the existing platform. It extends `NorthCX_System-Architecture.md`; work packages are in `../08-implementation/NorthCX_Implementation-Plan.md` (E1, E2, E3, E5, E6, E8, E22). Requirements: `../03-specs/NorthCX_Workspace-Spec.md` and its companions.

## 1. Principles
1. **One engine, pointed at staff.** The staff assistant runs on the same agent runtime, supervisors, approvals, traces and audit as customer agents. Staff agents are marked `audience: staff`; customer agents cannot use staff tools.
2. **Permissions travel with the person.** Every tool call carries the signed-in person's permissions (E5.2). A tool checks them itself; an assistant can never reach more than its user.
3. **Fail closed.** A search provider that cannot prove access returns nothing. A write without an approval rule does not run.
4. **Masked by default.** Customer personal data is masked before it reaches a model, a saved output or a list outside the live conversation.
5. **Replaceable parts.** Models, search providers, connectors and storage sit behind interfaces, as for the customer side.

## 2. Components
| Component | Role | New or existing |
|---|---|---|
| `apps/workspace` (Next.js) | Staff web app built on `packages/ui` and `packages/api-client` | New (first slice on the feature branch) |
| `apps/studio` (Next.js) | Admin app, regrouped navigation, Agent Hub, Builder, personal settings | Existing, extended |
| `packages/ui`, `packages/api-client` | Design system ("glass", themes, accessibility), typed client | New (in progress) |
| Workspace API (`/v1/workspace/*`) | Streamed chat bound to the signed-in identity, tasks, spaces, outputs, search | New (E5.4, E6) |
| Task engine | Runs Pilot tasks: plan, approval, background steps, pause, redirect, stop | New (E5, E8 runner reused) |
| Search framework | `search(query, identity)` over providers with reciprocal rank fusion | New (E5.6) |
| Memory service | Staff and team memory namespaces with recall, edit and erase | New (E5.5); customer memory exists |
| Provider registry and selector | `provider:model` names, capabilities, prices, constraint-first selection | Registry built (WP1.1 to 1.2); selector proposed (WP1.9+) |
| Automation scheduler and runner | Claim-once scheduler, durable runs, leases | New (E8); scheduler pattern exists for crawls |
| Approvals, hand-offs, audit chain, traces | Reused unchanged | Existing |
| Tenancy | Tenant context, tenant predicate, row-level security | New (E2); a prerequisite for the Workspace |

## 3. A Pilot task, end to end
1. The Workspace posts the task (assistant, space, style, attachments, model mode) to the Workspace API with the person's session.
2. The API builds a **task context**: identity, roles, tenant, space, the chosen layers (organization rules, team, space, personal instructions) and switched-on memory, in fixed precedence. Untrusted text (sources, memory, files) is labelled as data.
3. The **selector** picks a model tier from the data-policy constraints first (is customer data involved? what may leave?), then qualification, then rules, then cost. The choice and reason are written to the trace.
4. For Research and Do the assistant returns a **plan**; the task waits in `planned`. Approval creates the run; the run is leased to one worker.
5. Steps call staff tools through the normal tool layer. Reads are filtered by the person's permissions; conversations are masked; every call is traced and audited without content.
6. A write step raises an **approval request** (existing approvals) addressed to the person, and the run waits.
7. The result is stored as a versioned **output** with its sources, steps, model and cost. Events stream to the window throughout.
8. A pause, redirect or stop is a message to the run; redirect rewrites only the remaining plan steps.

## 4. Proposed data model (names provisional; each new table needs `tenant_id`)
`workspace_tasks` (id, owner, assistant, space, style, state, plan, estimate, limits), `task_steps` (task, order, kind, state, trace reference, cost), `spaces` and `space_members` (instructions, visibility), `space_items` (files, sources, chats), `outputs` and `output_versions` (kind, sources, model, cost, shared-with), `staff_memories` (scope, owner, content, origin, status), `staff_instructions` (layer, owner, text, locked), `skills`, `automations` and `automation_runs` (E8.1), `hub_installs` (template, version, settings), `saved_views`. The document `NorthCX_Database-Schema.md` is updated when each migration lands; the sync test fails the build if a table is missing from it.

## 5. Proposed API surface (all under `/v1/workspace`, all permission-checked in the route table)
`POST /chat` (stream), `POST/GET /tasks`, `POST /tasks/{id}/approve|pause|redirect|stop`, `GET /tasks/{id}/steps` (stream), `GET/POST /spaces`, `GET/POST /outputs`, `GET /search`, `GET/PUT /me/instructions`, `GET/POST/DELETE /me/memory`, `GET/POST /automations`, `POST /automations/{id}/kill`. Admin additions: `/v1/hub/*`, `/v1/policies`, `/v1/models/rules`. Every route is added to `ROUTE_PERMISSIONS`, the golden route snapshot and the generated reference, as today.

## 6. Permissions
Roles come from groups (E3). Workspace roles: staff, reviewer, team lead, administrator. Team (Quality, Performance) and Customers need the lead or reviewer role. A hub entry cannot widen a tool's scope. Space visibility is private or team; administrators of the app cannot read private spaces or personal memory.

## 7. Data and privacy
Per-tenant storage with row-level security (E2). Retention, export and erase per person and per space. Outputs inherit the strictest classification of their sources. Sensitive conversations are pinned to private or local models; the fallback chain is filtered by the same constraint before any call.

## 8. Reliability and cost
Task and automation runs are durable and leased; a worker restart resumes from the last finished step. Per-task and per-tenant budgets use the shared limiter. A model failure ends a step with a reason; the person chooses retry, skip or stop.

## 9. Front-end architecture
Both apps share `packages/ui` (tokens, glass surfaces, themes through `data-` attributes, accessibility settings, shell and navigation components) and `packages/api-client`. Preferences are stored per browser first and per user when the backend exists. Server components fetch with the person's session; the browser never holds a long-lived API key.

## 10. Open design points
Row-level security versus explicit tenant predicates (WP2.1 decides); where Pilot step events are stored (the trace store versus a task table); whether search results are cached per person.
