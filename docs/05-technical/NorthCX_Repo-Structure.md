# NorthCX Repo Structure

Status: Draft. The repository now has `backend/` (Python product backend), `prototype/` (TypeScript reference), `third_party/`, `NOTICE` and `THIRD_PARTY.md`. `web/` is still to come.

```
northcx/
├── README.md
├── package.json, tsconfig.json
├── docs/                 numbered documentation phases
├── src/
│   ├── core/             runtime, agent, guardrails, store, trace, llm, types   (built)
│   ├── sim/              simulation runner and judge                            (planned)
│   └── server/           HTTP API, widget, entrypoint                           (built)
├── examples/support/     example agent and tools                                (built; scenarios planned)
└── tests/                runtime and server tests with a scripted model         (built)
```

Reuse layout (see Code Reuse Policy): `NOTICE`, `THIRD_PARTY.md` and `third_party/<source>/` hold attribution and provenance for copied code.

Target split once stable: `packages/core`, `packages/sim`, `apps/server`, `apps/studio`, `adapters/*`.

Conventions: backend in Python with typed models and pytest; web platform in strict TypeScript; no network in unit tests.

## Target layout (product)
```
northcx/
├── backend/              Python (FastAPI): runtime, supervision, memory, knowledge, simulation, release, audit, API
│   ├── northcx/
│   ├── adapters/         channels, inbox, voice, observability export
│   └── tests/
├── web/                  Next.js platform: Studio, insights, approvals, admin
├── prototype/            TypeScript reference implementation (today's src/, examples/, tests/)
├── third_party/          copied source with original licences (see Code Reuse Policy)
├── NOTICE, THIRD_PARTY.md
└── docs/
```
