# NorthCX

Open-source platform for deploying supervised AI agents that resolve customer issues end to end, built on the Claude API.

## What it does
- Agents defined by goals and guardrails, with typed tools
- Policy supervision of every reply and tool call, human approval for sensitive actions
- Human handoff with full context
- Per-conversation traces
- Simulation testing (planned), multiple channels (phased), low-code Studio (planned)

## Status
Early development. The product will be a Python backend with a TypeScript web platform, assembled by copying and adapting licensed reference code. The repository currently holds a TypeScript prototype (`src/core`, `src/server`, `examples/support`) that serves as the reference implementation of runtime behaviour, covered by tests with a scripted model. Simulation testing, persistence, approval resume and channel adapters are planned.

## Quick start
```bash
npm install
npm run typecheck
npm test
ANTHROPIC_API_KEY=... npm run dev   # http://localhost:3000
```

## Documentation
See [`docs/README.md`](docs/README.md) for the index. External research and component selections are in [`docs/00-reference/NorthCX_Reference.md`](docs/00-reference/NorthCX_Reference.md).

## Licence
To be decided (proposal: Apache-2.0).
