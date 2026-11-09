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
| Infrastructure | Servers and the Postgres database |
| Human review | Approvals and failure review |
| Channels and inbox | Messaging provider fees |

## Packaging options
| Option | Description | Pros | Cons |
|---|---|---|---|
| A. Open core, self-host | Core under a permissive licence; paid support and services | Trust, adoption | Revenue depends on services |
| B. Managed cloud | Hosted NorthCX billed by usage | Recurring revenue | Operating burden; needs multi-tenancy (planned after 1.0, E2) |
| C. Outcome-based | Charge per resolved conversation | Aligned with value | Needs a trusted definition of "resolved" and reliable billing |
| D. Commercial add-ons | Paid extras on top of the open product | Clear upgrade path | Splits the community; features already released open (Studio, single sign-on, insights) cannot be taken back |

## Recommendation
Start with A for v1. Revisit B and C when resolution measurement is reliable and multi-tenancy exists. The decision is D1 (open versus commercial), still open; the leaning recorded in decision 170 is open core with everything built so far staying open. If billing is built, the plan is to meter everything and bill on conversations and staff seats (D8).

## Feature split principle
Anything needed to run safely stays open: runtime, supervision, approvals, audit, simulations, release management. Single sign-on, the Studio and insights are already built and released under Apache-2.0, so they stay open. Remaining candidates for commercial offerings: hosted operations, a back office for a hosted service, premium support and services.

## Decision inputs needed
- Customer discovery on willingness to pay.
- Definition and audit method for "resolved".
- Hosting and support capacity.
