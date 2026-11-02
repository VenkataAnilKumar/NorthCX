# NorthCX Product Definition

Status: Draft. Companion documents: PRD, Personas, Success-Metrics, Feature-Catalog.

## 1. Vision
Every company can offer customers an agent that resolves issues end to end, safely, in any channel, on infrastructure the company controls.

## 2. Problem
- Customer-service automation today mostly deflects. It answers FAQs but cannot act, so customers repeat themselves to a human.
- Agents that can act are risky: wrong refunds, leaked data, invented policy. Teams lack tools to constrain, test and audit them.
- Enterprise-grade agent platforms are closed and gated by large contracts. Open building blocks exist, but every team re-assembles channels, memory, evals, guardrails and observability on its own.
- Changing agent behaviour is slow. Prompt edits ship without regression tests, and nobody can say whether a change made things better.

## 3. Product statement
NorthCX is an open-source platform for building, testing, releasing and running supervised customer-experience agents. Agents act on business systems through typed tools, are checked by supervisors, hand off to people with full context, and are released only after simulations pass.

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
Described in `NorthCX_Personas.md`: CX lead, platform engineer, compliance owner, support agent, reviewer, administrator, and the end customer.

## 7. Scope
### In scope (v1)
Agent authoring in code and Studio, tools and approvals, supervision, handoff, chat and email and messaging, knowledge retrieval, persistent memory, simulations, release management, traces and insights, self-hosting, voice (late v1).
### Out of scope (v1)
General-purpose autonomous agents (browsing, code execution), hosted multi-tenant SaaS, replacing the helpdesk, outcome-based billing, full workforce management.

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
