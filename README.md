# NorthCX

Open-source platform for deploying supervised AI agents that resolve customer issues end to end, built on the Claude API.

## What it does
- Agents defined by goals and guardrails, with typed tools
- Policy supervision of every reply and tool call, human approval for sensitive actions
- Human handoff with full context
- Per-conversation traces
- Simulation testing (planned), multiple channels (phased), low-code Studio (planned)

## Status
Early development. The core runtime is scaffolded in `src/core`. The server, simulation testing and channel adapters are planned.

## Quick start
```bash
npm install
npm run typecheck
```

## Documentation
See [`docs/README.md`](docs/README.md) for the index. External research and component selections are in [`docs/00-reference/NorthCX_Reference.md`](docs/00-reference/NorthCX_Reference.md).

## Licence
To be decided (proposal: Apache-2.0).
