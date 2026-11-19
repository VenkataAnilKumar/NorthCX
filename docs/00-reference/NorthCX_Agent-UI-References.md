# NorthCX Agent Interface References

Status: **Reference**. Updated: 2026-11-18. Master for: commercial and open-source agent interfaces worth studying for NorthCX's screens (customer widget, Studio, test console, Workspace inbox and Pilot, quality and insights). It lives in `00-reference/` because it names other companies' products. Related: `NorthCX_Reference-Sources.md` (repositories and links to fetch), `NorthCX_Competitor-Landscape.md` (competitors by group), `NorthCX_Agent-Platform-Research.md` (what was learned).

Sources: the CX products and open-source projects come from web research in November 2026 (vendor pages, project pages, comparisons); the general commercial assistants (ChatGPT, Claude apps, Gemini, Microsoft Copilot products, Glean) are listed from general knowledge and their current versions were not checked. Licences were not reviewed; some open-source projects carry custom or branding terms (noted). Copying and rebranding is allowed where the licence permits and NorthCX never depends on the project (`../08-governance-safety/NorthCX_Code-Reuse-Policy.md`); nothing has been copied yet.

## 1. Customer-facing chat
| Product | Type | Study for |
|---|---|---|
| Intercom Fin | Commercial | Answers inside the help widget; hand-off to a person in the same thread |
| Sierra | Commercial | A branded agent across chat and voice; outcome-focused conversations |
| Decagon | Commercial | One agent across chat, email and voice |
| Zendesk AI agents, Salesforce Agentforce | Commercial | The agent embedded in an existing helpdesk |
| Chatwoot | Open source (MIT core; separate enterprise directory) | Multi-channel live-chat widget and inbox; NorthCX already has an adapter |
| assistant-ui | Open source library (MIT) | Streaming, tool cards, inline approvals, attachments |

## 2. Agent builder studios
| Product | Type | Study for |
|---|---|---|
| Sierra Agent Studio (Journeys) | Commercial | Plain-language procedures, generated from existing operating procedures |
| Decagon (Agent Operating Procedures) | Commercial | Procedures with Git-based versioning, generated from transcripts |
| Intercom Fin (Procedures, Workflows) | Commercial | Reasoning procedures kept separate from linear canvas flows; simulation before launch |
| Microsoft Copilot Studio | Commercial | Low-code agent building for business users |
| Sim | Open source (Apache-2.0) | Canvas builder with tools and triggers in one catalogue; the same frontend stack as NorthCX |
| Langflow | Open source (MIT) | Component palette and flow canvas |
| Dify | Source-available (custom licence with a multi-tenant restriction) | App builder with knowledge and a publish flow |
| React Flow (xyflow) | Open source library (MIT) | The canvas library most builders use |

## 3. General agent chat apps
| Product | Type | Study for |
|---|---|---|
| ChatGPT, Claude apps, Gemini | Commercial | Polished chat, artifacts and canvases, tool and agent modes, projects with files |
| Microsoft 365 Copilot, Glean | Commercial | An assistant over company data with permission-aware search |
| LibreChat | Open source (MIT) | Branching, edit and resubmit, artifacts, agents, MCP |
| Open WebUI | Open source with a branding clause above a user threshold | Self-hosted chat with retrieval, tools and roles |
| LobeHub | Open source under a custom community licence (terms not confirmed) | Agent setup in one screen, agent teams, editable memory |
| Jan | Open source (Apache-2.0; some components may differ) | Local-model desktop chat with an OpenAI-compatible server |

## 4. Agent-in-the-loop interfaces
| Product | Type | Study for |
|---|---|---|
| CopilotKit | Open source (MIT) | Human-in-the-loop pause and approve, generative UI, shared agent and UI state |
| AG-UI protocol | Open source (MIT) | The event contract: approval as an interrupt that ends a run, then a resume |
| Hermes Agent | Open source (MIT) | One gateway for many messaging platforms; scheduled jobs delivered to chat |
| Intercom and Zendesk agent inboxes | Commercial | How a person takes over from the AI with full context |

## 5. Quality, testing and observability
| Product | Type | Study for |
|---|---|---|
| Decagon (Watchtower, simulations) | Commercial | Always-on quality checks written in plain language; scheduled simulations |
| Intercom Fin (CX Score, Topics Explorer, Suggestions) | Commercial | Insights that propose the next fix |
| Langfuse | Open source (MIT outside `ee` folders) | Traces, prompt versions, evaluations; NorthCX already exports traces to it |
| Agenta | Open source (MIT core; enterprise features separate) | Side-by-side prompt comparison, LLM-as-judge |

## 6. Which references fit which NorthCX screen
| NorthCX surface | References |
|---|---|
| Customer widget | Intercom Fin and Chatwoot for the experience; assistant-ui for components |
| Studio for non-engineers | Sierra Journeys and Decagon AOPs for the authoring model; Copilot Studio for the low-code feel; Sim for layout |
| Studio test console | assistant-ui and CopilotKit for inline approvals; LibreChat for edit and rerun |
| Workspace inbox and Pilot | Intercom and Zendesk inboxes for take-over; Glean for company search; LibreChat and Open WebUI for chat |
| Quality and insights | Decagon Watchtower, Fin insights, Langfuse and Agenta |
