# NorthCX Licences

Status: **Reference**. Updated: 2026-11-09. Master for: licence rules for dependencies and copied code. Dependency-specific licence findings are in `00-reference/NorthCX_Reference.md`.

## Policy
- NorthCX core: Apache-2.0 (`LICENSE` at the repository root).
- Core dependencies must be Apache-2.0, MIT, BSD or equivalent.
- Source-available or restricted licences (including enterprise directories of open projects) are never copied or bundled.
- Directories under separate commercial terms in otherwise open projects are not used.

## Copied code
Code reuse is governed by `08-governance-safety/NorthCX_Code-Reuse-Policy.md`. Verified licences of the reference repositories are in the Reference (section 10). Restricted directories and source-available licences are never copied.

## Process
1. Record licence and version for every new dependency.
2. Check transitive licences in CI.
3. Review attribution and notice obligations before release.
4. Re-verify licences at each major upgrade.

## Dependency licence check (release candidate)
Run on the production dependencies at 1.0.0-rc.1.

| Part | Result |
|---|---|
| Backend (74 Python packages) | permissive only: MIT, BSD, Apache-2.0, PSF, ISC-style; one weak-copyleft file-level licence (MPL-2.0, the CA certificate bundle `certifi`, used unmodified); no GPL, AGPL, SSPL or source-available licences |
| Studio (production npm packages) | MIT, Apache-2.0, ISC, BSD, 0BSD; `caniuse-lite` data is CC-BY-4.0 (attribution); one optional native image library from Next.js (`@img/sharp-libvips`, LGPL-3.0-or-later) that is dynamically loaded and not modified or redistributed by NorthCX source |
| Browser SDK | no runtime dependencies |
| PDF reading (`pypdf`, BSD-3-Clause) | added in the knowledge step; pure Python |
| Our own packages | declared Apache-2.0 in `pyproject.toml` and `package.json` |

Re-run before every release (`pip-licenses`, `npx license-checker --production`) and after dependency upgrades. Not yet re-run since: the Workspace app and the shared UI package (early work, merged 2026-11-09) and the hash-pinned backend lock files; run it before the next release. CI runs `pip-audit` (known vulnerabilities, not licences) on both backend lock files.

## Contributor agreement
Provisionally the Developer Certificate of Origin (`Signed-off-by` on commits, described in `CONTRIBUTING.md`) rather than a CLA: it needs no paperwork and matches Apache-2.0 practice. The owner can change this before 1.0.0.
