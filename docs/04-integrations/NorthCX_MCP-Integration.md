# NorthCX MCP integration (Phase 2)

Status: **Plan** (stages 1 to 4 done; nothing built). Updated: 2026-11-19. Master for: how NorthCX uses tools from MCP servers, the trust rules that apply, and work packages 2.1 to 2.6 of `../12-project/NorthCX_Agent-Platform-Plan.md`. Builds on `NorthCX_Tool-Gateway.md` (every tool, from any source, already gets the runtime's checks) and part of `../00-platform/NorthCX_Agent-Platform-Design.md` section 5.

## 1. Research
Read on 2026-11-19. **How it was read:** the official site `modelcontextprotocol.io` does not resolve from this environment (it is not in the network allowlist), so the specification was read from its source files on GitHub (`modelcontextprotocol/modelcontextprotocol`, folder `docs/specification/2026-07-28`) through a page-summarising fetch tool, and the SDK from its published package. The statements below are what those showed; the exact MUST and SHOULD wording must be confirmed against the specification text before the code that depends on it is written (marked "confirm" in section 3).

**The 2026-07-28 revision (changes since 2025-11-25)**
- **Stateless.** No `initialize` handshake and no `Mcp-Session-Id`; every request carries `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` in `_meta`, and on HTTP the `MCP-Protocol-Version`, `Mcp-Method` and (for `tools/call`) `Mcp-Name` headers. Servers must implement `server/discover`. A version a server does not support returns `UnsupportedProtocolVersionError` (code -32022) listing the versions it does.
- **Results** carry a required `resultType`: `complete`, or `input_required` (the server asks for more input; the client retries with `inputResponses`). This replaces server-to-client sampling, roots and elicitation requests.
- **`tools/list`** must not vary per connection (it may vary by the authorization presented), should be in a deterministic order, and carries `ttlMs` and `cacheScope` (`public` or `private`). Change notifications arrive on a `subscriptions/listen` stream, not a separate endpoint.
- **`tools/call`** results: `content`, optional `structuredContent` (validated by the client against `outputSchema` when present), `isError` for execution errors the model can act on. Protocol errors are JSON-RPC errors. `inputSchema` may use any JSON Schema 2020-12 keyword.
- **Tool annotations.** The specification says clients "MUST consider tool annotations to be untrusted unless they come from trusted servers". The hints themselves (read-only, destructive, idempotent, open-world) are defined in the SDK's type package, not on the revision's tools page.
- **Authorization** (HTTP only; stdio takes credentials from the environment): servers implement OAuth 2.0 Protected Resource Metadata; clients use it to find the authorization server, send the `resource` parameter (RFC 8707) on both requests, use PKCE with `S256`, never pass a token to a server that its own authorization server did not issue, never put a token in a URL, and validate `iss` when present. Persisted credentials are keyed by issuer; Dynamic Client Registration is deprecated in favour of Client ID Metadata Documents.
- **Compatibility.** A client may probe with a modern request and, on a `400` whose body is not a recognised modern error, fall back to `initialize` (and, for the deprecated HTTP+SSE transport, to its GET). Era is a property of the server and is cached per origin.
- **Deprecated:** Roots, Sampling, Logging, HTTP+SSE. **Tasks** moved to an extension (`io.modelcontextprotocol/tasks`).

**The official Python SDK** (`mcp` 2.3.0, MIT, "Production/Stable", Python 3.10+; types in `mcp-types` 2.3.0, MIT)
- Supports 2026-07-28: `Client` connects to a URL (Streamable HTTP), a stdio command, or an in-process server (for tests); `mode="auto"` probes `server/discover` and falls back to the handshake for older servers.
- Takes a caller-supplied `httpx2` client, so headers, timeouts and event hooks are ours.
- **Redirects:** its HTTP transport follows a redirect that stays on the endpoint's origin and keeps the method, and ignores the client's `follow_redirects` setting. NorthCX's rule is that outbound calls never follow redirects (`CLAUDE.md`), so this has to be closed in our client, and tested (section 3, M6).
- **Dependencies.** Already locked here: `httpx2`, `pydantic`, `starlette`, `anyio`, `opentelemetry-api`, `typing-extensions`, `typing-inspection`, `uvicorn`. New: `mcp`, `mcp-types`, `jsonschema`, `pyjwt`, `python-multipart`, `sse-starlette`. Only the licences of `mcp` and `mcp-types` (MIT) were read; the other four are checked in WP 2.1 before the lock changes.

**Not verified:** how the SDK reports `input_required` and task handles to a caller; whether a response hook runs before the SDK's own redirect handling; the SDK's OAuth providers beyond the redirect note; behaviour against any real vendor server (no vendor sandbox accounts exist, owner, 2026-11-19).

## 2. What exists and what is missing
- A tool from any source already gets validation, scopes, approvals, dry-run, duplicate-write protection, secret redaction and output screening from the runtime (`NorthCX_Tool-Gateway.md`), and carries a source label and a fingerprint. YAML connectors are the only external source today.
- Missing for MCP: a client; a way to run a tool whose input rules are a server's JSON Schema; a way to treat a tool's output as untrusted without the agent having to configure it; stored connections per tenant with approved tool lists; an operator screen.

## 3. Requirements
For: **operator** (installs and administers), **author** (builds agents, picks tools), **reviewer** (security).

| ID | For | Requirement | Acceptance check |
|---|---|---|---|
| M1 | Operator | Connect an MCP server by URL and see its tools (name, description, input fields, how NorthCX classes each as read or write) before any agent can use them | Against a fake server, the connection lists every tool with its classification; nothing is callable until approved |
| M2 | Reviewer | A tool call from an MCP server gets every runtime guarantee in the conformance suite (`tests/test_tool_conformance.py`) | The MCP source runs the same nine tests as the other two sources |
| M3 | Reviewer | A tool is a **write** unless the operator marked the connection trusted and the server's read-only hint says read. A write needs a person's approval; the operator cannot waive that in Phase 2 | A fake server claiming every tool is read-only, on an untrusted connection: every call is held for approval; on a trusted one, a read-only tool runs and a destructive one is held |
| M4 | Reviewer | The approved tool list is pinned by fingerprint. A tool whose definition changed, or a new tool, is not callable until the operator approves it again; the change is audited and shown | A fake server that changes a description after approval: the tool is refused with a plain message, an audit entry exists, and the old definition is shown beside the new one |
| M5 | Reviewer | An MCP tool's output is always treated as untrusted: instruction-like text is withheld before the model reads it, even when the agent configured no output guardrail | A fake server returning "ignore all previous instructions…" in a result and in a tool description: the model sees neither |
| M6 | Operator | Outbound calls go only to hosts the operator allowed, over https (http only for localhost), never follow a redirect, time out, cap the result size and are rate limited | Tests: a host not on the list, plain http, a same-origin 307, a slow server, an oversized result and a burst each fail with a message naming what to change |
| M7 | Reviewer | A credential is looked up by name in the tenant's secret store when a call is made and never appears in a result, a trace or a stored message | The conformance secret test passes for the MCP source; the credential is absent from every trace event |
| M8 | Reviewer | Each tool call writes a trace event with source `mcp`; creating, approving, changing and disabling a connection writes an audit entry | Tests read both |
| M9 | Author, customer | When the server is down, slow or refuses, the agent gets a plain error (the system did not answer) and is told to hand off; a write is never retried; a read is retried once | Tests with a failing fake server |
| M10 | Operator | Servers on the 2026-07-28 revision and on the earlier handshake revisions both work | The fake server runs in both modes and passes M1 and M2 |
| M11 | Operator | A connection belongs to one tenant; one tenant cannot see, use or change another's | A two-tenant test (the tenancy preview rules) |
| M12 | Reviewer | A server that asks for more input (`input_required`) or returns a task handle is handled as a failure with a plain message, because no person is in the loop for that exchange | Tests with a fake server that does both |

Not in Phase 2 (recorded, not dead requirements): OAuth authorization-code sign-in for servers that need a person's consent (needs a browser step and a stored refresh token; the first such server is a vendor's, which cannot be tested without a sandbox account); server-initiated requests (sampling, roots, elicitation); NorthCX as an MCP server; the Activepieces sidecar. Credentials in Phase 2 are a bearer token or API key held in the tenant's secret store.

## 4. Design
**Operator** (WP 2.3 screen; the same fields are the programmatic configuration in WP 2.1)
1. Adds a connection: name, server address, which secret holds its credential, trusted or not (default not).
2. NorthCX connects once and shows the tools it found, each with its description, its input fields, and "can change things" or "only reads". The operator ticks the ones agents may use and confirms. That list, with a fingerprint for each, is the pinned list.
3. From then on NorthCX refreshes the list when the server says it is stale (`ttlMs`). If anything differs from the pinned list, the connection shows "changed since you approved it", the changed or new tools stay off, and the operator reviews old and new side by side.
4. The network-needs page (WP 2.6) lists the server's host so the operator can open exactly that.

**Author:** picks tools from the catalogue (WP 2.4); an MCP tool appears as `<connection>__<tool>` (the model API allows letters, digits, `_` and `-`, up to 64; a name that does not fit is refused at approval with the reason).

**Messages** (plain, each says what to do): "The orders system did not answer. Try again or hand this to a person." / "This tool changed since you approved it. Review it in Connections." / "The server's address is not on your allowed list: add the host in Settings, Network."

**Failure behaviour** (fail closed): an unreachable, changed, unapproved or unclassifiable tool is not run; a response over the size cap is refused, not truncated into a half answer; a server that answers with an unknown result type is a failure.

## 5. Architecture
- **`ToolSource` interface** (designed here, built in WP 2.1, now that a second source exists): `discover() -> list[Tool]` and `refresh() -> changes`. YAML connectors are wrapped as the first implementation without changing their tests; `McpSource` is the second. A source never applies approvals, scopes or dry-run; the runtime does.
- **Tool input from a server's schema.** Today a tool's input is a pydantic model and the model sees its generated schema. For MCP, `Tool` gets an optional `input_schema` (the server's JSON Schema, shown to the model as is) and a `validate` method; the default keeps the pydantic path, MCP validates with `jsonschema`. The fingerprint already hashes the schema shown to the model, so it covers this. Existing tools are unchanged.
- **Untrusted output.** `Tool` gets `untrusted_output` (default false). When true, the runtime screens the result with the default instruction-pattern check even if the agent configured none, then applies the agent's own output guardrails as today. MCP tools set it.
- **Approval for a write** uses the existing `requires_approval`; for an MCP write it always returns a reason ("`<tool>` can change things in `<connection>`").
- **Client wrapper.** One module wraps the SDK `Client` behind a small interface (`list_tools`, `call_tool`, `close`), with our own `httpx2` client: host allowlist and https check before connecting, a response hook that fails any 3xx, timeouts, a result size cap, headers from the secret store. Nothing outside this module imports the SDK, so it can be replaced.
- **Storage** (WP 2.3, a migration that runs on an existing install): `mcp_connections` (id, tenant, name, address, trusted, secret name, enabled, approved tools as name and fingerprint, created and changed by and when), with the tenancy row rules of the other tables. Credentials stay in the tenant secret store (decision 196). Connection details are configuration, not customer data; tool inputs and results are in traces and are masked as today. Export, erasure and retention: a tenant's connections go with the tenant; nothing else is stored.
- **Surfaces.** New routes under `/v1/connections` with route-permission entries, typed responses and the contract snapshot regenerated (the stability rule from Phase 1 applies); the catalogue (WP 2.4) is additive on `GET /v1/catalog`. Source label `mcp` added to `TOOL_SOURCES`.
- **Deployment setting.** `NORTHCX_MCP_HOSTS` (the operator's allowlist, like `NORTHCX_CONNECTOR_HOSTS`) in `.env.example`; connections can only use hosts on it. The residency report lists each connection's host (WP 2.6).
- **Alternatives rejected.** Our own minimal MCP client: the dual-era fallback, event streams and authorization are more than the first guess, and the SDK is maintained with the specification (kept replaceable behind the wrapper). A second approval layer for MCP in front of the runtime: duplicates the runtime (the lesson of Phase 1). Trusting the server's annotations by default: the specification says not to.
- **Threat model.** New inputs are a remote server's tool descriptions, schemas and results (untrusted: M3 to M5), a new outbound destination (M6, residency), and a stored credential reference (secret store, M7). A row for "malicious or compromised MCP server" is added to the threat model in WP 2.2.

## 6. Work packages
| WP | Work | Exit check | State |
|---|---|---|---|
| 2.1 | `ToolSource` interface; YAML connectors as the first source; the client wrapper and `McpSource` on the SDK; `Tool.input_schema` and `validate`; M1 (library level), M2, M6, M7, M9, M10, M12 against a fake server (in-process and over HTTP) | The conformance suite passes for the MCP source in both protocol modes; existing connector tests unchanged | Not started |
| 2.2 | Trust rules: M3, M4, M5, M8 (trace), the threat-model row | Injection and changed-tool-list scenarios pass | Not started |
| 2.3 | Stored connections, the routes, the operator screen, audit, M1 (screen), M8 (audit), M11 | An operator adds a connection and approves its tools without editing files; browser test | Not started |
| 2.4 | One catalogue of tools and triggers read by Studio and Automations | Catalogue API with tests | Not started |
| 2.5 | Connectors for the target market (helpdesk, commerce, payments) | A sandbox demonstration | **Blocked: no vendor sandbox accounts (owner, 2026-11-19).** Connectors written from vendor documentation alone would be unverified and are not claimed |
| 2.6 | Network-needs page; residency entries for every connection | Every external host is listed | Not started |

Order: 2.1, 2.2, 2.3, 2.4, 2.6. WP 2.1 and 2.2 are library work with no user-visible feature; MCP connections count as built only when WP 2.3 wires them through the API, storage and screen with tests, and the plan's progress table says so.

## 7. Decisions to record
200 adopt the `mcp` SDK behind a wrapper (new dependencies named in section 1); 201 an MCP write needs approval and trust is the operator's, per connection; 202 `Tool.input_schema` and `Tool.untrusted_output`.
