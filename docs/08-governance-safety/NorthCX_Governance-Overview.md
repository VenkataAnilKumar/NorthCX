# NorthCX Governance and safety: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** What keeps agents safe and accountable: guardrails and supervisors, approvals, access, audit, data controls, tenancy and security.

## Built
- Input checks (personal-data masking, injection, abuse, identity verification), reply and tool-output guardrails, an optional supervisor model, fail-closed behaviour
- Per-tool approval rules with exactly-once execution; forced hand-off topics
- Roles and hashed, scoped keys; single sign-on with OpenID Connect; a hash-chained audit log; privacy export, erasure and retention; a residency policy checked at start-up
- Tenancy as an evaluation preview: row-level security, a sealed secrets vault, a separate platform API, off by default

## Gaps and next steps
- An independent penetration test (an outside party)
- SAML: document an OpenID Connect bridge rather than build SAML (design section 13)
- Multi-tenancy beyond the preview after the penetration test

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Guardrails-and-Supervisors.md`](NorthCX_Guardrails-and-Supervisors.md) | Guardrails and supervisors (master) |
| [`NorthCX_Data-Flow.md`](NorthCX_Data-Flow.md) | Where data goes during a conversation |
| [`NorthCX_Threat-Model.md`](NorthCX_Threat-Model.md) | Threat model |
| [`NorthCX_Security-and-Compliance.md`](NorthCX_Security-and-Compliance.md) | Security controls and compliance mapping |
| [`NorthCX_Security-Review.md`](NorthCX_Security-Review.md) | Internal security review |
| [`NorthCX_Tenancy-ADR.md`](NorthCX_Tenancy-ADR.md) | Tenancy |
| [`NorthCX_Tenant-Isolation-Threat-Model.md`](NorthCX_Tenant-Isolation-Threat-Model.md) | Tenant isolation threat model |
| [`NorthCX_Penetration-Test-Brief.md`](NorthCX_Penetration-Test-Brief.md) | Penetration test brief |
| [`NorthCX_Licenses.md`](NorthCX_Licenses.md) | Licence rules |
| [`NorthCX_Code-Reuse-Policy.md`](NorthCX_Code-Reuse-Policy.md) | Code reuse policy |
