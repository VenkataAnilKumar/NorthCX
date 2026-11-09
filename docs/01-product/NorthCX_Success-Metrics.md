# NorthCX Success Metrics

Status: Draft. Targets are initial proposals; baselines come from pilots.

## Product metrics
| Metric | Definition | Target |
|---|---|---|
| Resolution rate (provisional, built) | Resolved conversations / conversations past the window, on in-scope intents (see PRD definition: completed, no hand-off, quiet for 3 days; same-conversation reopens only for now) | >= 60% on pilot intents |
| Containment rate | Conversations that end without human handoff / all conversations | Track; no target until baseline |
| Escalation correctness | Handoffs judged appropriate / handoffs (sampled review) | >= 95% |
| Unneeded escalation | Handoffs a reviewer says the agent could have handled / handoffs | Falling trend |
| Policy-violation escape | Violating replies or actions reaching customers / conversations | 0 on safety suite; monitored in production |
| Customer satisfaction | Post-conversation survey score | At or above human baseline |
| Reopen rate | Conversations reopened on the same issue within the window (needs a customer link across conversations; not built) | Lower than baseline |
| Cost per resolution | (Model + infrastructure + review cost) / resolved conversations | Falling trend |
| First-reply latency | p95 time to first token or reply | Set after streaming |
| Handoff context completeness | Handoffs with transcript, actions and summary / handoffs | 100% |

## Build and release metrics
| Metric | Definition | Target |
|---|---|---|
| Time to first agent | Clone to a working agent from a template | < 1 day |
| Simulation coverage | In-scope intents with at least one required scenario | >= 90% |
| Release lead time | Change merged to production | Falling trend |
| Failed-release rate | Releases rolled back / releases | Falling trend |
| Regression catch rate | Regressions caught by CI / regressions found anywhere | >= 80% |
| Judge agreement | Judge verdicts matching human labels on the calibration set | >= 90% |

## Staff platform metrics (after 1.0; proposals, no baseline yet)
| Metric | Definition | Target |
|---|---|---|
| Time to first useful result | Pilot task start to a saved output, median | Set after a pilot |
| Plan approval rate | Plans approved without edit / plans shown | Track; low means plans miss the intent |
| Hand-off handling time | Hand-off shown to resolved, median | Falling trend |
| Draft acceptance | Drafted replies sent with small or no edits / drafts shown (sampled) | Track |
| Unchecked-send escape | Messages sent to customers without a person's action | 0 |
| Approval turnaround | Approval requested to decided, p90 | Falling trend |
| Assistant citation coverage | Answers with a source / answers that need one | >= 95% (to validate) |
| Cost per task | Model cost and tools per finished task | Falling trend |
| Weekly active staff | Staff who open the Workspace weekly / licensed staff | Track |

## Adoption metrics
Active agents, conversations per month, tools per agent, Studio weekly active editors, contributors and external adapters.

## Measurement rules
- Define intent scope before measuring resolution.
- Sample human review for correctness metrics; never rely on the judge alone.
- Report numerator, denominator and period with each figure.
