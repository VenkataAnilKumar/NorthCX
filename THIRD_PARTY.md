# Third-Party Code

Provenance of code copied or adapted from other projects. Policy: `docs/08-governance-safety/NorthCX_Code-Reuse-Policy.md`.

**Current state: no third-party source code is copied or adapted into NorthCX, and the product has no dependency on any reference project's SDK or library.** Copying and rebranding reference code is allowed under the policy (decision 199: permissive licences read from the project's own LICENSE file, the licences kept in one folder per source, no dependency on the source), but nothing is copied at the moment. The third-party packages the product installs are ordinary infrastructure libraries (web server, database driver, HTTP client, YAML, and the web framework), listed in `src/backend/pyproject.toml` and the `package.json` files under `src` (`apps/studio`, `packages/*`, `sdk`), and, by the owner's named exception to decision 199 (decision 200), the official MCP Python SDK: `mcp` and `mcp-types` (MIT) with `jsonschema`, `jsonschema-specifications`, `referencing`, `rpds-py`, `attrs` and `pyjwt` (MIT), `python-multipart` (Apache-2.0) and `sse-starlette` (BSD-3-Clause); `pywin32` is pulled in only on Windows. Licences were read from each package's published metadata on 2026-11-19.

History: two small input-screening files were once adapted from a reference project under Apache-2.0. They were rewritten from scratch in NorthCX style (`northcx/safety/pii.py`, `northcx/safety/prompt_injection.py`) and the copied originals and their licence file were removed from the repository.

## Copied or adapted
None yet. Each project gets one line here, "Adapted from <owner>/<project> (<licence>)", pointing to `third_party/<source>/`, which holds its LICENSE (and NOTICE) file. Individual files and features are not listed. Add it in the same pull request as the copy.

## Assessed and not copied
| Source | Module | Reason |
|---|---|---|
| agno-agi/agno | `agno/approval`, `agno/agent` | Tightly coupled to Agno's own tool, run and HITL types (the agent package alone is about 21,000 lines); NorthCX keeps its own small runtime, whose semantics are specified and tested |
| simstudioai/sim | `apps/sim` (web app: `components`, `stores`, `executor`, `app/workspace`) | shallow clone, 2026-11-02 | Apache-2.0 (root); `apps/sim/ee` excluded | Roughly 21,000 files in one product, wired to its own database layer, authentication, billing and a workspace package (`@sim/emcn`) that its UI components import. Nothing copied; the NorthCX web app is written natively in the same stack (Next.js, React, Tailwind) following the Studio spec |
| onyx-dot-app/onyx | `backend/onyx/indexing/chunker.py` and `chunking/` | Licence verified 2026-11-03 from the repository LICENSE (MIT outside `ee` directories; commit 332b908f). The chunker depends on Onyx's configuration, tokenizer, connector and document models and a third-party sentence-splitting package; the useful idea (split by section, keep a small heading/metadata prefix, no overlap) is small. Nothing copied; NorthCX writes its own heading-aware chunker |
| langfuse/langfuse | `packages/shared/src/server/ingestion/types.ts`, `web/src/pages/api/public/ingestion.ts` | Licence verified 2026-11-03 from the repository LICENSE (MIT outside `ee` directories; commit 0ca8994b). Read only to learn the public ingestion API contract (batch of typed events, basic authentication); no code copied. NorthCX writes its own client in `northcx/trace_export.py` |
