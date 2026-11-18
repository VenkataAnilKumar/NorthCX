# NorthCX Competitive Analysis

Status: **Reference**. Updated: 2026-11-18. Master for: market position (named comparisons are in 00-reference). Named competitors and sourced comparisons are in `00-reference/NorthCX_Reference.md` (sections 1, 2, 7, 9). Ratings below are hypotheses.

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

## 9. Overcoming the loss scenarios (2026-11-18)
How each "we lose when" case in section 4 is answered. Build items point at the priorities in `NorthCX_Agent-Platform-Design.md` (section 13); go-to-market items are proposals for the owner. Named competitors for each case are in `../00-reference/NorthCX_Competitor-Landscape.md`.

| We lose when | Answer now | Answer later | Proof that it worked |
|---|---|---|---|
| The buyer wants a fully managed service today | Make self-hosting feel managed: one-command install with a setup wizard, tested upgrades, backup and restore, a health page (operator experience) | A dedicated single-company instance run by the project or by certified partners (needs D1); multi-tenant cloud only after the penetration test | Time from clone to a running agent; an upgrade between two releases with no manual step |
| The buyer is committed to one helpdesk's built-in AI | Native connectors to that helpdesk (the tool gateway and first connectors), and **shadow mode** as the way in: NorthCX drafts beside the current setup and a person compares, with nothing replaced | Publish a side-by-side test of the same scenarios; cost per conversation against per-resolution pricing | Shadow-mode agreement rate; cost per conversation from the existing cost figures |
| There is no engineering capacity | Guided Studio for non-engineers; two or three ready-made agents for the target market (order status, refunds, returns, subscription changes) with passing tests | Split the work: an operator (engineer or partner) sets up once, the CX team owns everything after | The usability gate: a CX lead releases a template agent unaided |
| The buyer needs packaged speech and telephony | Do not build it yet; publish a documented, tested reference setup for one telephony provider on the existing bridge protocol ("bring your own phone system") | An open-source voice framework if pilots keep asking | Pilot requests for voice |
| No production evidence exists (applies to every deal) | The live-model pass; an independent penetration test; a firm resolution figure | One design-partner pilot in the target market: shadow mode, then a staged rollout, measured honestly | A published case study with its denominators |

Order: proof first (live-model pass, penetration test), then connectors and shadow mode, then guided Studio and ready-made agents, then operator experience, then D1 and a managed offering, then a voice reference setup.

