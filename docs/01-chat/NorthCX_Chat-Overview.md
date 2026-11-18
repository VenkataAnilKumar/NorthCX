# NorthCX Chat: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** How customers and staff talk to agents: the channels, the browser SDK and widget, streaming, and hand-off to people.

## Built
- Web chat: dependency-free browser SDK and `<northcx-chat>` widget, streamed replies, uploads, renewed chat tokens
- Email, SMS, WhatsApp and Telegram channels; voice through a telephony bridge the operator connects (no speech or telephony shipped)
- Attachments (pictures, PDFs, text) with content checks; replies in the customer's language (offline detection)
- Hand-off: queues with business hours, a package with transcript and facts, suggested replies for the person, person replies, hand-back to the agent, delivery to a helpdesk by signed webhook and an inbox adapter

## Gaps and next steps
- An AG-UI endpoint beside the existing streaming endpoint, and a richer chat UI on staff surfaces (design section 6)
- Shadow mode: the agent drafts, a person approves or edits before anything is sent (design section 13)
- Sending media and buttons on messaging channels; native voice is a separate decision

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Channels-and-Voice.md`](NorthCX_Channels-and-Voice.md) | Channels (master) |
| [`NorthCX_Voice.md`](NorthCX_Voice.md) | Voice bridge protocol |
| [`NorthCX_Client-SDK.md`](NorthCX_Client-SDK.md) | Browser SDK and widget |
| [`NorthCX_Handoff-and-Approvals-Spec.md`](NorthCX_Handoff-and-Approvals-Spec.md) | Hand-offs and approvals |
