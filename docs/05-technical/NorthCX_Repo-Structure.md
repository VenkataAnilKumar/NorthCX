# NorthCX Repo Structure

Status: Draft. All code lives under `src/`. One repository holds every part of the product; deployment is separate (each app ships as its own container or static site). Decision log entry 140 (proposed: the target layout below is not yet confirmed by the owner).

## Today
```
northcx/
├── README.md, LICENSE, NOTICE, THIRD_PARTY.md, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md
├── docker-compose.yml        the full stack; docker-compose.dev.yml publishes the database; .env.example
├── scripts/                  repository checks (restricted paths) and the route-reference generator
├── .github/workflows/        CI
├── docs/                     numbered documentation phases; docs/assets holds the README screenshots
├── deploy/                   reserved for the deployment kit (Helm, Terraform, upgrade tool)
└── src/
    ├── backend/              Python (FastAPI): runtime, supervision, memory, safety, channels, API (one package, `northcx/`)
    │   ├── northcx/          package
    │   ├── examples/         example agents, scenarios, connectors, config samples
    │   └── tests/
    ├── web/                  Studio, the operator console (Next.js)
    ├── sdk/                  browser SDK and `<northcx-chat>` widget (TypeScript, no runtime dependencies)
    └── prototype/            TypeScript reference implementation of the runtime semantics
```

## Target layout (planned in `08-implementation/NorthCX_Gap-Closure-Plan.md`, items E0.7 and E0.8)
```
src/
├── backend/                  unchanged: one Python package, scaled by replicas and background workers
├── apps/                     one Next.js app per audience, each its own image
│   ├── studio/               operator console (today's src/web, renamed)
│   ├── workspace/            staff workspace (created when its first feature arrives)
│   ├── admin/                tenant admin portal
│   ├── ops/                  ops console, shipped only to private deployments
│   └── backoffice/           vendor-internal: tenants, licenses, flags, support access (internal network only)
├── packages/                 shared by the apps through npm workspaces
│   ├── ui/                   components and design tokens
│   └── api-client/           typed API client, session and role helpers
├── site/                     marketing, Trust Center, Legal Center, developer portal (static content)
├── surfaces/                 embedded surfaces, one folder each: slack, teams, outlook-addin, word-addin, browser-extension
├── sdk/                      browser SDK and widget
└── prototype/                reference implementation
```

## Rules
- **One backend package.** Do not split the API into services; scale it with replicas and workers (E0.8).
- **Apps import packages, never each other.** Anything shared moves to `packages/`.
- **The back office is never part of a customer-facing build**; its routes are served under `/platform/v1` on a separate listener.
- **Apps are created when their first feature arrives**, not as empty shells.
- **Later splits into separate repositories**, if needed: native mobile SDKs, vendor-store apps, the back office (if the project goes open core), and the marketing site (if non-engineers will edit it often).

## Reuse layout
`NOTICE`, `THIRD_PARTY.md` and `third_party/<source>/` hold attribution and provenance for copied code (see the Code Reuse Policy). Adapted files live in the owning module and carry attribution headers.

## Conventions
Backend in Python with typed models and pytest; web apps in strict TypeScript; no network in unit tests; every route that needs a key appears in the generated route reference; every setting appears in the Deployment Guide and `.env.example`.
