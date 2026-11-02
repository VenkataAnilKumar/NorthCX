# NorthCX Build vs Adopt

Status: Draft

| Capability | Decision | Component | Notes |
|---|---|---|---|
| Agent runtime, tools, approvals | Build | `src/core` | Core differentiator; small |
| Supervisor / guardrails | Build, optionally wrap | own + NeMo Guardrails | Own LLM check first |
| Simulation testing | Build | `src/sim` | No suitable open source found |
| Memory | Adopt | Mem0 (adapter) | Behind `MemoryStore` |
| Knowledge / RAG | Adopt | Onyx | As a tool; verify licence |
| Observability and evals | Adopt | Langfuse | OpenTelemetry export |
| Omnichannel and human inbox | Adopt | Chatwoot | Webhook integration |
| Voice | Adopt | Pipecat | Phase 5 |
| Studio | Adopt or build | Sim / custom | Decide Phase 4 |
| Agent framework alternative | Evaluate | Agno | Only if switching to Python |
| Durable workflows | Research | Temporal / Inngest | Not yet researched |
| CX connectors | Research | tbd | Not yet researched |
| Billing / outcome pricing | Build, later | tbd | Out of v1 |
| Open-ended autonomous agents | Skip | Kortix/Suna | Not a fit |

## Criteria
1. Permissive licence and self-hostable.
2. Fits a customer-service workload.
3. Replaceable behind an interface.
4. Active maintenance (verify).
