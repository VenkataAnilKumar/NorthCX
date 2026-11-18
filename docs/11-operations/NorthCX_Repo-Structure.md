# NorthCX Repo Structure

Status: **Built**. Updated: 2026-11-09. Master for: repository layout. All code lives under `src/`. One repository holds every part of the product; deployment is separate (each app ships as its own container or static site). Decision log entry 140 (decided): several apps plus shared packages in one repository. Studio and the two shared packages are in place; the other apps are created when their first feature arrives.

## Today
```
northcx/
├── README.md, LICENSE, NOTICE, THIRD_PARTY.md, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md
├── docker-compose.yml        the full stack; docker-compose.dev.yml publishes the database; .env.example
├── scripts/                  repository checks (restricted paths), lock files, the route-reference and API-reference generators, design mockup generator and screenshots
├── .github/workflows/        CI
├── docs/                     numbered documentation folders; docs/api the generated API reference; docs/assets screenshots and design mockups
├── deploy/                   reserved for the deployment kit (Helm, Terraform, upgrade tool)
└── src/
    ├── package.json          npm workspace root (apps/* and packages/*), one lock file
    ├── backend/              Python (FastAPI): one package, `northcx/`. `server.py` builds the app (setup, middleware, shared helpers); `api/routers/` has one module per area of routes (132 routes in 21 modules), `api/models.py` the request bodies, `api/deps.py` the shared-dependencies object; `db/stores/` has the Postgres stores in nine domain modules; runtime, supervision, safety and channels are beside them
    ├── apps/
    │   ├── studio/           the operator console (Next.js), growing into the Admin app; its Dockerfile builds from `src/`
    │   └── workspace/        the staff Workspace (Next.js); early, unfinished work; no Dockerfile yet
    ├── packages/
    │   ├── ui/               shared components: states, badges, trace timeline, answer charts
    │   └── api-client/       typed API client, session and role helpers, loading hook
    ├── sdk/                  browser SDK and `<northcx-chat>` widget (TypeScript, no runtime dependencies; its own lock file)
    └── prototype/            TypeScript reference implementation of the runtime semantics
```
One-way dependencies: `apps/studio` and `apps/workspace` use `packages/ui` and `packages/api-client`; `packages/ui` uses `packages/api-client`; nothing uses an app. Run it with `cd src && npm ci && npm run dev`; test with `npm test`; build with `npm run build`.

## Target layout (planned in `12-project/NorthCX_Gap-Closure-Plan.md`, items E0.7 and E0.8)
```
src/
├── backend/                  unchanged: one Python package, scaled by replicas and background workers
├── apps/                     one Next.js app per audience, each its own image
│   ├── studio/               operator console (built)
│   ├── workspace/            staff Workspace (early work exists)
│   │                         (decided 2026-11-09: the Admin app is the Studio extended, not a separate `admin/` app)
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
`NOTICE`, `THIRD_PARTY.md` and `third_party/<source>/` hold attribution and provenance for copied code (see the Code Reuse Policy). No code is copied today, so `third_party/` does not exist. Adapted files live in the owning module and carry attribution headers.

## Conventions
Backend in Python with typed models and pytest; web apps in strict TypeScript; no network in unit tests; every route that needs a key appears in the generated route reference; every setting appears in the Deployment Guide and `.env.example`.
