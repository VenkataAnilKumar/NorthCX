# NorthCX

Open-source platform for deploying supervised AI agents that resolve customer issues end to end, built on the Claude API.

## What it does
- Agents defined by goals and guardrails, with typed tools
- Supervision of every reply and tool call, input checks (PII masking, prompt-injection), human approval for sensitive actions
- Human handoff with full context
- Per-conversation traces
- Simulation testing (planned), more channels (phased), web platform and Studio (planned)

## Layout
| Path | Contents |
|---|---|
| `src/backend/` | Python product backend (FastAPI): runtime, guardrails, safety, stores, server, example agent, tests |
| `src/web/` | Web platform (Next.js): overview, test console, conversations and traces, approvals, agents, settings |
| `src/prototype/` | TypeScript reference implementation of the runtime semantics |
| `third_party/`, `NOTICE`, `THIRD_PARTY.md` | Provenance and licences of copied code |
| `docs/` | Documentation; start at `docs/README.md` |

## Status
Early development. The Python backend reproduces the prototype's runtime, API and example agent (156 backend tests and 11 web tests passing with a scripted model) and adds copied/adapted input guardrails from a reference project. The web platform (`src/web`) is browser-tested against the backend. Postgres persistence and approval resume (exactly-once execution, outcomes delivered to the customer, expiry) are built. Handoffs (a package with the transcript, actions and facts, a queue, and always-to-a-person topics) are built. Simulations, versions, channels, the Studio editor and insights are planned.

## Quick start (backend)
```bash
cd src/backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
ANTHROPIC_API_KEY=... python -m northcx    # http://localhost:3000 (NORTHCX_DEMO=1 uses an offline demo model)
# Postgres storage: docker compose up -d postgres, then add
#   NORTHCX_DATABASE_URL=postgresql://northcx:northcx@localhost:5432/northcx
```

## Quick start (web)
```bash
cd src/web
npm install
npm test
NORTHCX_API_URL=http://localhost:3000 npm run dev   # http://localhost:3001
```

## Documentation
See [`docs/README.md`](docs/README.md). External research and component selections are in [`docs/00-reference/NorthCX_Reference.md`](docs/00-reference/NorthCX_Reference.md).

## Licence
Apache-2.0. See `LICENSE`; copied code keeps its own notices (`NOTICE`, `THIRD_PARTY.md`).
