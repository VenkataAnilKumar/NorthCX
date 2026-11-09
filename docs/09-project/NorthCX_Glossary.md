# NorthCX Glossary

Status: **Reference**. Updated: 2026-11-09. Master for: terms.

| Term | Meaning |
|---|---|
| Agent | A configured assistant: instructions, tools, guardrails, model |
| Run | One user message processed to a reply |
| Session | A conversation's history, identified by `sessionId` |
| Tool | A typed function the agent can call |
| Guardrail / supervisor | A check on a draft reply or tool call |
| Approval | A human decision required before a tool runs |
| Handoff / escalation | Transfer of the conversation to a human |
| Trace | Event log for a run |
| Resolved | Defined in the PRD |
| Scenario | A scripted conversation with expectations |
| Judge | A model scoring a reply against a rubric |
| Customer facts | Durable facts stored per customer |
| Adapter | Code connecting a channel or service to the API |
| Studio | The planned low-code builder |
| Skill | A reusable procedure an agent can use inside a workflow |
| Journey | A scenario blueprint with goals, required steps and guardrails |
| Version | An immutable snapshot of an agent definition |
| Release | A version published to an environment |
| Environment | dev, staging or production |
| Forced-handoff topic | A topic that always goes to a human |
| Handoff package | Transcript, profile, actions and summary given to a human |
| Containment | Share of conversations that end without handoff |
| Required scenario | A simulation that must pass before promotion |
| Staged rollout | Serving a new version to a share of traffic |
| Workspace | The staff web app: Home, Pilot, Work, Assist, Create, Team (planned after 1.0) |
| Pilot | The Workspace window where a person gives an assistant a task, approves its plan and keeps the result |
| Assistant | A staff-facing helper; acts with the signed-in person's permissions. Not the same as an agent |
| Inbox | The Workspace tab for conversations that need a person (called Hand-offs in Admin) |
| Space | Where instructions, sources, files, chats and outputs for one piece of work live together |
| Output | Something an assistant made and the person saved |
| Result | The Pilot inner tab showing what the current chat is making |
| Automation | Multi-step work that runs by itself, with limits and a kill switch |
| Agent Hub | Gallery of predefined agents and assistants; installing never makes one live |
| Builder | Assistant that drafts agents and automations for review; never goes live by itself |
| Personal intelligence | A person's instructions, persona, memory, skills and personal context, layered under organization rules |
| Hybrid model selection | Choosing local, private or public models by data limits, qualification, rules and cost |
