# NorthCX Repo Structure

Status: Draft (current and target)

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

Conventions: ESM, strict TypeScript, Zod at boundaries, no network in unit tests.
