# Integration catalogue (WP 2.4)

Status: built 2026-11-19; checked by tests and component tests, not yet by a person in a browser.

## What it is
One place that says what an agent or a routine can use: tools (from every source) and the ways a routine can start. Today it is two existing endpoints, made consistent rather than a third one.

| Reader | Endpoint | Gives |
|---|---|---|
| Studio, the agent editor's Tools section | `GET /v1/catalog` | Every tool: name, description, source, connection, reads or changes, approval, inputs, fingerprint |
| Workspace, the routine editor | `GET /v1/automations-catalog` | Reports, events, destinations, assistants, step kinds, and the trigger types with a plain-words label and description |

## Requirements
| # | For | Requirement | Check |
|---|---|---|---|
| C1 | An author in Studio | Each tool in the picker is listed under the place it comes from: built in, a connector, or a named MCP connection | `toolGroups` test: built-in first, one section per connection, an unknown source shown under its own name, each tool once |
| C2 | Any client | A tool from an MCP connection says which connection it belongs to; any other tool says none | `test_describe_names_the_connection_of_an_mcp_tool_and_only_that` |
| C3 | A routine author | Each way a routine can start has a label and a one-sentence description, and the list matches what validation accepts | `test_the_automations_catalogue_describes_each_trigger...`: same keys and order as `triggers`; one definition (`TRIGGER_TYPES`) feeds the catalogue and both validators |
| C4 | A routine author | Choosing a trigger in the editor shows its description | Workspace component test |
| C5 | Existing clients | No field is removed or retyped | Agent API contract test; `triggers` is still a list of names |

## Design
- `connection` is the part of an MCP tool's name before the first `__`; connection names are lowercase letters, digits and `-` only (`CONNECTION_NAME`), so this is exact. Other tools have `null`.
- Access ("reads" or "changes things") is the existing `effect`; the picker already shows it. No second field.
- The catalogue is tenant-filtered as before: other tenants do not see the operator's MCP tools.

## Not in this work package, and why
- Connector-event triggers (a ticket arrives, an order changes): there is no such trigger yet. They arrive with WP 5.3 and will be added to `triggerInfo`; nothing is shown for them now.
- A routine `tool` step that reads `tools` from the catalogue: WP 5.1.
- Search and filtering in the picker: no list is long enough yet to need it (unverified; revisit with a real connection of 50+ tools).
