# NorthCX Integrations

Status: Draft. Connector research not yet done.

## Integration types
| Type | Examples of systems | Mechanism |
|---|---|---|
| Orders / commerce | Order and shipment lookup | Tool |
| Billing | Refunds, invoices | Tool with approval rule |
| CRM / accounts | Customer profile | Tool |
| Helpdesk / inbox | Tickets, human queue | Channel adapter + handoff |
| Knowledge | Articles, policies | Retrieval tool |

## Connector library (T5)
In-tree, tested connectors for common categories, each with typed tools, approval defaults and scenarios: order lookup, shipment tracking, refunds and credits, subscription changes, account profile updates, ticket create/update, appointment booking.

## Permissions (T6)
Tools are granted per agent and scoped per customer, so an agent can only touch the current customer's records.

## Idempotency (T4)
Writes carry an idempotency key derived from session and call; retries never duplicate effects.

## Dry-run (T8)
Tests and simulations can run tools in dry-run mode that records the intended action without executing it.

## Webhooks (P8)
Signed events for conversation status changes, approvals and handoffs.

## Declaring a tool: effect, dry run and secrets
- **`effect`**: `"read"` for a tool with no side effects, `"write"` (the default, the safe assumption) for anything that changes a system. Mark only genuinely read-only tools as reads.
- **`dry_run_result`**: what a write tool returns when the platform is testing. Simulations (and the release gate's proofs) never execute write tools; they call this instead, or return a generic placeholder if you give none. Apply the same business rules in it (the example refund checks the order exists, is delivered and not over its total) so scenarios still catch rule violations. The command line's `--allow-side-effects` runs writes for real and exists only for sandboxes.
- **Secrets**: a tool reads a credential with `ctx.secret("payments_key")`, configured as `NORTHCX_SECRET_PAYMENTS_KEY` or `NORTHCX_SECRET_PAYMENTS_KEY_FILE`. Never return a credential or include it in a message; if one slips into a result or an error, the platform replaces it with `[redacted:name]` before the model, traces, saved history, approvals, handoffs or replies see it. Credentials shorter than eight characters are refused because they cannot be scrubbed safely.
- **Idempotency**: `ctx.idempotency_key` is stable for an approved action; pass it to the downstream system.
- **Supplying your tools**: write a function returning a `Registry` and set `NORTHCX_REGISTRY=your.module:function` (the container's default is the bundled example), with `NORTHCX_AGENTS_DIR` and `NORTHCX_SCENARIOS_DIR` pointing at your spec and scenario directories.

## Tool authoring checklist
Narrow scope; typed input; least-privilege credentials; idempotency key for writes; timeouts; return minimal data; approval rule for money or irreversible actions; tests with a scripted model.

## Secrets
Credentials come from environment or a secrets manager, never from prompts or traces.

## Open
Which connectors ship in-tree vs as separate packages.
