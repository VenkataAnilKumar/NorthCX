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
