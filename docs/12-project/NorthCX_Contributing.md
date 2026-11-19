# Contributing to NorthCX

Status: **Reference**. Updated: 2026-11-19. Master for: how to contribute.

1. Fork and branch from the default branch.
2. What CI checks: backend `pytest` (with Postgres), the scripted scenario suite, `pip-audit` on both lock files and the restricted-path check; web `npm run typecheck`, `npm test` and `npm run build` (Studio, Workspace and the shared packages) and the SDK tests and build; and a Docker Compose smoke test. There is no linter or backend type checker in CI yet.
3. Add tests for behaviour changes; production failures need a regression scenario.
4. Behaviour changes need a scenario (`src/backend/examples/scenarios`) as well as unit tests; run `python -m northcx.simulation` as shown in the Simulation doc.
5. Keep external product research in `docs/00-reference/` only. Reference code may be copied and rebranded but never depended on; the rules are in `CONTRIBUTING.md` (item 4) and `../08-governance-safety/NorthCX_Code-Reuse-Policy.md`.
6. Update the affected docs and the decision log in the same pull request.
7. Describe what changed and why; link any related doc.

Code style: typed Python for the backend, strict TypeScript for the web platform, no network in unit tests.
Contributions are licensed under Apache-2.0 and signed off with the Developer Certificate of Origin (`git commit -s`); this is provisional until the owner confirms (see the Licenses document).
