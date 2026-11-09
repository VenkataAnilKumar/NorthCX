# NorthCX platform: features, tabs and screens

Status: **Designed**. Updated: 2026-11-09. Master for: Workspace and Admin tabs, names and features (master for the staff platform design). One place that gathers what was designed in this phase: the two web apps, every tab with its purpose and features, the Pilot window, Profile, the Admin side, and the features that cut across them. It states what exists today and what is only designed. Details and mockups are in the documents listed at the end. All mockups use invented sample data.

**Status words.** *Decided*: the owner confirmed it. *Designed*: decided by the owner, not built. *Proposed*: a recommendation the owner has not confirmed (few remain; section 10). *Built*: working in the repository on `main`. *In progress*: early code exists (merged to `main` on 2026-11-09 as unfinished work, still using the earlier tab names) and is only partly tested. *Needs backend*: the screen can be drawn, but the data or actions do not exist yet (the work package is named).

## 1. The platform at a glance
| Surface | For | State |
|---|---|---|
| **Workspace** (web app) | Support staff and team leads: work conversations, decide approvals, work with assistants, keep outputs | Decided as a separate app; a first slice is in progress on `main`, unfinished (see section 9) |
| **Settings and admin** (web app, today's Studio extended) | Administrators, release managers, developers, reviewers, auditors, and everyone for personal settings | Decided as a separate app; a new shell, Overview, Agent Hub, Preferences and Profile are in progress on `main`, unfinished (the 1.0 Studio had a flat navigation) |
| Customer channels | Customers: web chat widget, email, SMS, WhatsApp, Telegram, voice | Built |
| Developer portal, ops console, back office, marketing site, Trust and Legal centers | Developers, operators, the vendor, prospects, customers | Planned later (Gap Closure Plan, section 10) |

The two apps have separate addresses, one sign-in and one design system. A person with roles in both gets an app switcher; links jump between them (for example from a hand-off in Admin to the conversation in Workspace). **Look and feel:** "glass", meaning translucent surfaces over a soft gradient in light and dark, one accent colour, a floating rail with six items (expanded, collapsed to icons, or hidden in full window mode), with solid surfaces when the system or the person asks for less transparency, and high-contrast and reduced-motion options. The full design, mockups and tab icons are in `NorthCX_UI-UX-Design-Proposal.md` (approved 2026-11-09).

## 2. Workspace: tabs and features (final names, decided 2026-11-09)
Home is the landing page; Settings is in the corner. Twelve tabs: Pilot as its own left item and eleven tabs in four groups (Work 3, Assist 3, Create 3, Team 2), shown as six left items with sub-tabs (see below). The tables below list Pilot under Assist for reading only. The owner approved these names on 2026-11-09. Approvals, Customers, Library, Quality and Performance were confirmed as tabs on 2026-11-09 (decision 162); the six tabs the owner decided earlier are Pilot, Assistants, Search, Outputs, Spaces and Inbox, with Automations replacing Workflows and Scheduled.

### How the tabs are shown (decided 2026-11-09): sub-tabs instead of a long list
The left side shows only **six items**, not twelve tabs. Pilot is its own item because people open it most; the other groups open their own **sub-tabs** across the top of the page. The twelve tabs and their names do not change; only where they are shown changes.

| Left item | Sub-tabs |
|---|---|
| **Home** | none (the landing page) |
| **Pilot** | none; opens full width with its own inner tabs (section 3) |
| **Work** | Inbox, Approvals, Customers |
| **Assist** | Assistants, Search, Library |
| **Create** | Outputs, Spaces, Automations |
| **Team** (leads and reviewers only; hidden for everyone else) | Quality, Performance |

Settings and the profile stay in the corner. Rules: a count badge on a sub-tab (for example Approvals) also shows on its group item, so nothing waiting is hidden; the group remembers the last sub-tab you used; a group with one visible sub-tab shows no sub-tab row; search and the command bar (Ctrl K, jump to any tab by typing its name) reach every tab in one step. The Admin app uses the same idea with six left items: Overview, Operate, Build, Govern, Platform and Personal (decision 168). Mockups, one per left item: Home `55-workspace-home.png`, Pilot `50-pilot-research-plan.png`, Work `53-workspace-subtabs.png`, Assist `54-workspace-subtabs-assist.png`, Create `56-workspace-create.png`, Team `57-workspace-team.png`. Every Workspace mockup now uses the six-item sidebar. Customers (second release): `58-workspace-customers.png`; Performance: `60-workspace-performance.png`.

### Work
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Inbox** | Customer conversations that need a person | Needs me / agent is handling / resolved; read the transcript and the agent's summary; suggested reply; resolve with a note; several conversations open at once; masked customer data | In progress in a first form on `main`, unfinished (open and resolved hand-offs, transcript, suggested reply, resolve); the grouping into needs me, agent is handling and resolved and the multi-conversation tabs are designed only; decided name |
| **Approvals** | Decide what agents asked a person to approve | Count badge; approve or reject with a note; customer context and why it needs you; decided and expired lists | In progress in a first form on `main`, unfinished (pending, approved, rejected and expired lists with approve and reject); confirmed tab (decision 162) |
| **Customers** | One view of a person across every channel | Timeline, facts the agents may use, staff notes, satisfaction; search only by customer reference or order number; personal data masked, revealing a field needs a logged reason; each fact shows who added it and when, and a customer can ask for one to be removed | Designed for the second release (decision 158): leads and reviewers first, an administrator can widen it or switch it off; every open, reveal and edit is audited; deletion requests remove the record. Needs backend (a cross-channel customer record) |

### Assist
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Pilot** | Give an assistant a task | The Pilot window (section 3) | Decided name; needs staff backend (E5). A test chat with the customer-facing agents is in progress on `main`, unfinished as a stopgap |
| **Assistants** | Catalog of predefined staff assistants | Search, favorites, what each can see and do, start a chat, suggest a new one | Decided; needs E5 and Agent Hub entries (today it lists agents for test chats) |
| **Search** | One search across everything you may see | Knowledge, conversations, hand-offs, outputs; the reason you can see each result | Decided; knowledge search built, the rest needs E5 |
| **Library** | Sources, documents, playbooks and canned answers | Browse and search, out-of-date flags, propose edits | Designed; knowledge store built, playbooks and canned answers new |

### Create
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Outputs** | Everything assistants made for you | Filter by type, space and owner; versions; share to team; schedule; export | Decided; needs E6 |
| **Spaces** | Instructions, sources, files, chats and outputs for one piece of work | Private or team; each space has its own memory; add files and sources | Decided; needs E5 and E6 |
| **Automations** | Multi-step work that runs by itself | Trigger (schedule, webhook, event, manual), steps (get data, assistant, check, person, action), people where needed, limits and kill switch, describe-it draft, canvas and list view, run history with retry from a step; **Recurring** is a filter for scheduled ones | Decided (Workflows and Scheduled merged); needs E8 and E14 |

### Team (leads and reviewers only)
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Quality** | Review and coach | Review queue, scorecards, calibration, sampling rules, coaching notes | Designed; review queue exists in Admin, the rest is E7 |
| **Performance** | Numbers | Mine and my team's: handled, resolved, approvals, response times | Designed; organization analytics exist in Admin (Insights in the 1.0 Studio), personal and team views are E15 |

**Panels and controls that are not tabs:** customer panel and suggested knowledge (inside a conversation), notifications (a bell in the top bar), live call assist (a panel while a call is open), availability and workload (a status control in the header), the app switcher and theme switch.

### Same name, two jobs: the Workspace page and the Admin page
Some names appear in both apps on purpose. The Workspace page is where staff **do the work**; the Admin page is where administrators **set the rules, see everything and stop things**. A staff member who is not an administrator never sees the Admin page.
| Name | In the Workspace (staff use it) | In Admin (administrators manage it) |
|---|---|---|
| **Library** (Admin) and **Library** (Workspace) | Browse and search sources, documents, playbooks and canned answers; out-of-date flags; propose an edit that goes to a reviewer and never changes a live source by itself | Manage the sources: add documents and files, website crawls and schedules, indexing and freshness, gaps, and approval of suggested articles drawn from resolved hand-offs |
| **Automations** | Build and run your own and your team's routines: trigger, steps, your own run history | Every automation in the organization: owner, trigger, runs, cost and limits; publish review; failures and alerts; the kill switch for one automation or all |
| **Inbox** (Workspace) and **Hand-offs** (Admin) | Work the conversations that need a person: read, reply, resolve with a note | Watch the same queue: size, waiting time, who is handling what; no replying from here |
| **Approvals** | Decide the approvals addressed to you, with the exact action and customer context | Watch every approval and its age, set the approval rules, see who decided |
| **Quality** (Workspace) and **Review and QA** (Admin) | Leads and reviewers review sampled conversations, score them and attach coaching notes | Set the scorecards, sampling rules and calibration; see the review queue for the whole organization |
| **Performance** (Workspace) and **Analytics** (Admin) | Your own and your team's figures | Organization-wide figures by agent, channel and team; plain-language questions (Explorer) |
| **Assistants** (Workspace) and **Agent Hub** (Admin) | Browse the assistants made available to you and start a chat | Install, update, publish, retire and decide who may use each one and what it may see |
| **Connectors** (Personal) and **Systems** (Platform) | Systems your own assistants use on your behalf, with per-tool switches | The outside systems agents can reach: allowed hosts, tools, health, tests, outbound events |
Rule of thumb: if the question is "what do I do with this?" it belongs in the Workspace; if it is "who may, how much, and how do I stop it?" it belongs in Admin.

## 3. The Pilot window
**Layout.** Left: the Workspace navigation and recent chats. Centre: the conversation with a composer. Right: a panel with inner tabs. A title bar names the chat, the assistant and the space.

**Inner tabs:** **Plan** (clarifying questions, the plan, estimate of time and cost, approve or edit), **Result** (what is being made, with versions, edit, copy, save to Outputs, share, schedule), **Files** (files in this chat and its space, with their status and which answers used them), **Sources** (everything used, linked, with what each answer relied on), **Context** (instructions, space instructions, memory and personal context in use, each switchable for this chat), **Steps** (a live view of searches and tools, time, tokens, cost, the model and why; pause and stop, and redirect in the second version (decision 163); replay later), **Side chat** (a branch for a quick question that adds nothing back).

**Composer.** A **+ menu**: space, files, Library sources, a conversation or customer as masked context, connected systems, skills and playbooks, a pasted link or screenshot. A **task style**: Quick answer, Think, Research (asks questions, shows a plan, can run in the background), Do (uses connected tools; anything that writes asks first). The first release has Quick answer and Research (decision 163). A **model mode**: Auto, Faster and cheaper, Best quality, Private only, with where the text goes shown and unavailable options explained. Slash commands, mentions, voice input, stop, send key from Preferences.

**Answers.** Streaming with progress and numbered citations; show what it used and why this model; copy, regenerate, edit and resend, rate, save to Outputs, turn into an automation; drafted replies open in Inbox with the draft ready and are never sent automatically; unsure answers say so and say when a source disagrees with a remembered preference.

**Research and web access (decided 2026-11-09, decision 159).** The Research task style works on the company's own sources only (conversations, Library, outputs, files) and keeps customer data on the private or local model. Web search is not in the first release. Later it is an administrator-enabled tool: off by default, switched on per assistant, never used in a conversation flagged sensitive or with customer data in the query, results labelled as web sources with their address and never treated as company policy, page content treated as data and never as instructions, every search audited, and blocked entirely on private deployments with no outside network. The Pilot labels the two clearly: Research (your data) and Research the web (public).

**Chat management.** History search, pin, rename, archive, delete; temporary chat (nothing saved, no memory); branch from any message; share a chat read-only with customer data masked.

State: streaming chat, citations, approvals, traces and knowledge search are built; staff assistants with tools, spaces, masked conversation attach and chat history need E5; the Result tab needs E6; background runs and automations need E8; the model mode needs the hybrid selection work.

## 4. Home, top bar and Settings (Workspace)
**Home:** a greeting, what needs you (approvals, hand-offs), what is ready (digests, finished runs), recent work, suggestions, and a prompt with assistant, space and sources chosen up front. **Top bar:** search, notifications, availability, the app switcher, theme. **Settings:** sign-in and appearance; the full personal settings live in Settings and admin (section 5).

## 5. Settings and admin
A wide settings app opened from the profile menu. Everyone sees the **Personal** group; the **Organization** group appears only for roles that can use it.

### How the Admin app shows its pages (decided 2026-11-09, decision 168): sub-tabs instead of 35 links
The same idea as the Workspace. The left side shows six items and each opens its pages as sub-tabs across the top:
| Left item | Sub-tabs |
|---|---|
| **Overview** | none (the landing page; was the first Operate page) |
| **Operate** (badge: items waiting) | Conversations, Hand-offs, Approvals, Review and QA, Monitoring, Analytics |
| **Build** | Agents, Agent Hub, Builder, Library, Automations, Simulations, Models and budgets, Test console |
| **Govern** | People and groups, Access keys, Policies, Audit and activity, Trust and reliability, Data residency |
| **Platform** | Channels, Systems, Usage and billing, Organization settings |
| **Personal** (everyone) | Profile, Preferences, Memory, Connectors, MCP servers, Notifications, Privacy and data, Usage and limits, API keys, Security and sessions |
The 25 organization pages and 10 personal pages are unchanged. Personal is for everyone; the organization items appear only for roles that can use them, so a person with no organization role sees only Personal. Rules as in the Workspace: a badge on a sub-tab also shows on its group; the app remembers the last sub-tab per group; Ctrl K reaches any page by name; a sub-tab row that does not fit scrolls sideways. Mockups: `docs/assets/design/01-admin-overview.png`, `35-admin-agent-hub.png`, `21-settings-profile.png`, `59-admin-automations.png` (all workflows, owners, cost and the kill switch). Workspace Performance: `60-workspace-performance.png`.

### Personal (everyone)
| Page | What it holds | State |
|---|---|---|
| **Profile** (six tabs) | **About you** (name, team, language, time zone, default assistant, signature, roles read-only); **Instructions and persona** (standing instructions, style presets or a custom style from your writing, a table of what applies to a chat, highest wins); **Personal context** (opt-in, per-source consent, daily briefing, suggestions, reminders, preview); **Skills** (reusable ways of doing a task, from you, your team and your organization; instructions only, never new tools or access); **My assistants** (assistants you build, limited to your own access, shared with a reviewer when they can write); **Activity and controls** (what assistants used, retention, temporary chats, export, delete, erase) | Profile shows who you are and your permissions today (early code on `main`); the rest is designed (decision 166) and needs E5 (staff memory E5.5) |
| **Preferences** | Theme (match device, light, dark), accent colour with fixed status colours, density, text size, high contrast, reduce motion, chat defaults, language and date format | In progress on `main`, unfinished (saved in this browser) |
| **Memory** | Automatic and "remember this" saving; personal, space and team scopes; where each memory came from and what it applies to; start a chat without memory; review prompts for unused items; instructions always win over memory | Customer-side memory built; staff memory needs E5.5 |
| **Connectors** and **MCP servers** | Systems your assistants use on your behalf; per-tool switches; remote tools write-by-default and approval-gated; organization policy can lock third-party servers | Connectors exist as files; screens and MCP need E4 |
| **Notifications**, **Privacy and data**, **Usage and limits**, **API keys**, **Security and sessions** | Alerts and where; what is kept and for how long, export and erase; own usage; personal keys; sessions and sign-out | Privacy and data drawn; the others not yet drawn |

### Organization (administrators and the roles that can use each page; the list is confirmed, 2026-11-09)
Twenty-five pages, confirmed by the owner on 2026-11-09 (decision 167): Overview as its own left item, then Operate 6, Build 8, Govern 6 and Platform 4 (decision 168). The tables below list Overview under Operate for reading only.

**Operate**
| Page | What it holds | State |
|---|---|---|
| **Overview** | What needs attention: alerts, approvals, hand-offs, budgets, expiring keys, agent health, provisional resolution rate | In progress on `main`, unfinished (a new version; the 1.0 Studio showed five counters) |
| **Conversations** | Every conversation with its trace | Built (Studio) |
| **Hand-offs** | The queue of conversations waiting for a person | Built (Studio) |
| **Approvals** | Actions waiting for a decision | Built (Studio) |
| **Review and QA** | Queue, scorecards, calibration, sampling rules | Queue built; the rest is E7 |
| **Monitoring** | Alerts and what is firing | Built (Studio) |
| **Analytics** | Figures and charts; **Explorer**: plain-language questions with recommendations; figures only at first, masked samples later for leads and reviewers (decision 176) | Figures built (called Insights in the 1.0 Studio); Explorer: figures only at first, masked samples later (decision 176) |

**Build**
| Page | What it holds | State |
|---|---|---|
| **Agents** | Catalog (owner, purpose, model, release, tools, cost, health), editor, versions, releases and a governance tab per agent (tools and their effect, guardrails, limits, access, release gate, model policy) | Agents, editor, versions and releases built; catalog fields and governance tab designed |
| **Agent Hub** | Predefined agents: install flow (details, requirements check, tests, draft), updates, organization-only publishing | In progress on `main`, unfinished (lists the four templates and installs one as a draft with its tests); updates and publishing designed |
| **Builder** | Assistant that drafts and refines agents; the improvement loop (investigate, propose a diff, run scenarios and a replay, send to a reviewer); proactive suggestions | Designed; drafting and refining exist as API |
| **Library** | Sources, documents, gaps, suggested articles from resolved hand-offs (the same name as the Workspace tab, where people read and search it) | Built (called Knowledge in the 1.0 Studio); suggested articles designed |
| **Simulations** | Scenarios and runs that gate releases | Built (Studio) |
| **Models and budgets** | Providers, tiers, capabilities, prices, routing rules, per-agent qualification, budgets, fallback | Provider layer started (WP1.1 to 1.2, backend only); the rest designed (WP1.3 to 1.13) |
| **Automations** | Every workflow in the organization: owner, trigger, runs, cost, limits; publish review; the kill switch for one automation or all; failures and alerts | Designed; E8 |
| **Test console** | Try an agent as a customer would | Built (Studio) |

**Govern**
| Page | What it holds | State |
|---|---|---|
| **People and groups** | People, groups, role bindings, provisioning status | Designed; E3 |
| **Access keys** | Keys limited to agents and environments, expiry, last used | Keys built; scoping is E3.1 |
| **Policies** | Rules with where each value comes from (platform, tenant, team, agent) and locks | Designed; needs E2 for per-tenant values |
| **Audit and activity** | Staff and agent actions, approval reference, chain integrity, export | Audit built; agent-action records designed |
| **Trust and reliability** | Guardrail blocks, supervisor interventions, adversarial-suite trend, protections in place, and what has not been done | Designed |
| **Data residency** | Where data may go and whether every destination is compliant | Built (Studio) |

**Platform**
| Page | What it holds | State |
|---|---|---|
| **Channels** | Six channels with address, agent, volume, hand-off rate, health; same rules everywhere | Data exists; screen designed |
| **Systems** | The outside systems agents can reach: allowed hosts, tools, health, tests, and the outbound status events with a test sender (Personal has its own Connectors page for what your assistants use on your behalf) | Defined in files today; screen designed; MCP is E4 |
| **Usage and billing** | Spend by agent, team and model with export; plan and invoices | Designed; E1.6 and E10 |
| **Organization settings** | Sign-in (including single sign-on), retention, alerts | Built (called Settings in the 1.0 Studio) |

## 6. Features that cut across the apps
1. **Hybrid model selection** (local, private cloud, public cloud). Hard data-policy constraints first, then per-agent qualification by required scenarios, then operator-written rules, then cost; fallback never crosses a forbidden tier; every choice recorded in the trace. People choose within limits: administrators set what exists and what is allowed, agent owners pick allowed models, staff pick a mode (Auto, Faster, Best quality, Private only), customers choose nothing. Local models start on read-only single-step work and earn more by passing the agent's own scenarios. *Designed (rules decided in decision 164); WP1.9 to 1.13.*
2. **Personal intelligence in layers.** Instructions, persona and style, memory, skills, spaces and preferences are separate layers. Precedence from highest: organization rules (locked), team instructions, space instructions, your instructions, chat style; memory informs but never overrides; nothing overrides a policy, a source's facts or a customer's data. Everything is opt-in, explainable ("what it used") and erasable; customer messages and personal details are never saved to personal context or memory. *Designed (decision 166).*
3. **Agent Hub and predefined agents.** Four exist (Order status, Returns and refunds, Help-centre answers, Triage and hand-off); planned customer agents: billing and invoices, appointments, account help, delivery problems, plan change and cancellation, complaint handling, front door (the first three are billing, delivery problems and account help, decision 165); planned staff assistants: care copilot, hand-off triage, QA assistant, report builder, escalation analyst, knowledge curator. Installing never makes an agent live.
4. **Automations** with durable runs, people-in-the-loop steps, limits and a kill switch; **Builder** with an improvement loop; **Explorer** and suggested articles from resolved hand-offs.
5. **Safety and trust.** Write steps always ask first; assistants act with the signed-in person's permissions; customer data is masked wherever it is shown outside the conversation; audit without content; scheduled adversarial tests and a trust page that lists what has not been done (independent penetration test, live-model pass, certifications).
6. **Accessibility and look.** Light, dark and match device; accent colours with fixed status colours; density and text size; high contrast; reduce motion; solid surfaces when transparency is unwanted; keyboard operation and labelled controls.

## 7. Vocabulary
**Agent**: the customer-facing AI. **Assistant**: a staff-facing helper. **Inbox**: the Workspace tab for customer conversations that need a person (called Hand-offs in Admin). **Pilot chat**: a staff member working with an assistant. **Space**: where instructions, sources, files, chats and outputs live together. **Output**: something an assistant made and the person saved (the Outputs tab). **Result**: the Pilot inner tab showing what the current chat is making. **Automation**: multi-step work that runs by itself.

## 8. What exists today versus designed
**Built and working on `main`:** the backend for agents, approvals, hand-offs, simulations and releases, knowledge, six channels, insights with a provisional resolution rate, status events, shared limits and several-process operation, masked-text PDFs, the generated API reference and the provider layer (WP1.1 to 1.2); and the Studio pages from 1.0 (built with a flat navigation; since 2026-11-09 they sit inside the new grouped shell, which is unfinished: Overview of five counters, Conversations, Hand-offs, Approvals, Agents, Knowledge, Simulations, Review, Monitoring, Insights, Access and audit, Data residency, Settings, Test console).

**In progress (early code, merged to `main` on 2026-11-09 as unfinished work):** the glass design system, the Admin shell with grouped navigation, a new Overview, Agent Hub, Preferences and Profile, and a Workspace app with Home, Threads (the Inbox), Approvals, Chat (the Pilot), Assistants, Search, Knowledge (the Library) and Settings, plus "not available yet" pages for tabs without a backend. The code still uses the old tab names.

**Everything else in this document is a design.**

## 9. Web app build state (2026-11-09)
The glass Admin work, the Workspace app and their test scripts were merged to `main` on 2026-11-09 as unfinished work (typecheck, unit tests and builds pass). The Workspace app still uses the old tab names in code. Known: a Workspace Chat crash was fixed in code but not yet re-tested in a browser; the Workspace browser test script has not passed in full. On 2026-11-09 the owner asked to stop building and finalize the documentation first; no further code is being written.

## 10. Decisions (collected; all made except where marked open)
**Tabs and names:** the Organization page list is confirmed (25 pages, decision 167: Automations added to Build, Billing and plan merged into Usage and billing); Approvals, Customers, Library, Quality and Performance are confirmed tabs (decision 162); **naming clashes resolved on 2026-11-09:** Admin uses Library (not Knowledge), Analytics (not Insights; the Workspace keeps Performance for personal and team numbers), Systems (not Connectors for the organization page; Personal keeps Connectors) and Organization settings (not Settings); Admin keeps Hand-offs while the Workspace calls the same queue Inbox, because an administrator watches the queue and a staff member works it; the Pilot inner tab that was called Output is now **Result**, so it no longer sounds like the **Outputs** tab; Customers is decided (second release, leads and reviewers first, decision 158); first-release tab set is decided: Inbox, Approvals, Pilot, Assistants, Search, Library (decision 162; Customers is second release, the rest follow). **Pilot (decided, decision 163):** Quick answer and Research first, Think and Do later; plan for Research and Do only; pause and stop first, redirect second; per-space file limits set by an administrator. **Profile (decided, decision 166):** first sources are own hand-offs, approvals, drafts and outputs and team documents (calendar and email later); read-only personal assistants shareable without a reviewer; default retention for personal chats 90 days (placeholder to validate). **Models (decided, decision 164):** sensitive means customer personal data, an account, payment or health topic, or an agent an administrator marks sensitive; qualification is 100 percent of required safety scenarios and 90 percent of the rest (to validate on a pilot); an unqualified model runs only on read-only single-step work with no customer data; sensitive data goes to the public cloud only when an administrator explicitly allows it for a named agent. **Agent Hub (decided, decision 165):** organization-only for now (a marketplace waits for D1); developers install into Staging and release managers release; first customer agents are billing and invoices, delivery problems and account help; names stay Agent Hub and Assistants. **Builder (decided, decision 165):** name stays Builder; reviewable drafts only in the first release; proactive suggestions off by default; chat-tool presence later. **Automations (decided, decision 165):** a reviewer must approve publishing; workflows may not call customer-facing agents in the first release. **Platform (decision 170):** the staff product's working name is NorthCX Workspace (D2); open versus commercial (D1) is not decided, the leaning is open core with everything built so far staying open, and it must be decided before billing work and the back office; the plan's recommendations for D3 to D9 are accepted and each is locked in when its work package starts.

**Open on purpose:** D1 (open versus commercial), deferred until billing work starts or a sale or hosted service is planned (decision 176); it blocks pricing and any marketplace but nothing before Phase 6. Everything else from this document is decided.

## 11. Where the work sits in the plan
Wave 1: E1 model providers and cost governance, E3 identity and governance, E4 MCP. Wave 2: E2 multi-tenancy, E5 staff workspace backend, E6 libraries and outputs, E16 policy management, E18 support access. Wave 3: E8 automations, E9 connectors, E14 visual editor, E15 workspace analytics, E7 QA scoring. Proposed additions: E22 Agent Hub; WP1.9 to 1.13 hybrid selection. See `08-implementation/NorthCX_Implementation-Plan.md`.

## 12. Related documents and mockups
`07-design/NorthCX_Admin-Platform-Design.md` (the detailed design with screen-by-screen notes and the mockup images in `assets/design/`; the design rounds 0a to 0f are in `99-archive/NorthCX_Admin-Design-History.md`), `07-design/NorthCX_Agent-Hub-Design.md`, `04-ai-architecture/NorthCX_Hybrid-Model-Selection.md`, `04-ai-architecture/NorthCX_Model-Providers.md`, `00-reference/NorthCX_Feature-Research-2026-11.md` (market research; the only place other products are named), `09-project/NorthCX_Decision-Log.md` (decisions 139 to 172), `01-product/NorthCX_Product-Overview.md`. Mockup sources: `07-design/mockups/*.html`, regenerated with `python scripts/gen_design_mockups.py` and `node scripts/shoot_mockups.js`.
