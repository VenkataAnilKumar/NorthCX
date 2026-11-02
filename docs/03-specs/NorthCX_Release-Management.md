# NorthCX Release Management Spec

Status: Draft. Catalog IDs Q8-Q11. Phase 2 (versions, rollback), Phase 3 (environments), Phase 4 (rollout).

## Why
Agent behaviour changes whenever instructions, tools, policies or knowledge change. Each change must be reviewable, testable and reversible.

## Concepts
| Term | Definition |
|---|---|
| Agent version | Immutable snapshot of instructions, tools, guardrails, model settings |
| Release | A version published to an environment |
| Environment | dev, staging, production |
| Required scenarios | Simulations that must pass before promotion |
| Rollout | Share of traffic served by a version |

## Behaviour
1. Saving a definition creates a new version with author, time and change note.
2. Diff shows changes between versions.
3. Promotion to an environment runs required scenarios; failure blocks promotion.
4. Production promotion may require a reviewer approval.
5. Rollback republishes a prior version in one step and is audited.
6. Staged rollout sends a configured percentage to the new version; metrics compare versions; promote or revert.
7. A change to knowledge or policy triggers a simulation re-run.

## Data
`agent_versions`, `releases`, `environments` (see Database-Schema).

## API sketch
`POST /v1/agents/:id/versions`, `GET /v1/agents/:id/versions`, `POST /v1/agents/:id/releases {version, environment}`, `POST /v1/agents/:id/rollback {environment, toVersion}`.

## Acceptance
- A version cannot be modified after creation.
- A failing required scenario blocks promotion.
- Rollback restores the exact prior behaviour and is recorded.
- Every release shows who, when, what changed and test results.


## As built (Phase 2, sprint 10)

**Versions.** `POST /v1/agents/{id}/versions` saves a spec (as JSON, as YAML text, or `fromBaseline` to snapshot the spec file) as the next version number. Versions are immutable. Saving validates the spec against the tool and guardrail registry, including guardrail configuration; a spec whose `id` differs from the agent, or that is identical to the latest version, is refused. Going back to older content is allowed and becomes a new version. Numbers are gapless and unique, also under concurrent saves. `GET /v1/agents/{id}/versions[/{n}]` lists and reads them (with `live` and `everReleased` flags and the YAML), and `GET .../versions/{a}/diff/{b}` returns a reviewable diff: a unified diff of the instructions, tools added and removed, guardrails and always-to-a-person topics added, removed or changed, and other fields.

**Proving a version.** `POST /v1/simulations/runs` with `agent` and `version` runs that agent's scenarios against that exact spec and records its digest. `GET /v1/simulations/gate?agent=&version=` reports whether that version satisfies the release gate.

**Publishing.** `POST /v1/agents/{id}/releases` with `{version, by, note}` publishes only if the gate is satisfied for that version's digest; otherwise it answers 409 `gate_not_satisfied` with the list of reasons. A proof for one version never releases another, and a version that is already live cannot be published again. If simulations are not configured, nothing can be published. Each release records who, when, the note, the previous version, and a snapshot of the gate (scenarios covered and the runs that proved them).

**Serving.** The server resolves the agent for every chat through the release store: the live version's spec is built into an agent (cached by version) and serves immediately. Until something is released, the agent from the spec file (the baseline) serves. Because the lookup reads the release store on each request, a release or rollback takes effect for every server process at once. If the live version cannot be built (for example a tool it names was removed from the code), chat answers 503 `agent_unavailable` instead of guessing; rolling back is the way out.

**Rollback.** `POST /v1/agents/{id}/rollback` with `{by, note, toVersion?}` needs no gate, because it restores something that already ran in production. Without `toVersion` it undoes the last change: the previous distinct live version, or the spec file if the first release is withdrawn; rolling back a rollback goes forward again. With `toVersion` the version must have been live before (otherwise it must be published, which needs the gate). Rollback is recorded in the release history like any release.

**Traces.** Every trace and conversation row records the agent version that answered (`agentVersion`; null means the spec file), so a bad answer can be tied to the release that produced it.

**Web.** Agents lists what is live; each agent has a versions page to save a new version from an editable YAML spec (starting from what is live), run the scenarios for one version, see its gate, publish, view the spec or its changes from live, roll back, and read the release history.

**Behaviour to know about.**
- A conversation in progress continues with whatever version is live when the next message arrives; it is not pinned to the version it started on.
- An approval resolved after a release or rollback is executed and described by the live agent, which re-validates the held input and re-checks supervisors.
- There is one environment, `production`. Dev and staging, promotion between them, and staged rollout are Phase 3 and 4.
- Publishing and rolling back need the release manager or admin role; the release records the key's name (a typed name is only used in open mode), and every attempt, including those blocked by the gate, is in the audit log.
