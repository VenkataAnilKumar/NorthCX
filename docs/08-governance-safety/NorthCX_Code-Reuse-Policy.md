# NorthCX Code Reuse Policy

Status: **Reference**. Updated: 2026-11-19. Master for: the code reuse policy (in force). Copying and rebranding permissively licensed reference code is the normal way to use a reference when its code fits, with full provenance and no dependency on the source project (owner's decision of 2026-11-19, section "Copy and rebrand, never depend"). Nothing has been copied yet; see `NOTICE` and `THIRD_PARTY.md`.

## Copy and rebrand, never depend (decision 199, 2026-11-19)
The owner decided that code from reference projects may be copied and rebranded for NorthCX, and that NorthCX must never depend on those projects.

- **Rebrand means** renaming to NorthCX names and structure, restyling screens with the NorthCX design system, and removing the source project's product name, logo and marketing text from anything a user sees. It does **not** mean removing the licence and copyright notices. Apache-2.0, MIT and BSD all require them to stay, so they are kept in one place (the next point) and are never deleted from where they already are. CI already checks that `THIRD_PARTY.md`, `NOTICE` and `LICENSE` exist and that no `ee` or `enterprise` path is committed.
- **No dependency means** nothing in NorthCX imports, installs, vendors as a submodule, or calls a reference project as a package, a hosted API or a service it needs to run. Copied code lives in NorthCX's own `src/` tree and is changed until it stands alone. The only packages NorthCX installs are ordinary infrastructure libraries (web server, database driver, YAML, HTTP client, the web framework), which stay listed in the package manifests; adopting a library such as an MCP SDK or a canvas library is a dependency decision recorded in the decision log, not a copy.
- **Licences live in one folder per source project, `third_party/<source>/`, not in every copied file.** It holds the project's LICENSE file verbatim and its NOTICE file if it has one, and it is created in the same change as the first copy. `THIRD_PARTY.md` gets one line for the project: "Adapted from <owner>/<project> (<licence>)", pointing to the folder. Nothing lists individual files or features. Two things stay: a notice that is already inside a source file is not deleted, and a file copied from an **Apache-2.0** project gets one short line, for example `// Modified from <project> (Apache-2.0); see third_party/<source>/`, because that licence requires modified files to say they were changed. MIT and BSD files need nothing beyond the folder. CI already fails a `third_party/<source>/` folder that has no licence file.
- **Which sources.** Only code whose licence was read from the project's own LICENSE file at the commit being copied, and only if that licence is on the allowed list below. Licences named in blog posts or comparisons do not count. Not copyable, whatever the project's popularity: AGPL and GPL code (it cannot be distributed inside an Apache-2.0 project), source-available or custom licences (for example the Elastic License, n8n's Sustainable Use License, Dify's licence, LobeHub's community licence, Open WebUI's branding clause), anything under `ee` or `enterprise` directories, and anything with no licence. Buying a commercial licence from a project would be a separate written agreement recorded in `THIRD_PARTY.md`; none exists.
- **Quality bar applies to copied code.** Copy only what NorthCX uses and delete the rest of the file; copied code carries the same tests, no dead code and no foreign naming as anything else (see `CLAUDE.md`). A copied component that drags in a dependency is rewritten to use NorthCX's own parts or not copied.

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
4. **Import:** put the project's LICENSE (and NOTICE) file into `third_party/<source>/`, and the code into the owning module under `src/`.
5. **Record:** add the project's "Adapted from" line to `THIRD_PARTY.md`, and update `NOTICE` if the source has a NOTICE file.
6. **Adapt:** wire to NorthCX interfaces; keep changes in separate commits so upstream diffs remain readable.
7. **Test:** port or write tests; the feature must pass its scenarios.
8. **Review:** a second person confirms licence handling.

## Repository layout for reuse
```
NOTICE                    attribution for copied code
THIRD_PARTY.md            provenance table (source, path, commit, licence, local changes)
third_party/<source>/     LICENSE and NOTICE verbatim; the copied code lives under src/
```

## Do not
- Copy files from `ee` or `enterprise` directories or from any restricted licence.
- Delete a licence or copyright notice that is already inside a source file, or leave out the folder that holds the licences.
- Copy generated, vendored or large binary assets without checking their licences.
- Merge code whose licence is incompatible with the NorthCX licence (Apache-2.0).

## Compatibility with the NorthCX licence
Apache-2.0, MIT and BSD code can be included in an Apache-2.0 project. NorthCX is licensed under Apache-2.0 (`LICENSE`).

## Risks
| Risk | Mitigation |
|---|---|
| Missed restricted directory | Path allow-list in CI; licence scanner |
| Transitive dependencies with other licences | Dependency licence scan in CI |
| Divergence from upstream | Record upstream commits; isolate local changes |
| Mixed languages complicate the build | Backend language decided: Python (Decision Log #3) |
| Code quality or security issues inherited | Review, tests and scans on every import |


## Current rule
- **Copying or adapting reference code for a feature is allowed**, under the licence rules above: permissive licences only (MIT, Apache-2.0, BSD), never from `ee`/enterprise directories or from projects under restrictive licences, with the licences kept in `third_party/<source>/` and a line in `THIRD_PARTY.md`. Adapted code lives inside NorthCX's own source tree under `src/` and follows NorthCX naming and structure.
- **NorthCX never depends on a reference project's SDK or library.** Nothing in the product imports or installs a reference project's package, and no reference project is a runtime service the product needs. If a feature is wanted from a reference project, its code is copied and adapted, or the idea is rewritten; the project itself is not added as a dependency.
- Ordinary infrastructure libraries (web server, database driver, YAML, the web framework) are dependencies, not references, and are listed in the package manifests.
- **One named exception (owner, 2026-11-19, decision 200): the official MCP Python SDK (`mcp`, MIT).** It is both a reference source and the maintained implementation of a protocol NorthCX must speak, and it tracks the specification as it changes. It is a pinned dependency, imported by one module only (`northcx/mcp_client.py`) so it can be replaced, and its licence and its dependencies' licences were read (`THIRD_PARTY.md`). The exception covers that package; it is not a precedent for any other reference project.
- State today (2026-11-19): no third-party source code is currently copied. The two small guardrails that were once adapted were rewritten independently (a fresh implementation is fine, and so would an adapted copy have been); the earlier copies were removed.
