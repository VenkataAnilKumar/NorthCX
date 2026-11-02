# Contributing to NorthCX

1. Fork and branch from the default branch.
2. Backend: lint, type-check and `pytest` must pass. Web: lint, type-check and tests must pass.
3. Add tests for behaviour changes; production failures need a regression scenario.
4. Keep external product research in `docs/00-reference/` only.
5. Update the affected docs and the decision log in the same pull request.
6. Describe what changed and why; link any related doc.

Code style: typed Python for the backend, strict TypeScript for the web platform, no network in unit tests.
Contribution agreement (DCO or CLA) is undecided.
