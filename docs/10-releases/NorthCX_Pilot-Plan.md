# Design-partner pilot plan (WP 7.2)

Status: **Ready to agree with a partner. Not started: it needs a pilot customer.** Written 2026-11-23. Master for: how one company runs NorthCX with real customers for the first time, what is measured, when to stop, and what may be said afterwards. Every number below is a proposal for the owner and the partner to confirm before the pilot starts; none is a result.

## 1. What the pilot is for
To find out, with one company's real conversations and an agreed period, whether a supervised agent resolves a defined set of customer questions without a policy violation reaching a customer, how much people have to correct it, and what running it costs. It is not a load test, a security test (see the penetration test brief) or a sales demo.

## 2. Before it starts (gates the partner and NorthCX must both meet)
| # | Gate | Check |
|---|---|---|
| G1 | A model qualified for the partner's agents: the agent's required scenarios pass on that exact model (`POST /v1/agents/{id}/qualifications`). No qualified model, no pilot. | The qualification record, with the model and the agent version |
| G2 | One to three named intents in scope, each with at least one required scenario written with the partner from their own (invented-data) examples | The scenarios exist and pass on the qualified model |
| G3 | Data handling agreed in writing: where data lives (one region), retention (`NORTHCX_RETENTION_DAYS`), who may export or erase, which model providers see conversation text (the residency report), the partner's own legal basis | A signed note; the residency report attached |
| G4 | Named people: a pilot owner at the partner, two release approvers (the two-person rule), reviewers for hand-offs and the sampled review, and one person who may stop everything | Names recorded |
| G5 | The stop button works: the partner has used the kill switch on a test agent; the alert webhook reaches a channel someone reads (System health shows alert delivery working) | A dated test |
| G6 | Backups taken and a restore drill run on the partner's own deployment | The backup file and the drill's row counts |
| G7 | The usability gate (`../02-studio/NorthCX_Usability-Gate.md`) passed by the partner's own CX lead, or the partner accepts in writing that NorthCX staff configure the agent | The gate record, or the acceptance |

## 3. Stages
| Stage | What happens | Customers see | Exit |
|---|---|---|---|
| 0. Set up (about a week) | Install with `scripts/setup.py`; connect tools; write and test the agent; qualify the model; release to a staging environment | Nothing | G1 to G7 met |
| 1. Shadow (at least 2 weeks and at least 200 customer messages in scope) | The agent drafts; a person sends, edits or rejects every draft (shadow mode). Nothing the agent writes reaches a customer unreviewed. | Replies from people, as today | The shadow numbers below meet their gates |
| 2. Staged rollout (at least 2 weeks) | The agent answers the in-scope intents itself for 10%, then 25%, 50% and 100% of those conversations (a rollout with a percentage; each step needs the release approvers and a day of watching) | Agent replies for the share and intents in scope; everything else, and anything the agent hands over, goes to people | The rollout numbers meet their gates for two weeks at the final share |
| 3. Report | The measured results, with denominators, go to the partner first | Nothing new | Partner reads and agrees what may be published |

## 4. What is measured
Every figure is reported with its numerator and denominator, the period, and the number of conversations it covers. A figure computed from fewer than 30 conversations is shown as a count, not a rate.

| Measure | Definition (where it comes from) | Proposed gate |
|---|---|---|
| Draft acceptance (shadow) | Drafts sent unchanged / drafts decided (`GET /v1/shadow/summary`; edited and rejected counted separately with their reasons) | Watched; no gate (the first baseline) |
| Policy-violation escape | Agent replies or actions that broke a stated policy and reached a customer / conversations the agent answered, found by the sampled review | 0. One escape stops the rollout until fixed and the scenario that would have caught it is added |
| Escalation correctness | Hand-offs a reviewer judges appropriate / hand-offs reviewed (a sample of at least 30, or all if fewer) | At least 95% |
| Unneeded escalation | Hand-offs a reviewer says the agent could have handled / hand-offs reviewed | Watched; falling over the period |
| Resolution, counting returns | `resolutionFirm` on the Insights page, for the in-scope intents; with its `checkable` share (how many conversations have a known customer) | At least 60%, and reported next to how many were checkable |
| Containment | Conversations that never reached a person / conversations | Watched; no gate until a baseline exists |
| Customer rating | Average rating and response rate (`satisfaction`) | At or above the partner's human baseline for the same period, if they have one |
| Model errors and fallbacks | `errorRate` and `fallbackModelRate` | Errors below 2% of turns (proposal) |
| Cost per resolved conversation | Model cost (from the usage report) plus review time the partner records / resolved conversations | Reported; no gate |
| Time to answer | p95 reply time (`latencySeconds`) | Reported against the partner's expectation, set after the first week |

The baseline for each comparison is the partner's own figure for the same intents before the pilot, supplied by the partner. If they have none, the pilot reports NorthCX's figures alone and does not claim an improvement.

## 5. Stop conditions (any one: pause the rollout and tell the pilot owner the same day)
- A policy-violation escape (see above).
- A tool changed something it should not have (a refund, a cancellation) that no person approved.
- The model provider is unreachable or over budget for more than an hour and conversations are not reaching people (System health, alerts).
- The partner asks to stop. The kill switch is theirs.
- Hand-off rate or unneeded escalation rising for three days running without a reason found.

Rolling back is one action (the release rollback, or the rollout abort), and tested in stage 0.

## 6. Who does what
| Role | Does |
|---|---|
| Partner pilot owner | Decides scope, signs the data note, reads the report |
| Partner release approvers (two) | Approve each release and each rollout step; neither may approve their own request |
| Partner reviewers | Decide hand-offs, send or reject shadow drafts, take the review sample |
| NorthCX (the owner's team) | Installs, writes scenarios with the partner, qualifies the model, watches the numbers daily in stage 2, fixes what is found, writes the report |

## 7. What may be said afterwards
- Only what the partner agreed after reading the report. The partner is named only with their written consent.
- Figures are published with denominators and the period, and with the limits: one company, one region, the intents in scope, the model used, and any stop that happened.
- No claim of savings or satisfaction without the partner's own baseline.
- No customer conversation text, and no invented customers or quotes, in any case study.

## 8. What is not promised
That the agent will qualify for the partner's intents (the model pass may fail, and then the answer is a different model or a smaller scope), any resolution rate before it is measured, or any saving.

## 9. Open before it can start
A pilot customer; a model that qualifies (the first local pass, Qwen2.5 3B, did not: 8 of 18 shipped scenarios); the owner's confirmation of the numbers above; the penetration test done or its absence stated to the partner.
