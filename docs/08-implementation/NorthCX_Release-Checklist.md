# NorthCX 1.0.0 Release Checklist

Status: working checklist. Items marked **you** need a person or a live model; the rest were verified from a clean clone of the repository.

## Verified from a clean checkout (no local state)
- [x] `pip install --require-hashes -r requirements-dev.lock && pip install --no-deps -e .` in `src/backend` succeeds; the full backend suite passes against local Postgres with pgvector (`NORTHCX_REQUIRE_DB=1`).
- [x] `src/sdk`: `npm ci`, tests and `npm run build` pass; the widget bundle is produced.
- [x] `src` (the web workspace: Studio and the shared packages): `npm ci`, type-check, tests and `next build` pass.
- [x] `docker compose config` is valid with the values from `.env.example` filled in; the stack uses `pgvector/pgvector:pg16`.
- [x] Every relative link in the Markdown documents resolves; every document is listed in `docs/README.md`.
- [x] Version numbers agree (`northcx.__version__`, web and SDK `package.json`) and `CHANGELOG.md` has an entry for the release (`tests/test_release.py` enforces this).
- Not verifiable in the build environment: pulling the Postgres image from Docker Hub (rate-limited) and building the application images (the sandbox's TLS interception is not trusted inside builds). Both worked earlier in the project's history; repeat on a normal machine: `docker compose up -d --build --wait`.

## Before tagging 1.0.0 (you)
- [ ] **Real-model pass.** With a Claude API key in `ANTHROPIC_API_KEY`: run the example agent through the web console; run the shipped scenarios in live mode (`python -m northcx.simulation`); try an agent draft, a journey draft, a plain-language analytics question and the judge model; if an embeddings service is available, check meaning-based search. Fix or document anything that differs from the scripted tests, and calibrate the judge (`Q3`).
- [ ] **Independent penetration test.** Give the tester the Threat Model and Security Review as scope; track findings in `SECURITY.md`'s process; re-run the standing security tests after fixes.
- [ ] **Compose on a normal machine.** `docker compose up -d --build --wait`, then the five-minute demo in the README, then a restart to confirm data persists.
- [ ] **Decide the open licence and ownership details**: the project is Apache-2.0; confirm `NOTICE` and `THIRD_PARTY.md` are current (they state that no third-party source is copied).
- [ ] **Publish the release candidate tag** `v1.0.0-rc.1` (it exists only in the session checkout; push it from a machine with access) and let it soak.

## Cutting 1.0.0 (after the above)
1. Set the version to `1.0.0` in `src/backend/northcx/__init__.py`, every `package.json` under `src` (workspace root, `apps/*`, `packages/*`, `sdk`) (and their lock files).
2. Move the `[Unreleased]` section of `CHANGELOG.md` under `[1.0.0]` with the date; update the status line in `README.md`.
3. Run the whole suite (`tests/test_release.py` checks the versions agree), build the images, tag `v1.0.0`, and publish the release notes from the changelog.

## Known limits to state in the release notes
- The real-model path has been exercised with scripted and offline models only until the real-model pass is done.
- No independent penetration test until that is done.
- One region per deployment; no multi-tenancy, metering or billing.
- Not built: sending media or buttons on messaging channels, automatic template fall-back, Telegram groups, Office files in the website crawler, analytics groupings and forecasts, speaker separation in recordings.
