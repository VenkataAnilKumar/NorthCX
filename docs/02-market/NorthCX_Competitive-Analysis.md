# NorthCX Competitive Analysis

Status: Draft. Competitor details come from third-party summaries and are **unverified**.

## Segments
| Segment | Examples | Relevance |
|---|---|---|
| Enterprise CX agent platforms | Sierra | Direct benchmark |
| Incumbent helpdesk AI | Helpdesk vendors' built-in bots | Compete for the same budget |
| Open-source agent frameworks | Agno | Building block / alternative runtime |
| Open-source workflow builders | Sim | Studio building block |
| Open-source knowledge/chat | Onyx | Knowledge building block |
| General agent platforms | Kortix/Suna | Different use case |

## Comparison
| Dimension | Sierra (reported) | Agno | Sim | Onyx | NorthCX (target) |
|---|---|---|---|---|---|
| Open source | No | Yes (Apache-2.0) | Yes (Apache-2.0) | Yes (MIT, `ee/` excluded) | Yes |
| CX-specific out of the box | Yes | No | No | No | Yes |
| Omnichannel incl. voice | Yes | Build it | Build it | Limited | Phased (chat first) |
| Supervisor / guardrails | Yes | Guardrails | Limited | Limited | Yes |
| Simulation testing | Yes | Evals | No | No | Yes (planned) |
| Low-code builder | Yes | Control plane UI | Yes | Agent builder | Phase 4 |
| Self-host | Unclear | Yes | Yes | Yes | Yes |

## Differentiation
1. Open and self-hostable CX platform, not a general framework.
2. Safety first: supervisors, approvals and simulations are core, not add-ons.
3. Composes proven projects instead of reinventing them.
4. Claude-first, model-agnostic through an interface.

## Risks
- Sierra and incumbents move faster on enterprise integrations.
- Composition adds integration burden and licence review.
- Frameworks like Agno may add CX features.

## To verify
Sierra's pricing, SDK availability and channel list; current licences and versions of every open-source project.
