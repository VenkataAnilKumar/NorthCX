# NorthCX Personas

Status: Draft. Personas are hypotheses to validate with interviews, not research findings.

## Overview
| Persona | Role | Primary relationship | Main surfaces |
|---|---|---|---|
| Maya | CX / support lead | Owns outcomes | Studio, insights |
| Dev | Platform engineer | Builds and releases | Code, CLI, CI |
| Sam | Compliance / security owner | Approves and audits | Audit log, policies |
| Jo | Support agent | Receives handoffs | Human inbox |
| Rae | Reviewer / approver | Decides held actions | Approval queue |
| Ari | Administrator | Operates the platform | Settings, keys, deployment |
| Cam | End customer | Gets help | Chat, email, messaging, voice |

## Maya, CX / Support Lead
- **Jobs to be done:** raise resolution and satisfaction; lower cost per contact; change policy fast without an engineering ticket.
- **Pains:** bots deflect poorly; no visibility into why conversations fail; changes feel risky.
- **Needs:** edit instructions in plain language; failed-conversation review; proof a change is safe; staged rollout.
- **Objections:** "Will it say something wrong to a customer?" "Can my team use it without developers?"
- **Success measures:** resolution rate, satisfaction, escalation correctness.
- **Key features:** U1-U8, O5-O7, Q2-Q11, S7.

## Dev, Platform Engineer
- **Jobs:** build agents and tools like any other service; keep them tested and deployed.
- **Pains:** glue code for channels, memory, evals; prompts shipped without tests; opaque failures.
- **Needs:** agents as code, typed tools, local test runs, CI gate, traces, self-hosting.
- **Objections:** "Another framework to maintain." "Will it lock us to one model?"
- **Success:** failing changes caught before production; fast iteration.
- **Key features:** A2, T1-T8, Q1-Q10, O1-O3, P7.

## Sam, Compliance / Security Owner
- **Jobs:** keep customer data and actions under control; pass audits.
- **Pains:** unclear what an agent did and why; PII in logs; no approval trail.
- **Needs:** audit log, approval gates, redaction, retention, roles, data-flow documentation.
- **Objections:** "Where does customer data go?" "Who can change the agent?"
- **Success:** every action attributable; no PII exposure incidents.
- **Key features:** P2-P6, S6-S11, K8, O4.

## Jo, Support Agent
- **Jobs:** resolve escalated cases quickly.
- **Pains:** customers repeat themselves; missing context.
- **Needs:** transcript, actions taken, summary, suggested next steps, easy return of simple cases to the agent.
- **Success:** shorter handle time on escalations.
- **Key features:** H1, H4-H8.

## Rae, Reviewer / Approver
- **Jobs:** approve or reject held actions fast and safely.
- **Needs:** exact action payload, customer context, reason held, one-click decision with audit.
- **Key features:** H2, H3, U5, P3.

## Ari, Administrator
- **Jobs:** deploy, secure and operate NorthCX.
- **Needs:** container deployment, configuration, key and role management, backups, upgrades, health checks.
- **Key features:** P1-P4, P7, P9, T7.

## Cam, End Customer
- **Jobs:** get a problem solved quickly, without repeating information.
- **Needs:** fast, correct, honest answers; a human when needed; the same experience across channels; their language.
- **Key features:** C1-C10, R9, H1, K2.

## Persona to goal map
| Goal | Primary persona |
|---|---|
| Higher resolution | Maya |
| Safe, fast releases | Dev, Maya |
| Auditability | Sam, Rae |
| Smooth handoff | Jo, Cam |
| Operability | Ari |
