# NorthCX voice calls

Status: the conversation side of voice is built (C5, C6); the telephony and speech side is a bridge you connect. NorthCX does not ship speech-to-text, text-to-speech or telephony, and was not tested with a real phone line.

## Shape

```
 caller ── phone network ── your telephony bridge ──(WebSocket, JSON)── NorthCX  /v1/voice/stream
                            (does the speech-to-text and
                             text-to-speech: Twilio, LiveKit,
                             Vonage, SIP, a cloud speech API...)
```

The bridge turns audio into text and back. NorthCX decides what to say and when to stop talking, runs the agent (with all its tools, checks, approvals, journeys, languages and hand-offs), and keeps the call's record. Nothing about NorthCX depends on a particular provider.

## Switching it on

`NORTHCX_VOICE_AGENT=support` (the agent that answers), plus `NORTHCX_VOICE_BRAND`, `NORTHCX_VOICE_LANGUAGE`, `NORTHCX_VOICE_RECORDING`, `NORTHCX_VOICE_TRANSFER`, `NORTHCX_VOICE_TRUST_CALLER_ID` (see the deployment guide). The bridge connects to `wss://<server>/v1/voice/stream` with `Authorization: Bearer <channel key>` (a key with the `channel` role; other roles are refused, and the HTTP middleware does not cover WebSockets so this endpoint checks the key itself). One connection is one call.

## Messages from the bridge

| Message | Meaning |
|---|---|
| `{"type":"start","callId":"...","from":"+1555...","to":"+1555...","language":"es"}` | the call began; `language` is optional (for example from the number dialled). Nothing else counts before this |
| `{"type":"transcript","text":"...","final":false}` | what the caller is saying; partial results (`final:false`) can interrupt the agent when they are at least 3 characters; `final:true` ends an utterance and gets answered. Optional `language` |
| `{"type":"dtmf","digits":"0"}` | key presses: `0` a person, `9` or `*` repeat, `1`/`2` answer the recording question |
| `{"type":"silence","seconds":8}` | the caller has been quiet; only counted when nothing is playing |
| `{"type":"speech_ended","utteranceId":"...","completed":true,"spokenChars":123}` | playback of a `say` ended; if the caller cut it off, `completed:false` and `spokenChars` is how much of the text was heard (the conversation then keeps only that part) |
| `{"type":"end","reason":"..."}` | the caller hung up |

## Messages to the bridge

| Message | Meaning |
|---|---|
| `{"type":"say","id":"...","text":"...","language":"es","interruptible":true}` | speak this in that language (choose the voice from `language`) |
| `{"type":"stop_speaking"}` | the caller talked over the agent: stop playing now |
| `{"type":"record","on":true}` | start recording; only ever sent after the caller agreed |
| `{"type":"transfer","to":"+1555...","queue":"billing"}` | transfer the call (after queued speech has finished playing) |
| `{"type":"hangup","reason":"callback|silence|time_limit"}` | end the call (after queued speech has finished playing) |

Try it without any telephony: `python -m northcx.voice_sim ws://localhost:3000/v1/voice/stream --key <channel key>` lets you type what the caller says.

## What NorthCX handles for you

- **Disclosure.** Every call starts by saying the caller is speaking with an automated assistant and who they reached.
- **Recording consent.** With `NORTHCX_VOICE_RECORDING=consent` the caller is asked (say yes/no or press 1/2). Recording starts only after a clear yes; a no, or no clear answer after one retry, means no recording. Without that setting NorthCX never asks for or starts recording. Whether you need consent, and whose, depends on the countries involved: get legal advice before launch.
- **Speakable replies.** Voice calls add a style telling the agent to answer in one to three short sentences, no lists, markdown or links, and to read back what it will change and ask for confirmation first (an agent's own `channel_styles.voice` replaces it). Replies are also stripped of markup and links and shortened at a sentence end.
- **Barge-in.** If the caller speaks while something is playing, the agent stops at once. What the caller actually heard is what the conversation remembers. Words said while the agent is still thinking are answered together in the next reply; the unspoken answer stays in the conversation.
- **Waiting.** If the answer takes longer than 1.5 seconds the caller hears "One moment please" once. Reply time (from the end of the caller's utterance to the answer being ready) is recorded for every call.
- **Keypad.** `0` hands the call to a person (recorded as a hand-off with the trigger "The customer asked for a person"), `9`/`*` repeats the last thing said.
- **Hand-off.** When the agent or the keypad hands over, the call is transferred to the number for the hand-off's queue (`NORTHCX_VOICE_TRANSFER`, with a `default`). Outside the team's hours, or with no number configured, the caller is told a teammate will call back and the call ends; the hand-off stays open with the transcript for the callback.
- **Silence.** After 8 seconds of quiet (the bridge decides) the caller is asked if they are still there, twice, then the call ends politely. A call is capped at 30 minutes.
- **Languages (C6).** The language of each utterance is detected (the 13 languages in `NorthCX_Channels-and-Voice.md`) and the agent replies in it when its spec lists it; `say` carries the language so the bridge picks the right voice. The platform's own phrases (greeting, "one moment", goodbye...) exist in English, Spanish, French and German and follow the caller; other languages hear English for those phrases. Switching language mid-call works.

## Identity and privacy

- The caller's number is **not** trusted as who they are unless `NORTHCX_VOICE_TRUST_CALLER_ID=1`, because caller ID can be faked. By default the caller is anonymous: no customer facts, no memories, no customer-scoped tools. With it on, the customer is `phone:+E164`, the same identity SMS uses.
- The call record (`GET /v1/voice/calls`, permission `traces:read`) holds the outcome, consent, turns, barge-ins, languages, reply latency and a **hash** of the number; no audio and no number. The transcript is the conversation `voice-<callId>` (visible in Conversations and exportable/erasable like any other); erasing the conversation (`DELETE /v1/privacy/sessions/voice-<callId>`) erases the call record too.
- Audio recording, if you turn it on, happens in your bridge or telephony provider. Their retention, not NorthCX's, applies to the audio.

## Known limits

- Not tested with a real phone line or speech provider; latency depends heavily on your speech services and the model. The recorded reply latency does not include speech-to-text or text-to-speech time.
- Fixed phrases exist in four languages only. Outbound calls, call transfer with context hand-over to a human softphone, and call scripts for people (H6 for voice) are not built.
- A single caller utterance that spans several `final` transcripts is answered as separate turns unless they arrive while the agent is thinking.
