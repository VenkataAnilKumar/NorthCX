# NorthCX Product Definition

Status: **Partly built**. Updated: 2026-11-09. Master for: vision, problem, pillars, market and scope. Companion documents: PRD, Personas, Success-Metrics, Feature-Catalog.

## 1. Vision
Every company can offer customers an agent that resolves issues end to end, safely, in any channel, on infrastructure the company controls.

## 2. Problem
- Customer-service automation today mostly deflects. It answers FAQs but cannot act, so customers repeat themselves to a human.
- Agents that can act are risky: wrong refunds, leaked data, invented policy. Teams lack tools to constrain, test and audit them.
- Enterprise-grade agent platforms are closed and gated by large contracts. Open building blocks exist, but every team re-assembles channels, memory, evals, guardrails and observability on its own.
- Changing agent behaviour is slow. Prompt edits ship without regression tests, and nobody can say whether a change made things better.

## 3. Product statement
NorthCX is an open-source platform for building, testing, releasing and running supervised customer-experience agents. Agents act on business systems through typed tools, are checked by supervisors, hand off to people with full context, and are released only after simulations pass.

## 3a. Platform surfaces (design decided 2026-11-09; built only where marked in the Feature Catalog)
The product is one platform with two jobs: customer-facing agents that resolve issues under supervision, and a **Workspace** where the staff who supervise them work, with assistants of their own. It has two web apps (one sign-in, one design system) beside the customer channels:
- **Workspace** for support staff, team leads and reviewers. Six left items: Home, Pilot, Work (Inbox, Approvals, Customers), Assist (Assistants, Search, Library), Create (Outputs, Spaces, Automations) and Team (Quality, Performance; leads and reviewers only). The **Pilot** is where a person gives an assistant a task: it asks clarifying questions, writes a plan for approval, then works in the background, on the company's own data only in the first release.
- **Settings and Admin** (the Studio, extended) for administrators, release managers, developers, reviewers and auditors: Operate, Build, Govern and Platform groups, an **Agent Hub** (a catalog of agents and assistants; installing never makes one live), a **Builder** assistant, and personal settings with **personal intelligence** (instructions, persona, memory, skills; organization rules always outrank personal ones).
- **Hybrid model selection:** local, private and public models chosen by privacy limits, qualification, rules and cost; a fallback never crosses a forbidden tier.
Details: `../07-design/NorthCX_Platform-Features-and-Tabs.md`. Everything in this section except the customer channels and the current Studio is designed, not built.

## 4. Product pillars
| Pillar | Promise | Key features (catalog IDs) |
|---|---|---|
| Act | Resolve, don't deflect | T1-T8, R1-R10 |
| Trust | Every reply and action is checked and auditable | S1-S11, H2-H3, P3 |
| Prove | Ship changes only when tests pass | Q1-Q12 |
| Collaborate | Seamless handoff, human and agent together | H1-H8 |
| Reach | One agent, every channel | C1-C10 |
| Know | Grounded in the company's knowledge and the customer's history | K1-K8 |
| Learn | See what works and what fails | O1-O10 |
| Own | Open, self-hostable, no lock-in | P7, A2, model interface |

## 5. Target market
Mid-size and large companies with meaningful support volume and engineering capacity, plus platform teams inside larger enterprises. Initial focus: e-commerce, subscription and service businesses where most contacts are order, billing and account requests.

## 6. Users
Described in `NorthCX_Personas.md`: CX lead, platform engineer, compliance owner, support agent, reviewer, administrator, and the end customer. The Workspace adds a daily-use surface for the support agent, reviewer and team lead personas (section 3a).

## 7. Scope
### In scope (v1)
Agent authoring in code and Studio, tools and approvals, supervision, handoff, chat and email and messaging, knowledge retrieval, persistent memory, simulations, release management, traces and insights, self-hosting, voice (late v1).
### Out of scope (v1)
General-purpose autonomous agents (browsing, code execution), hosted multi-tenant SaaS, replacing the helpdesk, outcome-based billing, full workforce management.
### After 1.0 (decided 2026-11-08)
Multi-tenancy and the staff workspace move into scope after 1.0 (not in 1.0); the Workspace, Pilot, Agent Hub, Builder, Automations, personal intelligence and hybrid model selection are designed (2026-11-09) and planned for after 1.0. Web search for assistants is later and off by default; Customers view is second release. Outcome-based billing stays out of scope until the open-versus-commercial decision (D1). Agents remain supervised and permission-bound; general-purpose autonomous agents and replacing the helpdesk stay non-goals.

## 8. Principles
1. Safe by default: fail closed when unsure.
2. Actions are explicit: typed tools, approval rules, audit trail.
3. Everything is testable: no agent change reaches customers without passing checks.
4. Humans stay in the loop: handoff is a first-class path, not a failure.
5. Open and replaceable: every external dependency sits behind an interface.
6. Model-agnostic, Claude-first.
7. Honest about uncertainty: unknown means ask or escalate.

## 9. Assumptions to validate
| Assumption | How to validate |
|---|---|
| Teams will define agents in code | Pilot with 2-3 engineering-led teams |
| CX teams need Studio to own tuning | Interviews, Studio prototype tests |
| Approvals and handoff matter more than raw autonomy | Pilot feedback on trust |
| 60% resolution on common intents is reachable | Pilot measurement |
| Self-hosting is a buying criterion | Customer discovery |

## 10. Dependencies and constraints
Model provider availability and terms; customer-system APIs for actions; data-protection rules; telephony and messaging provider terms; open-source licence compatibility.

## 11. Open decisions
Studio adopt-or-build; runtime language confirmation; initial vertical focus.
