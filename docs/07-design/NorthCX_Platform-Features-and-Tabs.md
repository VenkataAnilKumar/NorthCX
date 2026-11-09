# NorthCX platform: features, tabs and screens

Status: **working specification, 2026-11-09.** One place that gathers what was designed in this phase: the two web apps, every tab with its purpose and features, the Pilot window, Profile, the Admin side, and the features that cut across them. It states what exists today and what is only proposed. Details and mockups are in the documents listed at the end. All mockups use invented sample data.

**Status words.** *Decided*: the owner confirmed it. *Proposed*: my recommendation, not yet confirmed. *Built*: working in the repository. *Needs backend*: the screen can be drawn, but the data or actions do not exist yet (the work package is named).

## 1. The platform at a glance
| Surface | For | State |
|---|---|---|
| **Workspace** (web app) | Support staff and team leads: work conversations, decide approvals, work with assistants, keep outputs | Decided as a separate app; a first slice is built (see section 9) |
| **Settings and admin** (web app, today's Studio extended) | Administrators, release managers, developers, reviewers, auditors, and everyone for personal settings | Decided as a separate app; extended with a new shell, Overview, Agent Hub, Preferences and Profile |
| Customer channels | Customers: web chat widget, email, SMS, WhatsApp, Telegram, voice | Built |
| Developer portal, ops console, back office, marketing site, Trust and Legal centers | Developers, operators, the vendor, prospects, customers | Planned later (Gap Closure Plan, section 10) |

The two apps have separate addresses, one sign-in and one design system. A person with roles in both gets an app switcher; links jump between them (for example from a hand-off in Admin to the conversation in Workspace). **Look and feel:** "glass", meaning translucent surfaces over a soft gradient in light and dark, with solid surfaces when the system or the person asks for less transparency, and high-contrast and reduced-motion options.

## 2. Workspace: tabs and features (final names, decided 2026-11-09)
Home is the landing page; Settings is in the corner. Twelve tabs in four groups.

### Work
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Inbox** | Customer conversations that need a person | Needs me / agent is handling / resolved; read the transcript and the agent's summary; suggested reply; resolve with a note; several conversations open at once; masked customer data | Built in a first form (hand-offs); decided name |
| **Approvals** | Decide what agents asked a person to approve | Count badge; approve or reject with a note; customer context and why it needs you; decided and expired lists | Built in a first form; proposed tab |
| **Customers** | One view of a person across every channel | Timeline, facts the agents may use, notes, satisfaction | Needs backend (a cross-channel customer record) and an owner decision on who may see customer data; proposed |

### Assist
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Pilot** | Give an assistant a task | The Pilot window (section 3) | Decided name; needs staff backend (E5) |
| **Assistants** | Catalog of predefined staff assistants | Search, favorites, what each can see and do, start a chat, suggest a new one | Decided; needs E5 and Agent Hub entries (today it lists agents for test chats) |
| **Search** | One search across everything you may see | Knowledge, conversations, hand-offs, outputs; the reason you can see each result | Decided; knowledge search built, the rest needs E5 |
| **Library** | Sources, documents, playbooks and canned answers | Browse and search, out-of-date flags, propose edits | Proposed; knowledge store built, playbooks and canned answers new |

### Create
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Outputs** | Everything assistants made for you | Filter by type, space and owner; versions; share to team; schedule; export | Decided; needs E6 |
| **Spaces** | Instructions, sources, files, chats and outputs for one piece of work | Private or team; each space has its own memory; add files and sources | Decided; needs E5 and E6 |
| **Automations** | Multi-step work that runs by itself | Trigger (schedule, webhook, event, manual), steps (get data, assistant, check, person, action), people where needed, limits and kill switch, describe-it draft, canvas and list view, run history with retry from a step; **Recurring** is a filter for scheduled ones | Decided (Workflows and Scheduled merged); needs E8 and E14 |

### Team (leads and reviewers only)
| Tab | Purpose | Features | State |
|---|---|---|---|
| **Quality** | Review and coach | Review queue, scorecards, calibration, sampling rules, coaching notes | Proposed; review queue exists in Admin, the rest is E7 |
| **Performance** | Numbers | Mine and my team's: handled, resolved, approvals, response times | Proposed; organization insights exist in Admin, personal and team views are E15 |

**Panels and controls that are not tabs:** customer panel and suggested knowledge (inside a conversation), notifications (a bell in the top bar), live call assist (a panel while a call is open), availability and workload (a status control in the header), the app switcher and theme switch.

## 3. The Pilot window
**Layout.** Left: the Workspace navigation and recent chats. Centre: the conversation with a composer. Right: a panel with inner tabs. A title bar names the chat, the assistant and the space.

**Inner tabs:** **Plan** (clarifying questions, the plan, estimate of time and cost, approve or edit), **Output** (what is being made, with versions, edit, copy, save to Outputs, share, schedule), **Files** (files in this chat and its space, with their status and which answers used them), **Sources** (everything used, linked, with what each answer relied on), **Context** (instructions, space instructions, memory and personal context in use, each switchable for this chat), **Steps** (a live view of searches and tools, time, tokens, cost, the model and why; pause, redirect, stop; replay later), **Side chat** (a branch for a quick question that adds nothing back).

**Composer.** A **+ menu**: space, files, Library sources, a conversation or customer as masked context, connected systems, skills and playbooks, a pasted link or screenshot. A **task style**: Quick answer, Think, Research (asks questions, shows a plan, can run in the background), Do (uses connected tools; anything that writes asks first). A **model mode**: Auto, Faster and cheaper, Best quality, Private only, with where the text goes shown and unavailable options explained. Slash commands, mentions, voice input, stop, send key from Preferences.

**Answers.** Streaming with progress and numbered citations; show what it used and why this model; copy, regenerate, edit and resend, rate, save to Outputs, turn into an automation; drafted replies open in Inbox with the draft ready and are never sent automatically; unsure answers say so and say when a source disagrees with a remembered preference.

**Chat management.** History search, pin, rename, archive, delete; temporary chat (nothing saved, no memory); branch from any message; share a chat read-only with customer data masked.

State: streaming chat, citations, approvals, traces and knowledge search are built; staff assistants with tools, spaces, masked conversation attach and chat history need E5; the Output tab needs E6; background runs and automations need E8; the model mode needs the hybrid selection work.

## 4. Home, top bar and Settings (Workspace)
**Home:** a greeting, what needs you (approvals, hand-offs), what is ready (digests, finished runs), recent work, suggestions, and a prompt with assistant, space and sources chosen up front. **Top bar:** search, notifications, availability, the app switcher, theme. **Settings:** sign-in and appearance; the full personal settings live in Settings and admin (section 5).

## 5. Settings and admin
A wide settings app opened from the profile menu. Everyone sees the **Personal** group; the **Organization** group appears only for roles that can use it.

### Personal (everyone)
| Page | What it holds | State |
|---|---|---|
| **Profile** (six tabs) | **About you** (name, team, language, time zone, default assistant, signature, roles read-only); **Instructions and persona** (standing instructions, style presets or a custom style from your writing, a table of what applies to a chat, highest wins); **Personal context** (opt-in, per-source consent, daily briefing, suggestions, reminders, preview); **Skills** (reusable ways of doing a task, from you, your team and your organization; instructions only, never new tools or access); **My assistants** (assistants you build, limited to your own access, shared with a reviewer when they can write); **Activity and controls** (what assistants used, retention, temporary chats, export, delete, erase) | Profile shows who you are and your permissions today; the rest is proposed and needs E5 (staff memory E5.5) |
| **Preferences** | Theme (match device, light, dark), accent colour with fixed status colours, density, text size, high contrast, reduce motion, chat defaults, language and date format | Built (saved in this browser) |
| **Memory** | Automatic and "remember this" saving; personal, space and team scopes; where each memory came from and what it applies to; start a chat without memory; review prompts for unused items; instructions always win over memory | Customer-side memory built; staff memory needs E5.5 |
| **Connectors** and **MCP servers** | Systems your assistants use on your behalf; per-tool switches; remote tools write-by-default and approval-gated; organization policy can lock third-party servers | Connectors exist as files; screens and MCP need E4 |
| **Notifications**, **Privacy and data**, **Usage and limits**, **API keys**, **Security and sessions** | Alerts and where; what is kept and for how long, export and erase; own usage; personal keys; sessions and sign-out | Privacy and data drawn; the others not yet drawn |

### Organization (administrators; the list is proposed, not yet confirmed)
| Page | What it holds | State |
|---|---|---|
| **Overview** | What needs attention: alerts, approvals, hand-offs, budgets, expiring keys, agent health, provisional resolution rate | Built (new version) |
| **Agents** | Catalog (owner, purpose, model, release, tools, cost, health) and a governance tab per agent (tools and their effect, guardrails, limits, access, release gate, model policy) | Agents built; catalog fields and governance tab proposed |
| **Agent Hub** | Predefined agents: install flow (details, requirements check, tests, draft), updates, organization-only publishing | Built in a first form (the four templates, install as draft with tests); updates and publishing proposed |
| **Builder** | Assistant that drafts and refines agents; the improvement loop (investigate, propose a diff, run scenarios and a replay, send to a reviewer); proactive suggestions | Proposed; drafting and refining exist as API |
| **Knowledge** | Sources, documents, gaps, suggested articles from resolved hand-offs | Built; suggested articles proposed |
| **Channels** | Six channels with address, agent, volume, hand-off rate, health; same rules everywhere | Data exists; screen proposed |
| **Insights** | Figures and charts; **Explorer**: plain-language questions with masked samples and recommendations | Figures built; Explorer proposed (a privacy decision) |
| **Review and QA** | Queue, scorecards, calibration, sampling rules | Queue built; the rest E7 |
| **Simulations** | Scenarios and runs that gate releases | Built |
| **Models and budgets** | Providers, tiers, capabilities, prices, routing rules, per-agent qualification, budgets, fallback | Providers layer started (WP1.1 to 1.2); the rest proposed (WP1.3 to 1.13) |
| **People and groups** | People, groups, role bindings, provisioning status | Proposed; E3 |
| **Policies** | Rules with where each value comes from (platform, tenant, team, agent) and locks | Proposed; needs E2 for per-tenant values |
| **Access keys** | Keys limited to agents and environments, expiry, last used | Keys built; scoping E3.1 |
| **Audit and activity** | Staff and agent actions, approval reference, chain integrity, export | Audit built; agent-action records proposed |
| **Trust and reliability** | Guardrail blocks, supervisor interventions, adversarial-suite trend, protections in place, and what has not been done | Proposed |
| **Connectors (organization)** | Systems agents can reach: allowed hosts, tools, health, tests | Files today; screen proposed; MCP E4 |
| **Data residency** | Where data may go and whether every destination is compliant | Built |
| **Billing and plan** | Usage, plan, invoices | Proposed; E10 |

## 6. Features that cut across the apps
1. **Hybrid model selection** (local, private cloud, public cloud). Hard data-policy constraints first, then per-agent qualification by required scenarios, then operator-written rules, then cost; fallback never crosses a forbidden tier; every choice recorded in the trace. People choose within limits: administrators set what exists and what is allowed, agent owners pick allowed models, staff pick a mode (Auto, Faster, Best quality, Private only), customers choose nothing. Local models start on read-only single-step work and earn more by passing the agent's own scenarios. *Proposed; WP1.9 to 1.13.*
2. **Personal intelligence in layers.** Instructions, persona and style, memory, skills, spaces and preferences are separate layers. Precedence from highest: organization rules (locked), team instructions, space instructions, your instructions, chat style; memory informs but never overrides; nothing overrides a policy, a source's facts or a customer's data. Everything is opt-in, explainable ("what it used") and erasable; customer messages and personal details are never saved to personal context or memory. *Proposed.*
3. **Agent Hub and predefined agents.** Four exist (order status, returns and refunds, knowledge FAQ, human triage); proposed customer agents: billing and invoices, appointments, account help, delivery problems, plan change and cancellation, complaint handling, front door; proposed staff assistants: care copilot, hand-off triage, QA assistant, report builder, escalation analyst, knowledge curator. Installing never makes an agent live.
4. **Automations** with durable runs, people-in-the-loop steps, limits and a kill switch; **Builder** with an improvement loop; **Explorer** and suggested articles from resolved hand-offs.
5. **Safety and trust.** Write steps always ask first; assistants act with the signed-in person's permissions; customer data is masked wherever it is shown outside the conversation; audit without content; scheduled adversarial tests and a trust page that lists what has not been done (independent penetration test, live-model pass, certifications).
6. **Accessibility and look.** Light, dark and match device; accent colours with fixed status colours; density and text size; high contrast; reduce motion; solid surfaces when transparency is unwanted; keyboard operation and labelled controls.

## 7. Vocabulary
**Agent**: the customer-facing AI. **Assistant**: a staff-facing helper. **Inbox** conversation: a customer conversation that needs a person. **Pilot chat**: a staff member working with an assistant. **Space**: where instructions, sources, files, chats and outputs live together. **Output**: something an assistant made. **Automation**: multi-step work that runs by itself.

## 8. What exists today versus proposed
Built and working: the backend for agents, approvals, hand-offs, simulations and releases, knowledge, six channels, insights with a provisional resolution rate, status events, shared limits and several-process operation, masked-text PDFs, the generated API reference and the provider layer (WP1.1 to 1.2). Built in a first form in the web apps: glass design system, Admin shell with grouped navigation, Overview, Agent Hub, Preferences, Profile; a Workspace app with Home, Inbox (as Threads), Approvals, Chat, Assistants, Search, Knowledge and Settings, and honest "not available yet" pages for tabs without a backend. Everything else in this document is a design.

## 9. Web app build state (2026-11-09)
The glass Admin work and the Workspace app are on the feature branch `claude/awesome-brown-o0nk5s` as work in progress; `main` does not contain them. The Workspace app still uses the old tab names in code. Known: a Workspace Chat crash was fixed in code but not yet re-tested in a browser; the Workspace browser test script has not passed in full. Tabs and features were being decided when the build paused.

## 10. Open decisions (collected)
**Tabs and names:** confirm the Organization page list; whether Customers is allowed (privacy); first-release tab set (recommended: Inbox, Approvals, Pilot, Assistants, Search, Library). **Pilot:** all four task styles or Quick answer and Research first; plan on every task or on request; pause and redirect in the first version; per-space file limits. **Profile:** which personal-context sources first (recommended: hand-offs, approvals, own drafts and outputs, team documents; calendar and email later); read-only personal assistants shareable without a reviewer; default retention for personal chats. **Models:** what marks a conversation sensitive; qualification threshold; where unqualified models may run; whether sensitive data may ever go to the public cloud. **Agent Hub:** organization-only or later a marketplace (depends on open versus commercial, D1); who may install; first customer agents; names. **Builder:** name, first-release scope, proactive suggestions default, chat-tool presence later. **Automations:** who may publish a workflow; whether workflows may call customer-facing agents. **Platform:** open versus commercial (D1); naming of the staff product (D2); the remaining plan decisions D3 to D9.

## 11. Where the work sits in the plan
Wave 1: E1 model providers and cost governance, E3 identity and governance, E4 MCP. Wave 2: E2 multi-tenancy, E5 staff workspace backend, E6 libraries and outputs, E7 QA scoring. Wave 3: E8 automations, E9 connectors, E14 visual editor, E15 workspace analytics. Proposed additions: E22 Agent Hub; WP1.9 to 1.13 hybrid selection. See `08-implementation/NorthCX_Implementation-Plan.md`.

## 12. Related documents and mockups
`07-design/NorthCX_Admin-Platform-Design.md` (the detailed design with screen-by-screen notes and the mockup images in `assets/design/`; sections 0 to 0g), `07-design/NorthCX_Agent-Hub-Design.md`, `04-ai-architecture/NorthCX_Hybrid-Model-Selection.md`, `04-ai-architecture/NorthCX_Model-Providers.md`, `00-reference/NorthCX_Feature-Research-2026-11.md` (market research; the only place other products are named), `09-project/NorthCX_Decision-Log.md` (decisions 139 to 153), `01-product/NorthCX_Product-Overview.md`. Mockup sources: `07-design/mockups/*.html`, regenerated with `python scripts/gen_design_mockups.py` and `node scripts/shoot_mockups.js`.
