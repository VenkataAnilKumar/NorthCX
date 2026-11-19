# NorthCX Reference Sources

Status: **Reference**. Updated: 2026-11-18. Master for: the list of external projects, specifications and product pages studied for the Agent Platform modules (Chat, Agent Studio, Integrations, Automations), with how to fetch them for reading. The design that uses them is `../00-platform/NorthCX_Agent-Platform-Design.md`.

These are for reading, and for **copying and rebranding where the licence allows, never depending** (decision 199; rules in `../08-governance-safety/NorthCX_Code-Reuse-Policy.md`). Nothing has been copied yet (`../../NOTICE`, `../../THIRD_PARTY.md`). Keep fetched copies **outside this repository** (for example `~/northcx-sources/`) and copy only the files you use into `src/`. Licences were not reviewed here and some are unclear or restrictive; read the project's own LICENSE file at the commit you copy from. Facts about commercial products come from vendor pages and third-party reviews and are directional.

## Folder layout
```
northcx-sources/
  integrations/  chat/  studio/  automations/  benchmarks/
```

## Repositories to clone
Repository addresses marked * came from search results or mirrors, not from a page that was opened; if a clone fails, search GitHub for the project name.

```bash
mkdir -p ~/northcx-sources/{integrations,chat,studio,automations,benchmarks} && cd ~/northcx-sources

# Integrations
git clone --depth 1 https://github.com/modelcontextprotocol/python-sdk integrations/mcp-python-sdk   # *
git clone --depth 1 https://github.com/modelcontextprotocol/servers integrations/mcp-servers
git clone --depth 1 https://github.com/Activepieces/activepieces integrations/activepieces
git clone --depth 1 https://github.com/onyx-dot-app/onyx integrations/onyx                           # *
git clone --depth 1 https://github.com/topoteretes/cognee integrations/cognee                        # *

# Chat
git clone --depth 1 https://github.com/ag-ui-protocol/ag-ui chat/ag-ui
git clone --depth 1 https://github.com/assistant-ui/assistant-ui chat/assistant-ui
git clone --depth 1 https://github.com/CopilotKit/CopilotKit chat/copilotkit
git clone --depth 1 https://github.com/danny-avila/LibreChat chat/librechat
git clone --depth 1 https://github.com/chatwoot/chatwoot chat/chatwoot
git clone --depth 1 https://github.com/vercel/ai-elements chat/ai-elements
git clone --depth 1 https://github.com/lobehub/lobe-chat chat/lobehub
git clone --depth 1 https://github.com/janhq/jan chat/jan

# Studio
git clone --depth 1 https://github.com/simstudioai/sim studio/sim
git clone --depth 1 https://github.com/xyflow/xyflow studio/xyflow
git clone --depth 1 https://github.com/langflow-ai/langflow studio/langflow
git clone --depth 1 https://github.com/agenta-ai/agenta studio/agenta                                # *
git clone --depth 1 https://github.com/agno-agi/agno studio/agno                                     # *
git clone --depth 1 https://github.com/rowboatlabs/rowboat studio/rowboat

# Automations and agent runtimes
git clone --depth 1 https://github.com/NousResearch/hermes-agent automations/hermes-agent
git clone --depth 1 https://github.com/Cloudgeni-ai/opengeni automations/opengeni                    # *
git clone --depth 1 https://github.com/openagents-org/openagents automations/openagents              # *
git clone --depth 1 https://github.com/langfuse/langfuse automations/langfuse
```

## Specifications and documents to save (primary sources)
| Module | Link |
|---|---|
| Integrations | MCP 2026-07-28 announcement: https://blog.modelcontextprotocol.io/posts/2026-07-28/ |
| Integrations | MCP specification: https://modelcontextprotocol.io/specification/2026-07-28 |
| Integrations | MCP registry: https://registry.modelcontextprotocol.io |
| Integrations | Activepieces piece authentication: https://www.activepieces.com/docs/developers/piece-reference/authentication |
| Integrations | Zendesk MCP: https://support.zendesk.com/hc/en-us/articles/10497779528730-Connecting-to-MCP-servers-and-using-MCP-tools-in-action-flows |
| Chat | AG-UI interrupts: https://docs.ag-ui.com/concepts/interrupts.md |
| Chat | AG-UI events: https://docs.ag-ui.com/concepts/events.md |
| Chat | assistant-ui documentation: https://www.assistant-ui.com (not reachable when this list was made) |
| Automations | Temporal human-in-the-loop: https://docs.temporal.io/ai/cookbook/human-in-the-loop-python |
| Automations | Temporal document approvals: https://docs.temporal.io/guides/reliable-document-approvals |

## Product benchmarks (secondary sources)
| Product | Link |
|---|---|
| Sierra Agent Studio | https://sierra.ai/blog/meet-agent-studio and https://sierra.ai/product/agent-studio |
| Decagon AOPs | https://decagon.ai/product/aop |
| Decagon testing and QA | https://decagon.ai/product/testing-qa |
| Intercom Procedures vs Workflows | https://www.intercom.com/help/en/articles/14077835-procedures-vs-tasks-vs-workflows |
| Intercom Fin capabilities | https://www.fin.ai/capabilities |

## Suggested reading order
1. MCP Python SDK and the MCP specification (Integrations).
2. AG-UI and assistant-ui (Chat).
3. Sim (its `apps/` and `packages/`) and xyflow (Studio).
4. Hermes Agent (`gateway/`, `cron/`, `skills/`) (Automations).
5. The Sierra, Decagon and Intercom pages (the product benchmark).

## What to study in each
| Source | Study for |
|---|---|
| MCP SDK and spec | Stateless transport, authorization, tools, extensions: the tool gateway |
| Activepieces | How an integration (actions, triggers, one auth definition) is defined |
| AG-UI | Typed events; approval as an interrupt that ends a run and a resume that starts the next |
| assistant-ui, LibreChat | Tool cards, inline approvals, branching, edit and re-run |
| Sim, Langflow, xyflow | Graph editor, node inspector, tools and triggers in one catalogue |
| Agenta | Side-by-side prompt versions and judge scoring |
| Hermes Agent, OpenGeni | One gateway for many channels, scheduled jobs, replayable sessions |
| Decagon, Sierra, Intercom | Plain-language procedures, simulations, always-on quality checks |

Commercial and open-source agent interfaces to study, grouped by NorthCX screen, are in `NorthCX_Agent-UI-References.md`.
