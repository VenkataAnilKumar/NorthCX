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
Early development. The Python backend reproduces the prototype's runtime, API and example agent (745 backend tests and 22 web tests passing with a scripted model) and adds copied/adapted input guardrails from a reference project. The web platform (`src/web`) is browser-tested against the backend. Postgres persistence and approval resume (exactly-once execution, outcomes delivered to the customer, expiry) are built. Handoffs (a package with the transcript, actions and facts, a queue, and always-to-a-person topics) are built. Scenario simulations (18 example scenarios (3 of them adversarial attack suites), a judge, and a command line that gates CI) are built. Stored simulation runs, a release-gate rule tied to the exact agent version, and a Simulations page are built. Immutable agent versions with diffs, gated publishing and one-step rollback (with a versions page) are built. Customers can also email the agent (threaded, loop-safe, replies over SMTP). Customers chat with short-lived, conversation-scoped tokens (no keys in browsers). Roles, hashed API keys, a tamper-evident audit log and rate limits (with an Access page) are built. Environments, channels, the Studio editor and insights are planned.

## Quick start (everything, in containers)
```bash
cp .env.example .env          # set NORTHCX_DB_PASSWORD and NORTHCX_API_KEY, plus ANTHROPIC_API_KEY (or NORTHCX_DEMO=1)
docker compose up -d --build --wait
# console: http://localhost:3001   API: http://localhost:3000
```

## Quick start (backend from source)
```bash
cd src/backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
NORTHCX_API_KEY=<long random value> ANTHROPIC_API_KEY=... python -m northcx    # http://localhost:3000; without NORTHCX_API_KEY the server is open (development only) (NORTHCX_DEMO=1 uses an offline demo model)
# Postgres storage: docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres, then add
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
