# NorthCX Product Definition

Status: Draft

## One line
NorthCX lets a company deploy supervised AI agents that resolve customer issues end to end, across chat, email, messaging and voice, on open-source infrastructure it controls.

## Problem
Enterprise customer-experience agent platforms are closed and gated to large contracts. Teams that want the same capability, with control over data and models, must stitch together agent frameworks, channel tools, evals and observability themselves.

## Solution
A composed open-source platform, with Claude as the default model:
- **Agents defined by goals and guardrails**, not flowcharts.
- **Actions** against the company's systems (orders, billing, accounts) with approval rules.
- **Supervision:** policy checks on every reply and tool call, plus human handoff.
- **One agent, many channels:** web chat first, then email, SMS, WhatsApp, voice.
- **Simulation testing** before release, and traces for every conversation.

## Target users
| Persona | Need |
|---|---|
| CX / support lead | Deploy and tune agents without code; see resolution rate and failures |
| Platform engineer | Define agents and tools in code, test in CI, self-host |
| Compliance / security owner | Auditable actions, PII control, approval gates |
| Human support agent | Clean handoff with full context |

## Principles
1. Open source and self-hostable first.
2. Compose proven projects; build only the gaps.
3. Every action is traceable and policy-checked.
4. Safe by default: fail closed when a supervisor is unsure.

## Non-goals (v1)
- General-purpose autonomous agents (browsing, code execution).
- A hosted multi-tenant SaaS.
- Replacing the helpdesk; NorthCX integrates with one.

## Open decisions
- Final licence for NorthCX itself (proposal: Apache-2.0).
- Whether Studio is adopted from an existing project or built in-house (see the Reference).
