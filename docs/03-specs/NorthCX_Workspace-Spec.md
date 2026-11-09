# NorthCX Workspace Specification

Status: **Designed**. Updated: 2026-11-09. Master for: the staff Workspace app. Requirements for the staff Workspace app (FR35). Screens and mockups: `../07-design/NorthCX_Platform-Features-and-Tabs.md`. Catalog IDs (W1 to W14) are in `NorthCX_Feature-Catalog.md` section 12. Everything here is planned for after 1.0 (epics E2, E5, E6, E7, E8 and E22 in the implementation plan).

## 1. Purpose and users
A separate web app for the people who supervise the agents: support staff, team leads and reviewers. It has its own address, one sign-in with the Admin app, and one design system. It does not replace the helpdesk, and it never sends a message to a customer without a person doing so.

## 2. Navigation (decided, decisions 153, 157)
Six left items: Home, Pilot, Work (Inbox, Approvals, Customers), Assist (Assistants, Search, Library), Create (Outputs, Spaces, Automations), Team (Quality, Performance; leads and reviewers only). A badge on a sub-tab also shows on its group. Each group remembers the last sub-tab used. A command bar (Ctrl K) reaches any tab by name. A group with one visible sub-tab shows no sub-tab row.

## 3. Cross-cutting rules
1. A person sees only what their roles allow; assistants act with the signed-in person's permissions, never more.
2. Customer personal data is masked everywhere outside the live conversation. Revealing a field needs a logged reason.
3. Nothing is sent to a customer, and no write to a business system happens, without a person approving it.
4. Every state change (resolve, approve, reject, publish, share) is written to the audit log with the person, the time and the note.
5. Every list has empty, loading, error and "no permission" states, each with a reason and a next step.
6. Keyboard operation and labelled controls everywhere; the themes and accessibility settings in the Design System apply.

## 4. Requirements by tab
| Tab | Requirement | Acceptance |
|---|---|---|
| **Home** (W1) | Shows what needs the person (approvals, hand-offs), what is ready (finished runs, digests), recent work and a prompt with assistant, space and sources chosen | A person with 2 approvals and 3 hand-offs sees both counts and opens each in one click |
| **Inbox** (W2) | Hand-offs grouped as needs me, agent is handling, resolved; transcript with the agent's summary; suggested reply; resolve with a required note; several conversations open at once | Resolving needs a note, the note and person are audited, the customer sees the reply only after the person sends it |
| **Approvals** (W3) | Count badge; approve or reject with a note; shows customer context, the exact action and why it needs a person; decided and expired lists | An approved action resumes the conversation once; a second decision on the same item is refused |
| **Customers** (W4, second release, decision 158) | Cross-channel timeline, facts the agents may use, staff notes, satisfaction; leads and reviewers by default; search only by customer reference or order number | Every open, reveal and edit is audited; a deletion request removes the record |
| **Pilot** (W5) | See `NorthCX_Pilot-Spec.md` | |
| **Assistants** (W6) | Catalog of predefined staff assistants: search, favourites, what each can see and do, start a chat, suggest a new one | An assistant that is not installed and released does not appear |
| **Search** (W7) | One search across knowledge, conversations, hand-offs and outputs; each result says why the person can see it | A result the person may not see never appears, including in counts |
| **Library** (W8) | Sources, documents, playbooks and canned answers; browse, search, out-of-date flags, propose edits | A proposed edit goes to a reviewer; it never changes a live source by itself |
| **Outputs** (W9) | Everything assistants made; filter by type, space and owner; versions; share to team; schedule; export | Each output shows who made it, the sources used and the model |
| **Spaces** (W10) | Instructions, sources, files, chats and outputs for one piece of work; private or team; each has its own memory | A private space is invisible to others, including to administrators of the Workspace |
| **Automations** (W11) | See `NorthCX_Automations-Spec.md` | |
| **Quality** (W12, leads and reviewers) | Review queue, scorecards, calibration, sampling rules, coaching notes | A reviewer's score and note are audited; the agent owner sees them |
| **Performance** (W13) | Mine and my team's figures: handled, resolved, approvals, response times, each with its denominator | A figure with no data says so instead of showing zero |
| **Notifications, availability, app switcher, theme** (W14) | A bell with what needs the person; an availability and workload control; a switcher between Workspace and Admin | Turning availability to away stops new hand-offs being offered to that person |

## 5. States and failures
Backend unavailable: read-only banner, drafts kept locally, no silent loss. Permission removed mid-session: the next request shows "no longer allowed" and the page refreshes its navigation. A conversation resolved by someone else while open: the page shows who and when and disables the resolve button. Offline: composer disabled with a reason.

## 6. Out of scope for the first release
Customers tab (second release); Outputs, Spaces, Automations, Quality and Performance (later releases, as their backends land); web search for assistants (later, off by default), live call assist, a mobile app, sharing outside the organization.

## 7. Decisions
None open. Per-space file limits are set by an administrator (decision 163). Decision 162: all twelve tabs are confirmed; the first release is Inbox, Approvals, Pilot, Assistants, Search and Library; Customers is second release; Outputs, Spaces, Automations, Quality and Performance follow as their backends land.
