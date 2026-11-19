# Contributing to NorthCX

Thank you for helping. This page is the short version; the long one is [`docs/12-project/NorthCX_Contributing.md`](docs/12-project/NorthCX_Contributing.md).

## Set up
```bash
cd src/backend && python -m venv .venv && . .venv/bin/activate && pip install --require-hashes -r requirements-dev.lock && pip install --no-deps -e .
NORTHCX_REQUIRE_DB=1 python -m pytest        # needs Postgres 16 (docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres)
cd .. && npm ci && npm run typecheck && npm test   # the web workspace in src/: Studio, Workspace and the shared packages
cd sdk && npm ci && npm test              # then `npm run build` if you changed src/sdk/src: the built bundle is committed and a test checks it
```
Browser checks: `src/apps/studio/e2e/smoke.mjs`, `src/apps/workspace/e2e/smoke.mjs` (early work; not yet passing in full) and `src/sdk/e2e/smoke.mjs` (see the deployment guide).

## What a good change looks like
1. **Tests first-class.** Behaviour changes come with tests; a bug fix comes with a test that failed before. A change to what an agent does comes with a scenario in `src/backend/examples/scenarios`. No network in unit tests.
2. **Docs in the same change.** Update the affected document, the Feature Catalog status, and add a line to the decision log for any decision a reader would otherwise have to guess. Settings must be in `docker-compose.yml`, `.env.example` and the deployment guide (a test enforces it).
3. **Security by default.** New endpoints need an entry in the route permission table (a test fails otherwise); new outbound calls must not follow redirects; SQL values are always bound; anything a customer can influence is untrusted data. See `docs/08-governance-safety/NorthCX_Threat-Model.md`.
4. **Copy and rebrand, never depend.** Code from a reference project may be copied, renamed to NorthCX names and restyled, but nothing in NorthCX may import, install or call that project. Only code whose licence you read in the project's own LICENSE file, and that is MIT, Apache-2.0 or BSD, may be copied; never AGPL, GPL, source-available or custom licences, or `ee` and `enterprise` directories. Every copied file keeps its licence and copyright notice in an attribution header, with an entry in `THIRD_PARTY.md` in the same pull request (`docs/08-governance-safety/NorthCX_Code-Reuse-Policy.md`). Ordinary infrastructure libraries are fine. External research and product names belong in `docs/00-reference/` only.
5. **Small and explained.** Say what changed and why, and what you did not do.

## Sign your work
Add a `Signed-off-by: Your Name <you@example.com>` line to each commit (`git commit -s`). It certifies that you wrote the change or have the right to submit it under Apache-2.0 (the Developer Certificate of Origin, https://developercertificate.org). Contributions are licensed under Apache-2.0.

## Reporting problems
Bugs and ideas: open an issue. Security problems: follow [`SECURITY.md`](SECURITY.md), not a public issue.

## Conduct
Be kind and specific; see [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
