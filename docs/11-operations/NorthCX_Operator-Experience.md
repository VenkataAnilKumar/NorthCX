# Operator experience: install, upgrade, backup, health, sign-in, resolution (Phase 6)

Status: stages 1 to 4 written 2026-11-22. **WP 6.5 (O7) WP 6.3 (O4, O5) and WP 6.2 (O3) are built**; the plan's progress table says which work package is. Master for: Phase 6 of `../12-project/NorthCX_Agent-Platform-Plan.md`. Part of `../00-platform/NorthCX_Agent-Platform-Design.md` (a missing area: what decides whether a self-hosted customer keeps running NorthCX).

## 1. Research: what exists today
Read in this repository on 2026-11-22.
- **Install:** copy `.env.example` to `.env`, fill in the REQUIRED values by hand (database password, API key), then `docker compose up -d --build --wait`. The compose file refuses to start without both (`${VAR:?...}`), and the CI `stack` job writes its own `.env` with a shell script, so the written steps and the tested steps differ. A person must invent passwords and know which model settings exist.
- **Sign-in:** the compose backend sets `NORTHCX_REQUIRE_AUTH=1` and the server exits if no API key exists (`bootstrap/security.py`). So "the stack refuses to start open" is already true; there is no test that proves it for the compose path.
- **Migrations:** Alembic, 58 revisions, applied on start; `migrate(url, revision)` can stop at a revision. Tests apply, roll back and reapply from nothing and check the models match the migrations. No test upgrades a database that already holds data.
- **Release candidate 1.0.0-rc.1** was cut on 2026-11-03. This checkout has no tag for it and its history is squashed, so the exact schema revision it shipped cannot be read here.
- **Backup:** the deployment guide says "back up the Postgres volume or use `pg_dump`". Everything the product stores (conversations, approvals, versions, keys, outputs, files, sealed secrets) is in the one database. There is no command and no restore drill.
- **Health:** `GET /health` (alive) and `GET /ready` (the stores answer), both public and answering only yes or no. `/v1/admin/overview` and `/v1/alerts` show parts of the picture. Nothing shows migrations, model reachability, channels or alert delivery in one place.
- **Resolution figure** (`insights.resolution`): a conversation counts as resolved when its last turn completed, it never reached a person, and it stayed quiet for three days. A customer who returns in a new conversation is not detected, so the figure can overstate. `privacy.link(session, customer)` already records which customer a session belongs to.
- `docker`, `pg_dump` and `pg_restore` are available in the development container, so the drills can run here.

## 2. Requirements
| ID | For whom | Requirement | Acceptance check |
|---|---|---|---|
| O1 | An operator | One command writes a working `.env`: generates the database password, API key and token secret, asks (or takes flags) for demo or real, and which model (a cloud key, a local server address, or none), refuses to overwrite an existing file, and prints the next command | A test runs it with flags and loads the result through `docker compose config`; CI starts the stack from a generated file instead of a hand-written one |
| O2 | An operator | The time from a fresh clone to a running agent is measured | The CI `stack` job prints the seconds from `docker compose up` to the first answer; the number is recorded in the plan once measured on CI (no figure is claimed before) |
| O3 | An operator upgrading | A database created by an earlier version and holding data upgrades to the current one without losing rows | A test creates the schema at several earlier revisions, inserts rows, upgrades to the newest and reads the rows back through the current stores; it runs in CI |
| O4 | An operator | `python -m northcx backup` writes one file holding the whole database, with a record of when, the migration revision and a checksum | A test backs up a database that holds data |
| O5 | An operator | `python -m northcx restore` puts a backup into an empty database, refuses a corrupt file or a backup newer than the code, refuses a database that already has data unless told to replace it, and brings it to the current revision | A restore drill: back up, restore into a new database, compare row counts of every table and read a conversation back |
| O6 | An operator | A health page shows: database, migrations (current and expected), each model provider, each enabled channel, and the alert webhook's last delivery, each ok, failing or not set up, with what to do | A browser test; component tests for each state; the route needs the operator permission and shows no secret or address with credentials |
| O7 | An operator | The compose stack does not start without sign-in | A test starts the server with `NORTHCX_REQUIRE_AUTH=1` and no key and sees it exit with the instruction; the compose file is checked to set it |
| O8 | A CX lead | The resolution figure counts a customer who comes back (a new conversation by the same customer within the window) as not resolved, and the page shows the old and the new figure each with its denominator | Tests with returning and non-returning customers; the old figure is unchanged |

## 3. Design
- **Wizard (O1).** `scripts/setup.py`, standard library only, so it runs before anything is installed. Flags: `--demo`, `--anthropic-key`, `--local-model-url`, `--force`, `--non-interactive`. Secrets come from `secrets.token_urlsafe`; the file is created with mode 600. It writes only the settings that exist in `.env.example`, and a test fails if it writes one that does not. Interactive questions are the same flags asked in plain words.
- **Backup (O4, O5).** Built without Postgres client tools, because the backend image is `python:3.12-slim` and a `pg_dump` older than the server refuses to run: `northcx.ops.backup` reads every table in one repeatable-read snapshot with the driver's binary COPY. The file is a tar of `manifest.json` (time, schema revision, row count and SHA-256 per table) and one dump per table. Restore verifies every checksum first, refuses a newer backup or a non-empty database (without `--replace`), rebuilds the schema at the backup's revision, empties what the migrations seeded, loads the tables in foreign-key order (the audit log's append-only trigger is off only inside that one transaction), resets the counters and upgrades to the newest revision. It uses the migration (owner) URL when one is set, since row-level security would hide rows from the server's own role. The password never appears in output. `knowledge_embeddings` (made on demand, derived) is not saved.
- **Upgrade test (O3).** `tests/test_upgrade.py` uses `migrate(url, revision)` to build the schema at seven earlier revisions (0001, 0010, 0020, 0030, 0041, 0050, 0057), puts one row in every table that exists at that revision (made from column types; constraints between tables are off only while seeding), upgrades to the newest, checks no table lost a row or went missing and that the upgraded schema has no difference from the code's models (the check fails when a column is added by hand), and takes a conversation through the current stores. It runs in the normal backend CI job.
- **Health (O6).** `GET /v1/system/health` returns a list of checks `{name, status, detail, action}`; status is ok, failing or not_set_up. Checks: database (a query), migrations (stored revision against the newest in the code), providers (the existing provider listing and, for each, whether the last call succeeded, never a new model call), channels (configured or not, last inbound or outbound error where recorded), alert delivery (last event's delivery status). Studio gets a System health page under Platform. No check makes a model call or sends anything.
- **Sign-in (O7).** Already built; adds the proving tests and keeps the compose line.
- **Resolution (O8).** `resolution` takes the session-to-customer links. A resolved session is reopened when another session of the same customer starts after its last turn and within the window. The new figure is `resolvedFirm`; `resolutionRate` keeps its meaning so nothing that reads it changes. Customer links are read through `privacy`, so erasure removes them (no new store).

## 4. Architecture
- `scripts/setup.py` (new, stdlib only); `.github/workflows/ci.yml` uses it for the stack job and prints the time to first answer.
- `northcx/ops/` (new): `backup.py` (backup, restore, manifest) and `__main__` subcommands `backup` and `restore`; documented in the deployment guide.
- `northcx/api/routers/system.py` (new): `GET /v1/system/health`, permission `admin:read`-class (the same as the admin overview); added to the route-permission table, the route golden and the API reference. Additive.
- `apps/studio/app/system/page.tsx` (new) and a nav entry under Platform.
- `northcx/insights.py` and `privacy.py`: customer links into `resolution`; the insights response gains `resolutionFirm`.
- No new dependency (`pg_dump` and `pg_restore` are in the Postgres client tools already in the backend image; the Dockerfile is checked for them), no migration.

## 5. Order of work
| Order | WP | Why here |
|---|---|---|
| 1 | 6.5 | Smallest: tests for what exists |
| 2 | 6.3 | The restore drill also supplies the data fixture for 6.2 |
| 3 | 6.2 | Uses the drill's data helpers |
| 4 | 6.1 | Wizard, then CI switches to it (and measures the time, O2) |
| 5 | 6.4 | Health route and page |
| 6 | 6.6 | Independent; last because it changes a figure people read |

## 6. Known limits
- **The previous release's exact schema revision is unknown here,** so O3 proves upgrades from several earlier revisions, not "from rc.1" by name. When the tag is available to a machine that has it, add its revision to the list.
- **The wizard has not been used by a person who is not an engineer.** Its time and clarity are unmeasured (the usability gate in `../02-studio/NorthCX_Usability-Gate.md` covers Studio, not install).
- **Backups include personal data** (conversations). The file is not encrypted by NorthCX; the guide says to store it where the database's own protections apply.
