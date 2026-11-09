# NorthCX Personal Intelligence Specification

Status: **Designed**. Updated: 2026-11-09. Master for: instructions, persona, memory, skills and personal context for staff. Requirements for the personal layer of the Workspace and Settings (FR39): instructions, persona, memory, skills, personal context and the controls over them. Catalog IDs PN1 to PN12. Needs epic E5 (staff memory E5.5). Screens: `../assets/design/` (settings-skills and the Profile screens).

## 1. Principle
Personal intelligence makes an assistant fit the person without ever weakening an organization rule. Every layer is opt-in, visible ("what it used"), switchable per chat and erasable.

## 2. Layers and precedence (highest wins)
1. **Organization rules** (locked policies, forced hand-off topics, data limits).
2. **Team instructions.**
3. **Space instructions.**
4. **Personal instructions** (standing instructions and persona).
5. **Chat style** (tone and length for this chat).
**Memory** and **personal context** inform an answer but never override a layer above. Nothing overrides a policy, a source's facts or a customer's data. When memory disagrees with a source, the answer says so.

## 3. Profile (six tabs)
| Tab | Holds | Rule |
|---|---|---|
| About you | Name, team, language, time zone, default assistant, signature; roles read-only | A person cannot edit their own roles |
| Instructions and persona | Standing instructions, style presets or a custom style from the person's own writing, a table of what applies to a chat | Instructions that conflict with a higher layer are shown as ignored, with the reason |
| Personal context | Opt-in sources, each with consent: own hand-offs, approvals, drafts and outputs, team documents; calendar and email later; a daily briefing; suggestions and reminders; a preview of what would be used | Off until the person turns each source on; turning one off stops its use at once |
| Skills | Reusable ways of doing a task from the person, the team and the organization | A skill is instructions only; it never adds a tool or access |
| My assistants | Assistants the person builds, limited to their own access | Shared only with a reviewer when the assistant can write |
| Activity and controls | What assistants used, retention, temporary chats, export, delete, erase | Erase removes memory, context and chat history on request |

## 4. Memory
Saving is automatic or by "remember this". Scopes: personal, space, team. Each item shows where it came from and what it applies to. A chat can start without memory. Items unused for a period are offered for review. Customer messages and personal details of customers are never saved to personal context or memory; only the person's own working preferences and facts about the work are.

## 5. Requirements
| ID | Requirement | Acceptance |
|---|---|---|
| PN1 | Layered instructions with the fixed precedence | A personal instruction cannot weaken an organization rule (test) |
| PN2 | Persona and style from presets or the person's writing | The style changes tone only, never facts or policy |
| PN3 | Memory with scopes, sources and per-item delete | A deleted item is not used in the next answer |
| PN4 | Per-chat switches for instructions, memory and context | A switched-off layer is absent from the prompt (test) |
| PN5 | "What it used" on every answer | The list matches what was in the prompt |
| PN6 | Personal context sources with consent | No data is read from a source that is off |
| PN7 | Skills as instructions only | A skill that names a tool the person lacks does not grant it |
| PN8 | Personal assistants within the person's own access | A personal assistant cannot read what its owner cannot |
| PN9 | Temporary chat | Nothing is saved and no memory is read or written |
| PN10 | Export and erase | An erase removes memory, context and history within a stated time and is audited |
| PN11 | Retention defaults set by the organization | A person may shorten but not lengthen |
| PN12 | Customer data never enters memory | A saved memory containing a customer's personal details is rejected (test) |

## 6. Privacy and safety
Memory is stored per tenant and person; an administrator cannot read a person's personal memory, but can set retention and turn the feature off. Memory content is untrusted input to the model, never instructions with authority. Prompt-injection text inside a remembered item cannot raise permissions.

## 7. Decisions (decision 166, 2026-11-09)
First personal-context sources: the person's own hand-offs, approvals, drafts and outputs, and team documents; calendar and email come later. Read-only personal assistants may be shared without a reviewer; any that can write need one. Default retention for personal chats is 90 days, a placeholder to validate; a person may shorten it but not lengthen it, and an administrator may change the default.
