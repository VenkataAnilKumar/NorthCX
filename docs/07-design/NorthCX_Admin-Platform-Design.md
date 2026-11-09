# NorthCX admin platform and staff workspace: design proposal

Status: **proposed** (2026-11-09). Nothing here is built yet except what the "Today" column says. The screens are static mockups with sample data (a company called "Acme Support" is invented for the pictures); they show intent, not working software. Sources: the current Studio, the implementation plan (E1, E3, E5, E7, E10), and the market research in `00-reference/NorthCX_Feature-Research-2026-11.md`.

Source files: `07-design/mockups/*.html` (regenerate with `python scripts/gen_design_mockups.py`, then `node scripts/shoot_mockups.js`). Images: `assets/design/`.

## 0. Layout decided on 2026-11-09 (supersedes the earlier arrangement where they differ)
The owner described the layout; the two windows are:

**Window 1, Workspace (the agent platform for staff).** Left side: a navigation list (**Chat, Search, Artifacts, Projects, Scheduled, Threads**), a "New chat" button, recent chats and the signed-in person. Right side: the **working space**, which shows the selected area. In Chat it is the conversation next to an artifact panel (the thing being produced, with copy, edit, share and schedule). Threads is where customer conversations that need a person are handled (the queue, the approval card, the draft reply).

| Left item | What it is | Mockup |
|---|---|---|
| Chat | Talk to a staff assistant (search, summarise, draft, report); answers cite sources; outputs open as artifacts | ![Chat](../assets/design/16-workspace-chat.png) |
| Search | One search across knowledge, conversations, hand-offs and artifacts, with the access reason on each result | ![Search](../assets/design/17-workspace-search.png) |
| Artifacts | Library of everything produced (summaries, drafts, reports, digests): versions, share to team, schedule, export. **Not drawn yet**; the artifact panel in Chat shows one | (see Chat) |
| Projects | Instructions, sources, chats and artifacts kept together for one piece of work (team or private) | ![Projects](../assets/design/18-workspace-projects.png) |
| Scheduled | Tasks that run on their own and leave an artifact or message; run history, pause, failures shown | ![Scheduled](../assets/design/19-workspace-scheduled.png) |
| Threads | Customer conversations: needs me, agent is handling, resolved; approvals and replies | ![Threads](../assets/design/20-workspace-threads.png) |

**Window 2, Settings and admin (the admin platform).** A wide settings app opened from the profile menu. Left: **Personal** options (Profile, Preferences, Memory, Connectors, MCP servers, Notifications, Privacy and data, Usage and limits, API keys, Security and sessions) and an **Organization (administrators)** group (People and groups, Agents, Models and budgets, Policies, Access, Audit and activity, Connectors (organization), Data residency, Billing and plan). Everyone sees the Personal group; the Organization group appears only for roles that can use it. The organization pages are the admin screens drawn earlier (sections 3 and below).

| Option | What it holds | Mockup |
|---|---|---|
| Profile | Name, team, language, time zone, default assistant, reply style, signature; roles shown read-only | ![Profile](../assets/design/21-settings-profile.png) |
| Memory | What assistants remember: read, edit, erase, export; personal and team; on/off | ![Memory](../assets/design/22-settings-memory.png) |
| Connectors and MCP servers | Connect systems, see scopes, enable or disable individual tools; remote tools write-by-default and approval-gated; organization policy can lock third-party servers | ![Connectors and MCP](../assets/design/23-settings-connectors-mcp.png) |

What exists today for these: memory (with recall, edit and erase APIs for customers; staff and team memory are E5.5), connectors from files (no screens), MCP is not built (E4), scheduled tasks exist only for knowledge re-crawls (E8 is the automation work), artifacts and projects do not exist (E6, E5). The earlier three-column and session-style Workspace mockups (09, 15) remain as variants for the Threads page.

## 0a. New interfaces, round 2 (2026-11-09)
Added after the feature research (`00-reference/NorthCX_Feature-Research-2026-11.md`, sections 7 to 10). Each is a candidate, not a commitment; most need new backend work. All sample data.

**Workspace**
| Screen | What it adds | Mockup |
|---|---|---|
| Home | Landing view: what needs you, what is ready, recent work, suggestions, a prompt with assistant, project and sources chosen up front | ![Home](../assets/design/25-workspace-home.png) |
| Artifacts library | Everything produced: filter by type, project and owner; versions; share, schedule, export | ![Artifacts](../assets/design/24-workspace-artifacts.png) |

**Admin (Settings and admin, Organization group; the grouped navigation now lists Overview, Agents, Knowledge, Channels, Insights, Review and QA, Simulations, Models and budgets, People and groups, Policies, Access keys, Audit and activity, Trust and reliability, Connectors, Data residency, Billing and plan)**
| Screen | What it adds | Mockup |
|---|---|---|
| Insights: Explorer | Ask a question in plain language; finding with figures, masked samples, recommendations that lead straight to an action (draft an article, review a limit, create a scenario), follow-ups; audited | ![Explorer](../assets/design/26-admin-insights-explorer.png) |
| Knowledge: suggested articles | Drafts written from how people resolved similar cases, each claim linked to its source, checks before publishing, nothing live until approved | ![Suggested articles](../assets/design/27-admin-expert-answers.png) |
| Improve an agent | A session that investigates a problem, proposes a spec change as a diff, tests it (required scenarios, new scenarios, replay of past conversations) and sends it to a reviewer; nothing goes live from it | ![Improve agent](../assets/design/28-admin-improve-agent.png) |
| Channels | All six channels in one table with address, agent, volume, hand-off rate and health; same rules on every channel; test a channel | ![Channels](../assets/design/29-admin-channels.png) |
| Trust and reliability | Guardrail blocks, supervisor interventions, a scheduled adversarial suite with trend, protections in place, and a list of what has **not** been done (penetration test, live-model pass, certifications) | ![Trust](../assets/design/30-admin-trust.png) |
| Privacy and data (personal) | What is kept and for how long, export and erase, where your text goes | ![Privacy](../assets/design/31-settings-privacy.png) |

Backend reality: Explorer's masked drill-down and suggested articles are not built (and the drill-down is a privacy decision); the improvement session reuses drafting, scenarios and replay that exist but lacks the loop; channels data exists; the adversarial suite, trend and trust page are new; the artifact library, home and projects need E5/E6.

## 1. Who uses what

![Surfaces and navigation](../assets/design/11-information-architecture.png)

One sign-in and one design system. **Admin platform** (today's Studio, extended) is for administrators, release managers, developers, reviewers and auditors. The **staff workspace** is a separate app for support staff and team leads, because its audience, speed needs and permissions differ. Developer portal, ops console and back office come later and are only drawn here as boxes.

## 1a. Together or separate: what other platforms do
Per the project rule, other companies' products are named only in `00-reference/NorthCX_Feature-Research-2026-11.md` (sections 7 to 9, with sources). Evidence is thin (product pages and third-party write-ups, no interface captures), so this is a pattern, not a measurement.

The pattern across employee AI workspaces, customer-service agent platforms, enterprise chat products and coding-agent workbenches: **people who do the work and people who govern the system get different surfaces**, tied together by one identity and a shared look. One customer-service helpdesk keeps both in a single app because its staff are the same people who configure the agent; the rest separate them. Working surfaces share one layout: threads on the left with status, the conversation in the middle, the work product on the right, several threads open at once. Administration is separate, off by default for risky capabilities, switched on per scope, and inherited from a higher level that lower levels cannot override. Two ideas carry into the design: parallel threads with visible status in the workspace queue, and every admin setting showing where it comes from and whether it is locked from above.

**Recommendation for NorthCX:** separate windows (separate addresses and navigation) with one sign-in, one design system and deep links between them. The staff workspace is its own app because its audience works all day in one queue, needs speed and a narrow permission set, and should never show configuration. The admin platform (Studio, extended) holds operate, build, govern and platform items for the people who configure and oversee agents. Small cross-links keep them feeling like one product: "Open in workspace" from a hand-off, "Open in admin" from an agent. A person with both roles gets an app switcher in the top bar.

### How the two windows look together
![Two windows](../assets/design/14-two-windows.png)
Two browser windows at different addresses, one sign-in. The app switcher (shown open in the Admin window) appears only for people who hold roles for both. Links jump across: a hand-off row in Admin opens the conversation in Workspace; an agent name in Workspace opens that agent in Admin.

## 2. Navigation (admin platform)

Four groups replace today's flat list of 14 items. Items a role cannot use are hidden, not greyed out.

| Group | Items | Today in Studio |
|---|---|---|
| **Operate** | Overview, Conversations, Handoffs, Approvals, Review and QA | All exist as separate pages; Overview is four counters |
| **Build** | Agents (catalog), Knowledge, Simulations, Models and budgets | Agents, Knowledge, Simulations exist; Models and budgets is new |
| **Govern** | People and groups, Access keys, Policies, Audit and activity | Keys and audit exist on one page; the rest are new |
| **Platform** | Connectors and MCP, Usage and cost, Data residency, Settings | Residency and Settings exist; the rest are new |

Top bar on every page: global search (Ctrl K), tenant switcher (appears once multi-tenancy exists; hidden for single-company installs), environment switcher, alerts, account menu.

## 3. Screens

### Overview: what needs attention
![Overview](../assets/design/01-admin-overview.png)
Answers "what do I do first": alerts, approvals waiting, budget warnings, expiring keys, sync problems, each with one button. Health per agent, channel mix, spend by team, recent changes. Uses existing insights, alerts, approvals and audit data; spend by team needs E1.6 and WP3.6.

### Agent catalog and governance
![Agent catalog](../assets/design/02-agent-catalog.png)
![Agent governance](../assets/design/03-agent-governance.png)
The catalog adds owner, purpose, team, model, release state, tool count (and how many write), cost and health. The governance tab shows what the agent may do (each tool's effect, scope and approval rule), its guardrails, limits and budget, who can change or release it, and the release gate. Tools, guardrails and gates exist in the backend; owner, purpose and team are new spec fields; per-agent budget and group access depend on WP1.6 and WP3.2.

### People and groups
![People and groups](../assets/design/04-people-groups.png)
Provisioned from the identity provider (SCIM); roles come from group bindings, effective permissions are the union. Deactivation ends sessions and revokes keys in one step. Backend is WP3.2 and WP3.3; nothing exists today beyond SSO group-to-role mapping.

### Access keys (scoped)
![Access keys](../assets/design/05-access-keys.png)
Keys limited to named agents and environments, with expiry and last-used. A drawer holds the create form so the list stays in view. Keys exist today; scoping is WP3.1.

### Models and budgets
![Models and budgets](../assets/design/06-models-budgets.png)
Providers with capabilities and operator-set prices, budgets per team and per conversation in currency, fallback order, and a refusal for a model that cannot call tools. Backend is E1 (WP1.3 to WP1.6).

### Audit and activity
![Audit and activity](../assets/design/07-audit-activity.png)
Staff actions and agent actions in one searchable record, with the approval reference on agent actions and the integrity status of the hash chain. The audit log exists; agent-action records are a new, medium-sized addition.

### Connectors and MCP
![Connectors and MCP](../assets/design/08-connectors-mcp.png)
Every external system an agent can use, with allowed hosts, tools (and which write), who uses it, health, a test button and the events-webhook test (built in WP0.8). Connectors exist as files today; the screen and MCP are new (E4).

### Review and QA
![Review and QA](../assets/design/10-review-qa.png)
A queue built from hand-offs, low ratings, guardrail blocks, outliers and random samples, scorecards, reviewer calibration and sampling rules; a failed review can become a regression scenario. Review and the judge exist; scorecards, calibration, sampling and assignment are E7.

### Policies (where each setting comes from)
![Policies](../assets/design/13-policies.png)
Each setting shows its value, which level set it (platform, tenant, team, agent), whether it is locked from above and what it applies to. A lower level may be stricter, never looser. Backend: the existing settings are environment variables today; per-tenant and per-team settings come with E2 (WP2.5).

### Staff workspace, session-style variant
![Session-style workspace](../assets/design/15-workspace-session-style.png)
An alternative arrangement of the same window, taking the session-list idea from coding-agent workbenches: a thread list grouped by who needs to act (needs me, agent is handling, resolved today) with status and team filters; a title bar with buttons that open Conversation, Customer, Knowledge, Trace and a side chat; a details column (where it is, what the agent did, what is running, context use); and under the reply box a row with queue, **reply mode** (draft only, review before send, send), copilot and budget. Reply mode is the staff counterpart of the approval modes agents already have. This is a layout idea, not a copy of any product.

### Staff workspace
![Staff workspace](../assets/design/09-staff-workspace.png)
Three columns: queue, open conversations as tabs with their status, conversation with inline approval and an editable draft reply, and a side panel with a summary, knowledge suggestions and the customer's context. Backend is E5; hand-offs, approvals and knowledge search exist and are the first things it would use.

## 4. Components
![Components](../assets/design/12-components.png)
Buttons (primary, secondary, destructive), status badges, stat tiles, budget bars, tables with row actions, tabs and filters, form fields, drawers, empty, loading and error states, confirm dialogs, trace timeline. They use the shared design tokens (light and dark). Today `packages/ui` has states, status badge, trace timeline and answer charts; tables, drawers, filters, dialogs, tabs and stat tiles would be added there so every app shares them.

## 4a. Components of the two windows (decided: two separate apps)
Decision of 2026-11-09: the staff **Workspace** and the **Admin** platform are two separate apps with one sign-in and one design system. Today = exists in Studio or `packages/ui`; New = to build.

### Window 1: Workspace (`apps/workspace`, for support staff and team leads)
| Area | Components | Status |
|---|---|---|
| Frame | App header with search, status (available, away), notifications, account menu, app switcher | New |
| Left rail | Queue list (by team, with waiting time and priority), open-thread tabs with status (approval, replying, resolved), saved searches, drafts, team playbooks | New |
| Conversation | Message timeline (customer, agent, staff, system notes), hand-off banner with reason, inline approval card (approve, reject, ask for more), reply composer with draft reply, regenerate, attach, canned answers | Approval and hand-off data exist; the screen is New |
| Right panel | Conversation summary, suggested knowledge sources with the passage used, customer context (plan, orders, identity verified), conversation tags, related past conversations | New |
| Actions | Resolve, return to agent, transfer to queue or person, add note, set tag, flag for review | Hand-off resolve exists in the API |
| Search | One search across knowledge, conversations and hand-offs, with access applied per result | New (SearchProvider, E5) |
| Ask the copilot | Side chat with a staff agent (search, summarise, draft, report) | New (E5) |
| States | Empty queue, loading, error, offline banner, session expired | Partly in `packages/ui` |

### Window 2: Admin (`apps/studio`, extended, for administrators, release managers, developers, reviewers, auditors)
| Group | Pages and their components | Status |
|---|---|---|
| Frame | Grouped navigation, global search (Ctrl K), tenant and environment switchers, alerts bell, account menu, app switcher, role-aware hiding | Flat navigation exists; rest New |
| Operate | **Overview** (needs-attention list, stat tiles, agent health, channel mix, spend by team, recent changes); **Conversations** (search, filters, transcript, trace timeline); **Handoffs** (queue, detail, resolve); **Approvals** (list, decision, expiry); **Review and QA** (queue, scorecard form, calibration, sampling rules, create scenario from review) | Conversations, hand-offs, approvals, review exist as pages; Overview v2, scorecards, calibration, sampling New |
| Build | **Agents** (catalog table, spec editor, builder, versions and releases, rollout panel, governance tab); **Knowledge** (sources, documents, import, crawl and schedules, search test, indexing status); **Simulations** (scenarios, runs, scenario editor, gate status); **Models and budgets** (providers, prices, capabilities, budgets, fallback order, routing) | Agents, knowledge, simulations exist; catalog fields, governance tab, models and budgets New |
| Govern | **People and groups** (people, groups, role bindings, provisioning status); **Access keys** (list, scoped-key drawer, expiry, last used, revoke); **Policies** (setting table with source, lock and applies-to, change history); **Audit and activity** (filters, staff and agent actions, approval reference, integrity status, export) | Keys and audit exist on one page; the rest New |
| Platform | **Connectors and MCP** (connectors, MCP servers, webhooks, test buttons, health); **Usage and cost** (by agent, team, model, period; export); **Data residency** (destination report, policy); **Settings** (single sign-on, SCIM, session policy, alerts, retention, branding) | Residency, SSO, settings, alerts exist; connectors UI, usage and cost, SCIM New |

### Shared by both windows (`packages/ui` and `packages/api-client`)
| Kind | Components | Status |
|---|---|---|
| Layout | App frame, page header with actions, tabs, two-column and three-column layouts, drawer, modal, confirm dialog | New (frame, tabs, drawer, dialog) |
| Data | Data table (sort, filter, row actions, bulk select, pagination), stat tile, budget bar, ratio display, timeline, trace timeline, answer charts | Trace timeline and answer charts exist |
| Inputs | Text, select, multi-select chips, date range, toggle, key-value editor, search box with filters | New |
| Feedback | Status badge, toast, inline error, empty state, loading skeleton, error box with retry | Status badge, states exist |
| Policy | Setting row with source and lock, inherited-value indicator | New |
| Identity | Sign-in (SSO), session expiry, role gate, tenant switcher, app switcher | Role gate (`useMe`) exists |
| Foundations | Design tokens (light and dark), focus ring, spacing and type scale, icons | Tokens exist (WP0.2) |

## 5. Rules for every screen
Hide what the role cannot do; confirm before anything destructive and record it in the audit log; show an empty, loading and error state; keyboard and screen-reader support (labelled controls, visible focus, no colour-only status); no layout depends on hover; works at tablet width; every number says what it counts and over what period (the provisional resolution rate says so on the tile).

## 6. How I would build it
Vertical slices, each ending with backend, screens, tests and refreshed screenshots, in this order:

| Slice | Contents | Depends on |
|---|---|---|
| A | New shell (grouped navigation, top bar, global search, environment switcher), component library in `packages/ui`, Overview v2 | nothing new |
| B | Agent catalog and governance view, owner/purpose/team fields | small spec change |
| C | Scoped keys (WP3.1) and the audit and activity view with agent actions | WP3.1 |
| D | People, groups and role bindings (WP3.2), then SCIM (WP3.3) | WP3.1 |
| E | Models and budgets screens | E1 (WP1.3 to 1.6) |
| F | Connectors and MCP screens | E4 |
| G | Review and QA: scorecards, calibration, sampling | E7 |
| H | Staff workspace app (`apps/workspace`) | E5 and tenancy decisions |

## 7. Decisions needed
1. ~~One app or two for admin?~~ **Decided 2026-11-09: two separate apps, Workspace and Admin** (see 4a). Earlier question: The plan (decision #140) said Studio first, then separate admin, ops and back-office apps. I drew the admin platform as Studio extended, because the audience and sign-in are the same until multi-tenancy; splitting `apps/admin` out later is cheap because the shared parts are packages. Recommended: extend Studio now.
2. **Naming** of the staff product (open decision D2).
3. **Start with slice A**, or reorder?
4. Whether the mockups should also exist as a Figma file. The Figma connection was not available in this session, so these are HTML and PNG only.
