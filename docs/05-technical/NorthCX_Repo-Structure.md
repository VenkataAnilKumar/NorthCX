# NorthCX Repo Structure

Status: Draft. All code lives under `src/`. `src/backend` (Python product backend) and `src/prototype` (TypeScript reference) exist; `src/web` (Next.js platform) now exists.

```
northcx/
├── README.md, LICENSE, NOTICE, THIRD_PARTY.md
├── docker-compose.yml        the full stack; docker-compose.dev.yml publishes the database; .env.example
├── scripts/                  repository checks (restricted paths, provenance)
├── .github/workflows/        CI
├── docs/                     numbered documentation phases
├── third_party/              copied source originals and licences (see Code Reuse Policy)
└── src/
    ├── backend/              Python (FastAPI): runtime, supervision, memory, safety, API (built)
    │   ├── northcx/          package
    │   ├── examples/         example agents
    │   └── tests/
    ├── web/                  Next.js platform: overview, test console, conversations, approvals, agents, settings (built); Studio editor and insights (planned)
    └── prototype/            TypeScript reference implementation of the runtime semantics
```

Planned backend modules: `simulation/`, `release/`, `audit/`, `knowledge/`, `adapters/` (channels, inbox, voice, observability export).

Reuse layout (see Code Reuse Policy): `NOTICE`, `THIRD_PARTY.md` and `third_party/<source>/` hold attribution and provenance for copied code. Adapted files live in the owning module and carry attribution headers.

Conventions: backend in Python with typed models and pytest; web platform in strict TypeScript; no network in unit tests.
