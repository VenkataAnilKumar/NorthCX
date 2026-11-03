# NorthCX Code Reuse Policy

Status: Draft. Decision: NorthCX is assembled by fetching reference repositories and copying or adapting the code that implements our features, instead of writing everything from scratch. Source repositories, paths and licences are in `00-reference/NorthCX_Reference.md` (sections 10 and 11).

## Principles
1. Reuse before build: a capability is copied or adapted when a licensed source implements it well.
2. Provenance always: every copied file can be traced to its source repository, path, commit and licence.
3. Licence first: only code under permissive licences is copied; restricted directories are never copied.
4. Adapt to our model: copied code is wired to NorthCX interfaces (agent definition, tools, stores, traces) rather than kept as a foreign island.
5. Keep upgrades possible: record the upstream commit so changes can be compared and merged.

## What may be copied
| Licence | Allowed | Obligations |
|---|---|---|
| Apache-2.0 | Yes | Keep licence and copyright notices; state changes in modified files; include the NOTICE content where the source has one |
| MIT | Yes | Keep copyright and permission notice |
| BSD-2-Clause | Yes | Keep copyright notice and conditions |
| Source-available or restricted (for example Elastic License 2.0) | No | |
| Enterprise or `ee` directories in otherwise open projects | No | Separate commercial licence |
| Unknown or missing licence | No | Until clarified |

## Process
1. **Select:** name the feature (catalog ID) and the candidate source path.
2. **Check licence:** confirm the file's licence, including directory-level licences and third-party notices.
3. **Assess fit:** read the code; record dependencies it drags in, size, and tests available.
4. **Import:** copy into `third_party/<source>/` or directly into the owning module, preserving headers.
5. **Record:** add an entry to `THIRD_PARTY.md` (source, path, commit, licence, files, local changes) and update `NOTICE`.
6. **Adapt:** wire to NorthCX interfaces; keep changes in separate commits so upstream diffs remain readable.
7. **Test:** port or write tests; the feature must pass its scenarios.
8. **Review:** a second person confirms licence handling.

## Repository layout for reuse
```
NOTICE                    attribution for copied code
THIRD_PARTY.md            provenance table (source, path, commit, licence, local changes)
third_party/<source>/     unmodified or lightly modified imports with original licence files
```

## Do not
- Copy files from `ee` or `enterprise` directories or from any restricted licence.
- Strip licence headers or copyright lines.
- Copy generated, vendored or large binary assets without checking their licences.
- Merge code whose licence is incompatible with the NorthCX licence (to be decided).

## Compatibility with the NorthCX licence
Apache-2.0, MIT and BSD code can be included in an Apache-2.0 project. The project licence is still undecided; confirm this policy against the final choice.

## Risks
| Risk | Mitigation |
|---|---|
| Missed restricted directory | Path allow-list in CI; licence scanner |
| Transitive dependencies with other licences | Dependency licence scan in CI |
| Divergence from upstream | Record upstream commits; isolate local changes |
| Mixed languages complicate the build | Decide the backend language before copying (see Decision Log) |
| Code quality or security issues inherited | Review, tests and scans on every import |


## Current rule
- **Copying or adapting reference code for a feature is allowed**, under the licence rules above: permissive licences only (MIT, Apache-2.0, BSD), never from `ee`/enterprise directories or from projects under restrictive licences, with the licence kept, an attribution header in each file and an entry in `THIRD_PARTY.md`. Adapted code lives inside NorthCX's own source tree under `src/` and follows NorthCX naming and structure.
- **NorthCX never depends on a reference project's SDK or library.** Nothing in the product imports or installs a reference project's package, and no reference project is a runtime service the product needs. If a feature is wanted from a reference project, its code is copied and adapted, or the idea is rewritten; the project itself is not added as a dependency.
- Ordinary infrastructure libraries (web server, database driver, YAML, the web framework) are dependencies, not references, and are listed in the package manifests.
- State today: no third-party source code is currently copied. The two small guardrails that were once adapted were rewritten independently (a fresh implementation is fine, and so would an adapted copy have been); the earlier copies were removed.
