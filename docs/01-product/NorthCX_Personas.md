# NorthCX Personas

Status: Draft. Personas are hypotheses to validate with user interviews, not research findings.

## 1. Maya, CX / Support Lead (primary buyer)
- **Goal:** raise resolution rate and cut cost per contact without hurting satisfaction.
- **Pain:** current bots deflect poorly; changing behaviour needs engineering tickets.
- **Needs:** edit policies in plain language, see why a conversation failed, safe rollout.
- **Success:** resolution rate and CSAT up, escalations arrive with context.

## 2. Dev, Platform Engineer (primary builder)
- **Goal:** ship and maintain agents like any other service.
- **Pain:** glue code between model, tools, channels and evals; no regression tests for prompts.
- **Needs:** agents and tools in code, schemas, CI simulations, self-hosting.
- **Success:** agent changes gated by tests; deploys on existing infrastructure.

## 3. Sam, Compliance / Security Owner (approver)
- **Goal:** keep customer data and actions under control.
- **Pain:** unclear what an agent did and why; PII in logs.
- **Needs:** audit trail, approval gates, data residency, role-based access.
- **Success:** every action traceable; sensitive actions require sign-off.

## 4. Jo, Human Support Agent (downstream user)
- **Goal:** pick up escalations quickly.
- **Pain:** customers repeat themselves after handoff.
- **Needs:** full transcript, actions taken, reason for escalation.
- **Success:** shorter handle time on escalated cases.

## Persona to feature map
| Persona | Key features |
|---|---|
| Maya | Studio, insights, simulations summary, policy editing |
| Dev | Agent SDK, tool schemas, CI simulations, traces |
| Sam | Guardrails, approvals, audit log, RBAC |
| Jo | Handoff with transcript, human inbox |
