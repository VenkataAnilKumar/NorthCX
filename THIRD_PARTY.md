# Third-Party Code

Provenance of code copied or adapted from other projects. Policy: `docs/05-technical/NorthCX_Code-Reuse-Policy.md`.

| Source | Source path | Upstream commit | Licence | NorthCX file | Local changes |
|---|---|---|---|---|---|
| agno-agi/agno | `libs/agno/agno/guardrails/pii.py` | b21807bb6d86d2a62efeb42d492c04e566ee7f90 | Apache-2.0 | `src/backend/northcx/safety/pii.py` | Rewritten to the async `InputGuardrail` interface and a result object instead of exceptions; credit cards use the Luhn check; phone pattern requires separators so plain order numbers are not flagged |
| agno-agi/agno | `libs/agno/agno/guardrails/prompt_injection.py` | b21807bb6d86d2a62efeb42d492c04e566ee7f90 | Apache-2.0 | `src/backend/northcx/safety/prompt_injection.py` | Rewritten to the async `InputGuardrail` interface; pattern list unchanged |

Unmodified originals for diffing are kept in `third_party/agno/original/` with the upstream `LICENSE` in `third_party/agno/LICENSE`.

## Assessed and not copied
| Source | Module | Reason |
|---|---|---|
| agno-agi/agno | `agno/approval`, `agno/agent` | Tightly coupled to Agno's own tool, run and HITL types (the agent package alone is about 21,000 lines); NorthCX keeps its own small runtime, whose semantics are specified and tested |
| simstudioai/sim | `apps/sim` (web app: `components`, `stores`, `executor`, `app/workspace`) | shallow clone, 2026-11-02 | Apache-2.0 (root); `apps/sim/ee` excluded | Roughly 21,000 files in one product, wired to its own database layer, authentication, billing and a workspace package (`@sim/emcn`) that its UI components import. Nothing copied; the NorthCX web app is written natively in the same stack (Next.js, React, Tailwind) following the Studio spec |
| onyx-dot-app/onyx | `backend/onyx/indexing/chunker.py` and `chunking/` | Licence verified 2026-11-03 from the repository LICENSE (MIT outside `ee` directories; commit 332b908f). The chunker depends on Onyx's configuration, tokenizer, connector and document models and a third-party sentence-splitting package; the useful idea (split by section, keep a small heading/metadata prefix, no overlap) is small. Nothing copied; NorthCX writes its own heading-aware chunker |
| langfuse/langfuse | `packages/shared/src/server/ingestion/types.ts`, `web/src/pages/api/public/ingestion.ts` | Licence verified 2026-11-03 from the repository LICENSE (MIT outside `ee` directories; commit 0ca8994b). Read only to learn the public ingestion API contract (batch of typed events, basic authentication); no code copied. NorthCX writes its own client in `northcx/trace_export.py` |
