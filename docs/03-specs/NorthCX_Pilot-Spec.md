# NorthCX Pilot Specification

Status: **Draft, designed 2026-11-09; not built.** Requirements for the Pilot window (FR36), the place where a staff member gives an assistant a task. Screens: `../assets/design/50-pilot-research-plan.png`, `51-pilot-add-menu-files.png`, `52-pilot-live-run.png`. Design text: `../07-design/NorthCX_Platform-Features-and-Tabs.md` section 3. Catalog IDs PI1 to PI14. Needs epics E5, E6 and E8.

## 1. Purpose
Let a person hand work to an assistant, see what it plans and does, steer it, and keep the result. It is plan-first for larger tasks and never acts without the person's permission for anything that writes.

## 2. Layout
Left: Workspace navigation and recent chats. Centre: the conversation and composer. Right: a panel with inner tabs **Plan, Result, Files, Sources, Context, Steps, Side chat** (decision 155 renamed Output to Result).

## 3. The task lifecycle
`draft` → (`needs answers`) → `planned` → `approved` → `running` → (`waiting for a person`) → `done` | `stopped` | `failed`.
1. The person describes a task, picks an assistant, a space and a task style.
2. For Research and Do, the assistant may ask up to three clarifying questions, each with answer chips and free text.
3. It writes a plan: numbered steps, sources and tools each step uses, an estimate of time and cost, the model tier and why, and whether anything writes.
4. The person approves, edits the plan, or runs it in the background. Quick answer and Think skip the plan.
5. Running shows live steps. The person can pause, redirect (edits the remaining plan, never rewrites what ran) or stop.
6. A step that would write to a system stops and asks the person. The ask names the exact action and input.
7. The result is saved as a versioned output, with sources, steps and cost, and can be shared, scheduled or turned into an automation.

## 4. Task styles (decided, decision 163: Quick answer and Research ship first; Think and Do follow, and Do waits for connected tools)
| Style | Behaviour | Plan | Background | Writes |
|---|---|---|---|---|
| Quick answer | One answer with citations | No | No | Never |
| Think | Longer reasoning, one answer | No | No | Never |
| Research | Questions, plan, searches the company's own sources, cited result | Yes | Yes | Never |
| Do | Uses connected tools to carry out steps | Yes | Yes | Only after the person approves each write |

Research works on the company's own sources only in the first release (decision 159). Web search is later, administrator-enabled, off by default and per assistant; it is never used in a sensitive conversation or with customer data in the query, its results are labelled as web sources, and page text is treated as data, never as instructions.

## 5. The + menu
Space; files; Library sources; a conversation or customer as masked context; connected systems; skills and playbooks; a pasted link or screenshot. Each item shows what it will let the assistant see. Files are checked before the assistant reads them: text is extracted, personal data is masked, a scan without text is refused with a reason, and administrators set size and count limits.

## 6. Model mode
Auto, Faster and cheaper, Best quality, Private only. The window shows where the text will go. A mode that is not allowed for this data is shown unavailable with the reason. Sensitive conversations never use a public model, including on fallback (`NorthCX_Hybrid-Model-Selection.md`).

## 7. Context and memory
The Context tab lists the instructions, space instructions, memory and personal context in use, each switchable for this chat. Order of precedence: organization rules, team, space, personal, chat style. Memory informs and never overrides (`NorthCX_Personal-Intelligence-Spec.md`). A temporary chat saves nothing and uses no memory.

## 8. Requirements
| ID | Requirement | Acceptance |
|---|---|---|
| PI1 | Plan before work for Research and Do, with estimate | Nothing runs before approval |
| PI2 | Clarifying questions with chips, at most three | The plan reflects the answers |
| PI3 | Live Steps view with time, tokens, cost, model | A running task shows each step as it completes |
| PI4 | Pause and stop in the first version; redirect in the second | Redirect keeps completed steps and changes only the rest |
| PI5 | Writes always ask first | A write step without a recorded approval cannot run |
| PI6 | Permissions of the signed-in person | An assistant cannot read a source the person cannot |
| PI7 | Citations on every claim from a source | An answer with no source says so |
| PI8 | Files, sources, space and masked conversation context | Masked data stays masked in the model prompt and the saved output |
| PI9 | Result tab with versions, save, share, schedule | Saving creates an output with its sources and cost |
| PI10 | Background runs that survive closing the window | The person is notified when it needs them or is done |
| PI11 | Side chat that adds nothing back | A side question never changes the main result |
| PI12 | Chat history, pin, rename, archive, delete, temporary chat, branch | A deleted chat is erased with its memory links |
| PI13 | Drafted replies open in Inbox with the draft ready and are never sent automatically | No send without a person |
| PI14 | Cost and step limits per task, set by the administrator | A task that would exceed the limit stops and asks |

## 9. Failures
A model or tool failure ends the step with a reason and offers retry, skip or stop; the plan is not silently changed. A source removed mid-run is reported and the step marked incomplete. Closing the browser does not stop a background run; the person can reopen it from Recent.

## 10. Decisions (decision 163, 2026-11-09)
Task styles: Quick answer and Research first. Plan: shown for Research and Do, skipped for Quick answer and Think. Steering: pause and stop in the first version, redirect in the second. Files: limits are set per space by an administrator, with conservative defaults whose numbers are chosen when the feature is built and measured.
