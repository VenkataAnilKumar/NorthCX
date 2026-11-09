# NorthCX Competitive Analysis

Status: **Reference**. Updated: 2026-11-09. Master for: market position (named comparisons are in 00-reference). Named competitors and sourced comparisons are in `00-reference/NorthCX_Reference.md` (sections 1, 2, 7, 9). Ratings below are hypotheses.

## 1. Market map
| Segment | What they offer | Strength | Weakness vs NorthCX goals |
|---|---|---|---|
| Enterprise CX agent platforms | Managed agents, channels, analytics, simulations | Complete, supported | Closed, contract-gated, hosted |
| Helpdesk vendors' AI add-ons | Bots inside the support tool | Tight inbox integration | Limited actions, vendor lock-in |
| General agent frameworks | Building blocks for agents | Flexible, open | No CX features out of the box |
| Workflow and no-code builders | Visual automation | Fast to prototype | Weak supervision and testing |
| Knowledge and search assistants | Answers from company data | Good retrieval | Little action-taking |
| Build in-house | Custom | Fits exactly | Slow, costly, re-solves common problems |

## 2. Capability comparison (hypothesis)
Legend: strong, partial, weak, none.
| Capability | Enterprise platforms | Helpdesk add-ons | Frameworks | Builders | NorthCX today (2026-11-09) |
|---|---|---|---|---|---|
| Takes actions on business systems | strong | partial | partial | partial | built |
| Supervision and approvals | strong | partial | partial | weak | built |
| Simulation testing | strong | weak | partial | none | built |
| Release management | partial | weak | none | partial | built |
| Omnichannel incl. voice | strong | partial | none | partial | built: six channels; voice through a bridge the operator connects (no speech or telephony shipped) |
| Human handoff with context | strong | strong | none | weak | built |
| Knowledge grounding | strong | partial | partial | partial | built |
| Low-code authoring | strong | strong | weak | strong | built: Studio editor, templates, drafts from procedures |
| Open source and self-host | none | none | strong | partial | built |
| Model choice | partial | weak | strong | partial | Claude today; other providers and local models planned (E1) |
| Staff workspace and assistants | not assessed | not assessed | not assessed | not assessed | designed, not built (after 1.0) |

## 3. Positioning
For companies that want customer-service agents that act, NorthCX is the open-source platform that makes agents safe to run and safe to change: supervised actions, simulation-gated releases and self-hosting. Unlike closed platforms it can be inspected, extended and run anywhere; unlike generic frameworks it is built for customer service.

## 4. Win and loss scenarios
| We win when | We lose when |
|---|---|
| Data control or self-hosting is required | Buyer wants a fully managed service today |
| Engineering team wants agents as code | No engineering capacity at all |
| Safety, audit and testing matter most | Buyer wants a vendor to operate it for them |
| Budget favours open source plus services | Buyer is committed to one helpdesk's native AI |
| | Buyer needs packaged speech and telephony, or a staff workspace today |

## 5. Messaging
- Resolve, don't deflect.
- Every action checked. Every change tested.
- Open source. Your infrastructure. Your models.

## 6. Differentiation evidence
| Claim | Evidence to produce |
|---|---|
| Safer by default | Safety suite results with zero escapes |
| Easier to change | Release lead time and rollback demo |
| Easy to self-host | Time from clone to running agent |
| Lower cost | Published cost-per-resolution method |
| CX-ready | Example agent with actions, approvals, handoff |

## 7. Risks and responses
| Risk | Response |
|---|---|
| Established vendors out-integrate us | Open connector library and community |
| Composition adds integration burden | Interfaces, tested adapters |
| Frameworks add CX features | Depth in supervision, testing, release management |
| Model providers add native agent features | Stay model-agnostic; add value in governance |

## 8. To verify
All competitor facts through primary sources once reachable. The NorthCX column says what is built; nothing in it has been measured against a competitor, and no customer evidence exists yet.
