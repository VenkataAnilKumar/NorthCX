# Choices on messaging channels, and what was dropped from WP 3.6

Status: stages 1 to 4 written 2026-11-20. **3.6a is built** (the tool, the runtime, the API, WhatsApp, Telegram, SMS and email; tested with fake providers and mock servers). 3.6b (the widget's buttons and its size limit, C2 for the web and C8) is not.

WP 3.6 in the plan read "the widget's AG-UI subset; media and buttons on messaging channels; the widget's size budget is kept". Research changed what is worth building.

## Research
| Found | Consequence |
|---|---|
| The widget talks to `chat/stream`, which already gives it streaming, tool progress and the hand-off and approval notices. AG-UI is an interface for *other people's* chat screens; the endpoint for them is built (WP 3.2) | **Dropped:** teaching the widget AG-UI would add bytes for a customer who gains nothing. Decision 207 |
| Nothing in the platform stores a file the agent could send: attachments are what customers upload, the knowledge base holds text, connectors return data | **Dropped for now:** sending images and documents has no source to send from. It returns when a real source exists (for example a shipping label from a connector), as its own work package with that source named |
| No number exists for "the widget's size budget" | **Added:** a measured limit and a test (C8) |
| WhatsApp and Telegram already read a tapped button as the customer's next message (WhatsApp `button_reply` and `list_reply`; Telegram has no callback handling yet) | Buttons are worth building: disambiguation ("which order?") and confirmation (yes or no) are the common cases where a tap beats typing, and a tap is read the way a typed word is |
| SMS and email have no buttons | They get a numbered list in text, so the same agent works everywhere |
| Replies on every channel come from `RunResult.reply` into the outbox; a draft in shadow mode is text | Choices travel with the reply in one place; shadow drafts stay text only (C7) |

## Requirements
| # | For | Requirement | Acceptance check |
|---|---|---|---|
| C1 | An author | An agent that lists the built-in tool `offer_choices` may offer the customer 2 to 10 options with its reply; each option is 1 to 20 characters; the tool does nothing else and is read-only | Spec and tool tests; invalid options are refused with the reason |
| C2 | A customer | Options appear as buttons on the web widget, WhatsApp and Telegram, and as a numbered list at the end of the text on SMS and email. Choosing one sends its words as the next message | Channel tests with fake providers; widget test |
| C3 | The company | The options are part of the reply for the agent's reply checks and for masking: a check that stops the reply stops them; they are offered only when the turn ends normally (not on a hand-off, a held action or a draft) | Tests: a blocking check; escalated and in-review turns carry none |
| C4 | The agent | The stored conversation notes which options were offered, so a reply of "2" on SMS or a tapped button is understood on the next turn | Test on stored messages |
| C5 | A developer | `choices` (a list of option texts) is in the chat, stream and AG-UI results and in outbox payloads; additive | Contract and drift tests |
| C6 | A customer on WhatsApp or Telegram | WhatsApp: 1 to 3 options as reply buttons, 4 to 10 as a list; a reply longer than the button body allows goes first as text. Telegram: an inline keyboard; a tap is read as the customer's message and acknowledged so the button stops spinning | Tests against the documented request shapes on mock servers |
| C7 | A reviewer | Shadow-mode drafts carry text only; the options are not offered while a person reviews | Test |
| C8 | A site owner | The widget bundle stays at or under 16,384 bytes (it is 12,710 bytes, 5,063 gzipped, on 2026-11-20); a test fails when it grows past it | The size test |
| C9 | A caller | Voice ignores options (the answer is spoken) | Test |

## Design
- **Tool.** `offer_choices(options: list[str])` is a registry tool with effect `read`. It returns `{"offered": n}`. The runtime reads the options from the turn's tool calls (the last call wins), checks them with the reply, and puts them in `RunResult.choices`.
- **History.** The assistant message that ends the turn gets a line the customer never sees on web, WhatsApp or Telegram and that SMS and email show as the numbered list: stored as `[Options offered: 1. X, 2. Y]`.
- **Channels.** A small function turns `(reply, choices)` into what each channel sends: the WhatsApp interactive payload, the Telegram keyboard, the numbered text. The SMS, WhatsApp and Telegram notifiers and the email sender call it; with no choices they send exactly what they send today.
- **Widget.** Buttons under the reply, built with `textContent` like everything else; a button sends its text through the normal send path and the buttons disappear once one is chosen or the customer types.

## Decision 207
The widget does not speak AG-UI, and media sending is not built. Both were in the plan; neither has a user who needs it now. The plan keeps one line saying why, and media comes back as a work package when a source of files exists.

## Limits and what is unverified
- The WhatsApp and Telegram request shapes follow the vendors' documentation as known to the author; they are tested against mock servers only. No Meta or Telegram account was available, so nothing was sent to either service. This is added to the release checklist as an item to verify before relying on it.
- Telegram's callback data is limited to 64 bytes: an option's own words are used and cut at a character boundary, so an option made of four-byte characters may arrive shortened.
- WhatsApp allows free-form and interactive messages only inside the 24-hour window, as for any reply.
