# NorthCX Build vs Adopt

Status: **Reference**. Updated: 2026-11-09. Master for: the build-versus-adopt strategy. Strategy: **adopt by copying and adapting** licensed reference code wherever possible; build only the gaps. See `NorthCX_Code-Reuse-Policy.md`. Component names and the feature-to-source map are in the Reference (sections 8, 10, 11).

| Capability | Decision | Notes |
|---|---|---|
| Agent loop, tools, workflows | Copy and adapt | Plus our supervision and approval layer |
| Agent runtime, tools, approvals | Build | Core differentiator; small |
| Supervisor / guardrails | Build first, wrap a rules engine later | Own LLM check first |
| Simulation testing | Build | No suitable open-source option found |
| Memory | Adopt | Behind `MemoryStore` |
| Knowledge / retrieval | Adopt | As a tool |
| Observability and evals | Adopt | OpenTelemetry export |
| Omnichannel and human inbox | Adopt | Webhook integration |
| Voice | Adopt | Phase 5 |
| Studio | Decide at Phase 4 | Adopt or build |
| Agent-assisted building and natural-language analytics | Build on the model | Phase 6 |
| Release management | Build | Versions, environments, rollback |
| Audit, roles, rate limits | Build | Phase 2 |
| Durable workflows | Research | Not yet researched |
| CX connectors | Research | Not yet researched |
| Outcome-based billing | Build, later | Out of v1 |

## Criteria
1. Permissive licence and self-hostable.
2. Fits a customer-service workload.
3. Replaceable behind an interface.
4. Actively maintained (verify).
