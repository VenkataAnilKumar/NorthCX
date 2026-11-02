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
│   └── server/           HTTP API and widget                                   (planned)
├── examples/support/     example agent, tools, scenarios                        (planned)
└── tests/                unit tests with a scripted model                       (planned)
```

Target split once stable: `packages/core`, `packages/sim`, `apps/server`, `apps/studio`, `adapters/*`.

Conventions: ESM, strict TypeScript, Zod at boundaries, no network in unit tests.
