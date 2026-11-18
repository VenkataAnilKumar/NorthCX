# NorthCX Build vs Adopt

Status: **Reference**. Updated: 2026-11-09. Master for: the build-versus-adopt strategy. Strategy: **adopt by copying and adapting** licensed reference code wherever possible; build only the gaps. See `../08-governance-safety/NorthCX_Code-Reuse-Policy.md`. Component names and the feature-to-source map are in the Reference (sections 8, 10, 11).

**What actually happened (2026-11-09).** The strategy below was the plan in early November. In practice every reference project assessed was either too coupled or a poor fit, so NorthCX contains no third-party source code and depends on no reference project (`NOTICE`, `THIRD_PARTY.md`, which also lists what was assessed and why it was not copied). The "Outcome" column records what was done.

| Capability | Planned decision | Outcome |
|---|---|---|
| Agent loop, tools, workflows | Copy and adapt | Built in-house (small runtime, `northcx/runtime.py`) |
| Agent runtime, tools, approvals | Build | Built |
| Supervisor / guardrails | Build first, wrap a rules engine later | Built in-house, including the policy library; no rules engine |
| Simulation testing | Build | Built |
| Memory | Adopt | Built in-house behind `MemoryStore` and `MemoryService`; replaceable |
| Knowledge / retrieval | Adopt | Built in-house (Postgres full-text and pgvector); embeddings through an optional external service |
| Observability and evals | Adopt | Built in-house; traces exported to OpenTelemetry and Langfuse backends |
| Omnichannel and human inbox | Adopt | Channel adapters built in-house; hand-offs delivered to a helpdesk by signed webhook and a Chatwoot adapter |
| Voice | Adopt | Conversation side built in-house; speech and telephony are a bridge the operator connects |
| Studio | Decide at Phase 4 | Built in-house (Next.js) |
| Agent-assisted building and natural-language analytics | Build on the model | Built |
| Release management | Build | Built |
| Audit, roles, rate limits | Build | Built |
| Durable workflows | Research | Designed as Automations (E8), built in-house on the existing leases and scheduler |
| CX connectors | Research | Generic YAML connectors built; native connectors planned (E9) |
| Outcome-based billing | Build, later | Out of scope until D1 |

## Criteria
1. Permissive licence and self-hostable.
2. Fits a customer-service workload.
3. Replaceable behind an interface.
4. Actively maintained (verify).
