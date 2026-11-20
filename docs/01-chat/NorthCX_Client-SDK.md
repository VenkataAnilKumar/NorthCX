# NorthCX client SDK and chat widget

Status: **Built**. Updated: 2026-11-09. Master for: the browser SDK and widget. Built for the web (C7). Source in `src/sdk`; the server serves the built scripts at `/sdk/northcx-widget.js` and `/sdk/northcx-client.js`. No runtime dependencies.

## How a customer's browser talks to NorthCX

```
 customer's browser ──(1) "start a chat" ──► your server ──(2) POST /v1/chat-tokens (channel key)──► NorthCX
        ▲                                         │
        └──────────(3) {token, sessionId}─────────┘
 customer's browser ──(4) token in the Authorization header──► NorthCX  (chat, stream, upload, outbox, feedback)
```

Your server holds a **channel key** and decides who the customer is (`customerId`) and which conversation (`sessionId`). The browser only ever gets a short-lived token that works for that one conversation. The token cannot read traces, other conversations or anything in Studio. When it expires, the SDK asks your server for a new one for the same conversation.

## Quick start (drop-in widget)

1. Allow your site to call the API: set `NORTHCX_CORS_ORIGINS=https://www.example.com` on the NorthCX server (exact origins, no wildcards).
2. Add an endpoint to your server that mints tokens (below).
3. Put this on your page:

```html
<script src="https://api.example.com/sdk/northcx-widget.js"></script>
<northcx-chat base-url="https://api.example.com" agent="support" token-url="/chat-token" attachments rating title="Help"></northcx-chat>
```

Attributes: `base-url`, `agent`, `token-url` (your endpoint), `title`, `placeholder`, `attachments` (show the paperclip; the agent must accept attachments), `rating` (ask for a 1-5 rating after a reply), `poll-ms` (how often to look for a teammate's replies, default 4000), `credentials` (`same-origin` default, or `include` if your token endpoint uses cookies). When the agent offers options (`choices` in the reply), the widget shows them as buttons; choosing one sends its words. Events on the element: `northcx:reply`, `northcx:error`. Theme with CSS variables: `--northcx-primary`, `--northcx-bg`, `--northcx-text`, `--northcx-radius`, `--northcx-font`, `--northcx-height`; it follows the visitor's light or dark setting.

The widget renders everything with `textContent`, so nothing a customer, an agent or a teammate writes can inject markup. It is a labelled, keyboard-operable control with a polite live region for the conversation.

### The token endpoint on your server

It receives `{ "sessionId": "..." }` when renewing (empty on the first call) and answers what NorthCX returns.

```js
// Node (Express): decide who the customer is from YOUR login, never from the request body
app.post("/chat-token", async (req, res) => {
  const r = await fetch("https://api.example.com/v1/chat-tokens", {
    method: "POST",
    headers: { authorization: `Bearer ${process.env.NORTHCX_CHANNEL_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({ customerId: req.user.id, agent: "support", sessionId: req.body.sessionId, ttlSeconds: 3600 }),
  });
  res.status(r.status).json(await r.json());   // {token, sessionId, expiresAt, ...}
});
```

```python
# Python (FastAPI)
@app.post("/chat-token")
async def chat_token(body: dict, user=Depends(current_user)):
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.example.com/v1/chat-tokens", headers={"authorization": f"Bearer {CHANNEL_KEY}"},
                         json={"customerId": user.id, "agent": "support", "sessionId": body.get("sessionId"), "ttlSeconds": 3600})
    return JSONResponse(r.json(), status_code=r.status_code)
```

Anonymous visitors: omit `customerId`. Never put the channel key in the browser.

## SDK (build your own UI)

```js
import { NorthCXClient } from "https://api.example.com/sdk/northcx-client.js";   // or bundle it
const chat = new NorthCXClient({
  baseUrl: "https://api.example.com", agent: "support",
  getToken: async (prev) => (await fetch("/chat-token", { method: "POST", body: JSON.stringify(prev ?? {}) })).json(),
});
const reply = await chat.send("Where is my order?", { onDelta: (t) => append(t), onProgress: (tool) => showWorking(tool) });
const file = await chat.upload(fileInput.files[0]);                 // picture, PDF or text, if the agent accepts them
await chat.send("What is wrong with this?", { attachments: [file.id] });
const stop = chat.watch((m) => { if (m.kind === "person_reply") show(m.reply); });   // a teammate's replies
await chat.rate(5, "quick help");
```

| Method | What it does |
|---|---|
| `start()` | gets a token if needed; returns the session id |
| `send(text, {attachments, onDelta, onProgress, signal, stream})` | sends a message; streams the reply when callbacks are given and the runtime supports it, otherwise one request with an idempotency key; resolves with the final reply `{reply, status, handoffId, ...}` |
| `upload(blob, name?)` | uploads one file, returns `{id, name, kind, size, ...}` |
| `messages(after)` / `watch(fn, {intervalMs})` | messages that arrive outside a request (teammate replies, approval results); `watch` polls politely and returns a stop function |
| `rate(1-5, comment?)` | rates the conversation |
| `close()` | stops polling |

Behaviour: an expired token is renewed once through `getToken` and the request repeated. Requests that are safe to repeat (non-streaming sends, which carry an idempotency key, and polling) are retried with back-off after network errors, 429 (honouring `Retry-After`) and 502/503/504; streams are never repeated automatically. Errors are `NorthCXError` with `status`, `code`, `message`. Reply `status` values: `completed`, `escalated` (a person was asked to take over), `needs_approval`, `with_person` (a person already has the conversation; the message was passed on).

## Mobile apps

The SDK is plain `fetch` and works in React Native and web views; React Native's `fetch` cannot stream, so call `send(text, { stream: false })` (you still get the full reply and typing indication can be shown locally). Native iOS and Android SDKs are not built: use the same REST calls, which are stable and documented in `../04-integrations/NorthCX_API-Design.md` (`POST /v1/agents/{id}/chat`, `PUT /v1/sessions/{id}/attachments`, `GET /v1/sessions/{id}/outbox`, `POST /v1/sessions/{id}/feedback`). Push notifications for teammate replies are not built; poll the outbox, or configure the outbox webhook (`NORTHCX_WEBHOOK_URL`) to push to your own notification service.

## Security notes

- Tokens are signed, expire (default one hour, at most a day), are limited to one conversation and one agent, and stop working when the channel key that minted them is revoked.
- CORS only lets a listed website's browser make the call; it does not replace the token. Without `NORTHCX_CORS_ORIGINS` no other site's browser can call the API.
- Limits that protect the service apply per conversation: message rate, upload size and count. A visitor who floods the chat only affects their own conversation.
- Pictures, and PDFs in file mode, are passed to the model unmasked; PDFs in `pdf_text` mode are read as text with personal data masked. Enable attachments per agent only where that is acceptable.

## Building

```bash
cd src/sdk && npm install && npm test && npm run build
```

`npm run build` writes `dist/` and copies the bundles into `src/backend/northcx/static/`, stamped with a hash of the sources; a backend test fails if the committed bundle is out of date. `npm run e2e` is `node e2e/smoke.mjs`: a real browser on a different origin chats through the widget, is handed to a teammate and receives their reply (needs a running server with `NORTHCX_CORS_ORIGINS=http://localhost:8080`).
