# Contributing to NorthCX

1. Fork and branch from the default branch.
2. Backend: lint, type-check and `pytest` must pass. Web: lint, type-check and tests must pass.
3. Add tests for behaviour changes; production failures need a regression scenario.
4. Behaviour changes need a scenario (`src/backend/examples/scenarios`) as well as unit tests; run `python -m northcx.simulation` as shown in the Simulation doc.
5. Keep external product research in `docs/00-reference/` only.
6. Update the affected docs and the decision log in the same pull request.
7. Describe what changed and why; link any related doc.

Code style: typed Python for the backend, strict TypeScript for the web platform, no network in unit tests.
Contributions are licensed under Apache-2.0 and signed off with the Developer Certificate of Origin (`git commit -s`); this is provisional until the owner confirms (see the Licenses document).
