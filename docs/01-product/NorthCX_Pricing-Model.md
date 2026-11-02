# NorthCX Pricing Model

Status: Draft proposal. No market testing has been done; figures are intentionally absent.

## Positioning
NorthCX core is open source and free to self-host. Sierra, by contrast, is reported to price on outcomes (unverified).

## Options
| Model | Description | Pros | Cons |
|---|---|---|---|
| A. Open core, self-host only | Core Apache-2.0; paid support and services | Simple; builds trust | Revenue depends on services |
| B. Open core + managed cloud | Hosted NorthCX billed by usage | Recurring revenue | Operating burden; multi-tenancy is a non-goal for v1 |
| C. Outcome-based (resolutions) | Charge per resolved conversation | Aligns with value | Needs reliable resolution measurement and billing |
| D. Seat/usage for Studio | Paid Studio features | Clear upgrade path | Splits the community |

## Recommendation
Start with **A** for v1. Revisit **B** and **C** after the simulation and insights features can measure resolution reliably, since outcome pricing needs a trusted definition of "resolved".

## Open decisions
- What counts as a resolution (customer confirmation, no contact within N days).
- Which features, if any, are commercial-only.
