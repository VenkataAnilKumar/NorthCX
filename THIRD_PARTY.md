# Third-Party Code

Provenance of code copied or adapted from other projects. Policy: `docs/05-technical/NorthCX_Code-Reuse-Policy.md`.

| Source | Source path | Upstream commit | Licence | NorthCX file | Local changes |
|---|---|---|---|---|---|
| agno-agi/agno | `libs/agno/agno/guardrails/pii.py` | b21807bb6d86d2a62efeb42d492c04e566ee7f90 | Apache-2.0 | `src/backend/northcx/safety/pii.py` | Rewritten to the async `InputGuardrail` interface and a result object instead of exceptions; credit cards use the Luhn check; phone pattern requires separators so plain order numbers are not flagged |
| agno-agi/agno | `libs/agno/agno/guardrails/prompt_injection.py` | b21807bb6d86d2a62efeb42d492c04e566ee7f90 | Apache-2.0 | `src/backend/northcx/safety/prompt_injection.py` | Rewritten to the async `InputGuardrail` interface; pattern list unchanged |

Unmodified originals for diffing are kept in `third_party/agno/original/` with the upstream `LICENSE` in `third_party/agno/LICENSE`.

## Assessed and not copied
| Source | Module | Reason |
|---|---|---|
| agno-agi/agno | `agno/approval`, `agno/agent` | Tightly coupled to Agno's own tool, run and HITL types (the agent package alone is about 21,000 lines); NorthCX keeps its own small runtime, whose semantics are specified and tested |
