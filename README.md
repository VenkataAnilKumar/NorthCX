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
| `src/web/` | Web platform (planned): Studio and insights, built from reference code |
| `src/prototype/` | TypeScript reference implementation of the runtime semantics |
| `third_party/`, `NOTICE`, `THIRD_PARTY.md` | Provenance and licences of copied code |
| `docs/` | Documentation; start at `docs/README.md` |

## Status
Early development. The Python backend reproduces the prototype's runtime, API and example agent (29 passing tests with a scripted model) and adds copied/adapted input guardrails from a reference project. Persistence, approval resume, simulations, channels and the web platform are planned.

## Quick start (backend)
```bash
cd src/backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
ANTHROPIC_API_KEY=... python -m northcx    # http://localhost:3000
```

## Documentation
See [`docs/README.md`](docs/README.md). External research and component selections are in [`docs/00-reference/NorthCX_Reference.md`](docs/00-reference/NorthCX_Reference.md).

## Licence
To be decided (proposal: Apache-2.0).
