# NorthCX Pricing Model

Status: **Plan**. Updated: 2026-11-09. Master for: pricing options (blocked on D1, open versus commercial). No market testing; figures are deliberately absent.

## Positioning
NorthCX core is open source and free to self-host. Revenue, if any, comes from services and optional commercial offerings; this document keeps those options open.

## Cost drivers for a deployment
| Driver | Notes |
|---|---|
| Model usage | Largest variable cost; scales with conversations, steps and history length |
| Supervisor model usage | Extra calls per reply; cheaper model recommended |
| Voice | Speech services and telephony add per-minute cost |
| Infrastructure | Servers, database, queue |
| Human review | Approvals and failure review |
| Channels and inbox | Messaging provider fees |

## Packaging options
| Option | Description | Pros | Cons |
|---|---|---|---|
| A. Open core, self-host | Core under a permissive licence; paid support and services | Trust, adoption | Revenue depends on services |
| B. Managed cloud | Hosted NorthCX billed by usage | Recurring revenue | Operating burden; multi-tenancy is out of v1 scope |
| C. Outcome-based | Charge per resolved conversation | Aligned with value | Needs a trusted definition of "resolved" and reliable billing |
| D. Commercial add-ons | Paid Studio, SSO, advanced insights | Clear upgrade path | Splits the community |

## Recommendation
Start with A for v1. Revisit B and C when resolution measurement is reliable and multi-tenancy exists.

## Feature split principle
Anything needed to run safely stays open: runtime, supervision, approvals, audit, simulations, release management. Candidates for commercial add-ons: SSO, advanced analytics, hosted operations, premium support.

## Decision inputs needed
- Customer discovery on willingness to pay.
- Definition and audit method for "resolved".
- Hosting and support capacity.
