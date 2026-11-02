# NorthCX Implementation Checklist

Status: Living checklist

## Foundation
- [x] Repo scaffold, TypeScript config, dependencies install
- [x] Core runtime, tools, guardrails, memory, traces (typechecked)
- [x] Unit tests for the runtime (history validity, approvals, handoff, guardrails, model failure)
- [ ] Chat and trace API, auth, widget
- [ ] Example support agent
## Quality
- [ ] Simulation runner and scenarios
- [ ] CI workflow with required checks
- [ ] Judge rubric and live-model trials
## Data
- [ ] Postgres store and migrations
- [ ] Retention and deletion jobs
- [ ] Trace redaction
## Safety
- [ ] Approval resume flow
- [ ] Policy test suite
- [ ] Threat-model review
## Channels and knowledge
- [ ] Inbox adapter
- [ ] Retrieval tool
## Platform
- [ ] Trace export
- [ ] Studio
- [ ] Insights
- [ ] Voice
## Release
- [ ] Choose licence
- [ ] Contribution guide
- [ ] v1.0
