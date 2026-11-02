# NorthCX Success Metrics

Status: Draft. Targets are initial proposals; baselines come from pilots.

## Product metrics
| Metric | Definition | Target |
|---|---|---|
| Resolution rate | Resolved conversations / conversations on in-scope intents (see PRD definition) | >= 60% on pilot intents |
| Containment rate | Conversations that end without human handoff / all conversations | Track; no target until baseline |
| Escalation correctness | Handoffs judged appropriate / handoffs (sampled review) | >= 95% |
| Unneeded escalation | Handoffs a reviewer says the agent could have handled / handoffs | Falling trend |
| Policy-violation escape | Violating replies or actions reaching customers / conversations | 0 on safety suite; monitored in production |
| Customer satisfaction | Post-conversation survey score | At or above human baseline |
| Reopen rate | Conversations reopened on the same issue within the window | Lower than baseline |
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

## Adoption metrics
Active agents, conversations per month, tools per agent, Studio weekly active editors, contributors and external adapters.

## Measurement rules
- Define intent scope before measuring resolution.
- Sample human review for correctness metrics; never rely on the judge alone.
- Report numerator, denominator and period with each figure.
