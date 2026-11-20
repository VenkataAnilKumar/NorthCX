"""Voice calls (C5, C6), independent of any telephony or speech provider.

A bridge (the company's Twilio/LiveKit/Vonage/SIP integration, which does the speech-to-text and text-to-speech) speaks a small JSON protocol with
NorthCX over a WebSocket: it sends what the caller said, key presses, silences and when playback ended; NorthCX answers with what to say, when to
stop talking, whether to record, and where to transfer. Everything that is about the conversation lives here: announcing that the caller is talking to
an automated agent, recording consent, barge-in, keeping spoken replies short and speakable, a keypad fallback, switching language mid-call,
hand-off to a phone queue (or a callback outside hours), silences, and latency.

Calls are never recorded unless the caller has agreed. A caller's number is not trusted as their identity by default, because caller ID can be faked.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .language import NAMES, conversation_language, detect


def refuse_shadow(agent: Any) -> None:
    """A caller hears the answer as it is spoken, so a person cannot approve it first: shadow mode is not available on voice. The caller is passed to a person."""
    if getattr(agent, "shadow", False):
        raise RuntimeError(f"Agent '{agent.id}' is in shadow mode, which cannot take voice calls; turn shadow mode off or use another agent for voice")


KEEPS = "keypad"
RECORDING_MODES = ("off", "consent")

# Fixed phrases the platform itself says, in the languages the call may use (English is the fallback).
PHRASES: dict[str, dict[str, str]] = {
    "en": {"disclosure": "Hello, you have reached {brand}. You are speaking with an automated assistant.", "consent_ask": "May we record this call to improve our service? Say yes or press 1. Say no or press 2.",
           "consent_unclear": "Sorry, I did not catch that. To allow recording say yes or press 1. Otherwise say no or press 2.", "recording_on": "Thank you. This call is being recorded.", "recording_off": "No problem. This call will not be recorded.",
           "how_help": "How can I help you today?", "filler": "One moment please.", "reprompt": "Are you still there?", "goodbye": "Thank you for calling. Goodbye.",
           "transfer": "I am transferring you to a teammate now.", "callback": "Our team is not available right now. A teammate will call you back.", "unknown_key": "Sorry, that key does not do anything. Press zero for a person.",
           "nothing_to_repeat": "There is nothing to repeat yet.", "too_long": "We have reached the time limit for this call. Thank you for calling. Goodbye.", "error": "Sorry, something went wrong. Let me connect you with a teammate."},
    "es": {"disclosure": "Hola, se ha comunicado con {brand}. Está hablando con un asistente automático.", "consent_ask": "¿Podemos grabar esta llamada para mejorar nuestro servicio? Diga sí o pulse 1. Diga no o pulse 2.",
           "consent_unclear": "Perdón, no le he entendido. Para permitir la grabación diga sí o pulse 1. Si no, diga no o pulse 2.", "recording_on": "Gracias. Esta llamada se está grabando.", "recording_off": "De acuerdo. Esta llamada no se grabará.",
           "how_help": "¿En qué puedo ayudarle hoy?", "filler": "Un momento, por favor.", "reprompt": "¿Sigue ahí?", "goodbye": "Gracias por llamar. Adiós.",
           "transfer": "Le paso ahora con una persona de nuestro equipo.", "callback": "Nuestro equipo no está disponible ahora. Una persona le devolverá la llamada.", "unknown_key": "Perdón, esa tecla no hace nada. Pulse cero para hablar con una persona.",
           "nothing_to_repeat": "Todavía no hay nada que repetir.", "too_long": "Hemos llegado al límite de tiempo de esta llamada. Gracias por llamar. Adiós.", "error": "Perdón, algo ha fallado. Le paso con una persona de nuestro equipo."},
    "fr": {"disclosure": "Bonjour, vous êtes en relation avec {brand}. Vous parlez à un assistant automatique.", "consent_ask": "Pouvons-nous enregistrer cet appel pour améliorer notre service ? Dites oui ou appuyez sur 1. Dites non ou appuyez sur 2.",
           "consent_unclear": "Désolé, je n'ai pas compris. Pour autoriser l'enregistrement dites oui ou appuyez sur 1. Sinon dites non ou appuyez sur 2.", "recording_on": "Merci. Cet appel est enregistré.", "recording_off": "Très bien. Cet appel ne sera pas enregistré.",
           "how_help": "Comment puis-je vous aider ?", "filler": "Un instant, s'il vous plaît.", "reprompt": "Êtes-vous toujours là ?", "goodbye": "Merci de votre appel. Au revoir.",
           "transfer": "Je vous passe un conseiller maintenant.", "callback": "Notre équipe n'est pas disponible pour le moment. Un conseiller vous rappellera.", "unknown_key": "Désolé, cette touche ne fait rien. Appuyez sur zéro pour parler à une personne.",
           "nothing_to_repeat": "Il n'y a encore rien à répéter.", "too_long": "Nous avons atteint la durée maximale de cet appel. Merci de votre appel. Au revoir.", "error": "Désolé, un problème est survenu. Je vous passe un conseiller."},
    "de": {"disclosure": "Guten Tag, Sie sind mit {brand} verbunden. Sie sprechen mit einem automatischen Assistenten.", "consent_ask": "Dürfen wir dieses Gespräch aufzeichnen, um unseren Service zu verbessern? Sagen Sie Ja oder drücken Sie 1. Sagen Sie Nein oder drücken Sie 2.",
           "consent_unclear": "Entschuldigung, das habe ich nicht verstanden. Für die Aufzeichnung sagen Sie Ja oder drücken Sie 1. Sonst sagen Sie Nein oder drücken Sie 2.", "recording_on": "Danke. Dieses Gespräch wird aufgezeichnet.", "recording_off": "Kein Problem. Dieses Gespräch wird nicht aufgezeichnet.",
           "how_help": "Wie kann ich Ihnen helfen?", "filler": "Einen Moment bitte.", "reprompt": "Sind Sie noch da?", "goodbye": "Danke für Ihren Anruf. Auf Wiederhören.",
           "transfer": "Ich verbinde Sie jetzt mit einem Mitarbeiter.", "callback": "Unser Team ist gerade nicht erreichbar. Ein Mitarbeiter ruft Sie zurück.", "unknown_key": "Entschuldigung, diese Taste hat keine Funktion. Drücken Sie null für einen Mitarbeiter.",
           "nothing_to_repeat": "Es gibt noch nichts zu wiederholen.", "too_long": "Die Zeit für diesen Anruf ist abgelaufen. Danke für Ihren Anruf. Auf Wiederhören.", "error": "Entschuldigung, es ist ein Fehler aufgetreten. Ich verbinde Sie mit einem Mitarbeiter."},
}
YES = {"yes", "yeah", "yep", "sure", "ok", "okay", "please", "si", "sí", "claro", "vale", "oui", "ouais", "ja", "klar", "bien", "sim", "certo"}
NO = {"no", "nope", "non", "nein", "nao", "não", "nah", "never"}
_URL = re.compile(r"https?://\S+|www\.\S+")
_MD = re.compile(r"[*_`#>~|]+")
_BULLET = re.compile(r"(?m)^\s*(?:[-•*]|\d+[.)])\s+")


def say_phrase(key: str, language: str, **fmt: str) -> str:
    return (PHRASES.get(language) or PHRASES["en"]).get(key, PHRASES["en"][key]).format(**fmt) if fmt else (PHRASES.get(language) or PHRASES["en"]).get(key, PHRASES["en"][key])


def speakable(text: str, limit: int = 600) -> str:
    """A reply made fit to be spoken: no markup, no links, lists read as sentences, kept short at a sentence end."""
    t = _URL.sub("", text)
    t = _BULLET.sub("", t)
    t = _MD.sub("", t)
    t = re.sub(r"\s*\n+\s*", ". ", t.strip())
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    if len(t) <= limit:
        return t
    cut = t.rfind(". ", 0, limit)
    return (t[: cut + 1] if cut > limit // 2 else t[:limit].rsplit(" ", 1)[0] + ".").strip()


def consent_answer(text: str) -> bool | None:
    words = set(re.findall(r"[\w']+", text.lower()))
    yes, no = bool(words & YES), bool(words & NO)
    return True if yes and not no else False if no and not yes else None


DEFAULT_STYLE = ("This is a phone call. Answer in one to three short spoken sentences. Never use lists, markdown, links or emoji. Say numbers and dates the way a person would say them. "
                 "Before you change anything for the caller, read back what you will do and ask them to confirm. If you did not understand, ask a short question.")


@dataclass
class VoiceConfig:
    agent_id: str
    brand: str = "our support line"
    default_language: str = "en"
    recording: str = "off"                     # off | consent
    transfer: dict[str, str] = field(default_factory=dict)  # queue name -> number to transfer to; "default" for the rest
    trust_caller_id: bool = False              # treat the caller's number as who they are (caller ID can be faked)
    filler_after: float = 1.5                  # seconds before "one moment" is said while the reply is prepared
    barge_in_min_chars: int = 3
    max_silence_prompts: int = 2
    max_minutes: float = 30.0

    def __post_init__(self) -> None:
        if self.recording not in RECORDING_MODES:
            raise ValueError(f"Voice recording must be one of {', '.join(RECORDING_MODES)}")
        for n in self.transfer.values():
            if not re.fullmatch(r"\+[1-9]\d{6,14}", n) and not re.fullmatch(r"sip:[^\s]+", n):
                raise ValueError(f"Voice transfer targets must be E.164 numbers (+15551234567) or sip: addresses, not '{n}'")
        if self.default_language not in NAMES:
            raise ValueError(f"Unknown voice default language '{self.default_language}'")


@dataclass
class CallRecord:
    call_id: str
    session_id: str
    agent_id: str
    caller_hash: str
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    outcome: str = "in_progress"               # in_progress | resolved | handed_off | callback | silence | caller_hung_up | time_limit | error
    consent: str = "not_asked"                 # not_asked | granted | refused | unclear
    recorded: bool = False
    turns: int = 0
    barge_ins: int = 0
    languages: list[str] = field(default_factory=list)
    handoff_id: str | None = None
    latency_ms: list[int] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        lat = sorted(self.latency_ms)
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None
        return {"callId": self.call_id, "sessionId": self.session_id, "agentId": self.agent_id, "startedAt": self.started_at, "endedAt": self.ended_at, "outcome": self.outcome,
                "consent": self.consent, "recorded": self.recorded, "turns": self.turns, "bargeIns": self.barge_ins, "languages": self.languages, "handoffId": self.handoff_id,
                "latencyMs": {"median": lat[len(lat) // 2] if lat else None, "p95": p95, "samples": len(lat)}}


class CallRepo(Protocol):
    async def save(self, c: CallRecord) -> None: ...
    async def get(self, call_id: str) -> CallRecord | None: ...
    async def recent(self, limit: int = 50) -> list[CallRecord]: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryCalls:
    def __init__(self) -> None:
        self.items: dict[str, CallRecord] = {}

    async def save(self, c: CallRecord) -> None:
        self.items[c.call_id] = c

    async def get(self, call_id: str) -> CallRecord | None:
        return self.items.get(call_id)

    async def recent(self, limit: int = 50) -> list[CallRecord]:
        return sorted(self.items.values(), key=lambda c: -c.started_at)[:limit]

    async def erase_session(self, session_id: str) -> int:
        gone = [k for k, c in self.items.items() if c.session_id == session_id]
        for k in gone:
            del self.items[k]
        return len(gone)


def caller_hash(number: str) -> str:
    return hashlib.sha256(("voice:" + number).encode()).hexdigest()


Send = Callable[[dict[str, Any]], Awaitable[None]]


class CallSession:
    """One phone call. Feed it the bridge's messages with `handle`; it sends actions through `send`."""

    def __init__(self, runtime: Any, resolve_agent: Callable[[str, str], Awaitable[Any]], cfg: VoiceConfig, repo: CallRepo, send: Send,
                 clock: Callable[[], float] = time.monotonic):
        self.rt, self.resolve_agent, self.cfg, self.repo, self.send, self.clock = runtime, resolve_agent, cfg, repo, send, clock
        self.rec: CallRecord | None = None
        self.state = "new"                      # new | consent | listening | thinking | transferring | ended
        self.playing = False                    # the bridge is playing something the caller can interrupt
        self.language = cfg.default_language
        self.customer_id: str | None = None
        self.session_id = ""
        self.last_say: str | None = None
        self.speaking_id: str | None = None
        self.speaking_text = ""
        self._turn: asyncio.Task | None = None
        self._queue: list[str] = []
        self._silence_prompts = 0
        self._consent_tries = 0
        self._started = 0.0
        self._lock = asyncio.Lock()

    # ---- helpers ----
    def _p(self, key: str, **fmt: str) -> str:
        return say_phrase(key, self.language, **fmt)

    async def _say(self, text: str, language: str | None = None, interruptible: bool = True) -> None:
        if self.state == "ended":
            return
        self.last_say = text
        self.speaking_id, self.speaking_text = uuid.uuid4().hex[:8], text
        self.playing = True
        await self.send({"type": "say", "id": self.speaking_id, "text": text, "language": language or self.language, "interruptible": interruptible})

    async def _save(self) -> None:
        if self.rec:
            await self.repo.save(self.rec)

    async def _finish(self, outcome: str) -> None:
        if self.rec and self.rec.outcome == "in_progress":
            self.rec.outcome = outcome
        if self.rec:
            self.rec.ended_at = time.time()
        self.state = "ended"
        await self._save()

    # ---- the bridge's messages ----
    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if self.state == "ended":
            return
        if kind == "start":
            await self._start(msg)
        elif self.state == "new":
            return                              # nothing counts before the call has started
        elif kind == "transcript":
            await self._transcript(str(msg.get("text", "")), bool(msg.get("final", True)), msg.get("language"))
        elif kind == "dtmf":
            await self._dtmf(str(msg.get("digits", "")))
        elif kind == "silence":
            await self._silence()
        elif kind == "speech_ended":
            await self._speech_ended(msg)
        elif kind == "end":
            await self._ended(str(msg.get("reason", "caller_hung_up")))

    async def _start(self, msg: dict[str, Any]) -> None:
        if self.state != "new":
            return
        call_id = str(msg.get("callId") or uuid.uuid4().hex)
        caller = str(msg.get("from") or "")
        self.session_id = f"voice-{call_id}"
        self._started = self.clock()
        lang = msg.get("language")
        if isinstance(lang, str) and lang in NAMES:
            self.language = lang
        self.customer_id = f"phone:{caller}" if self.cfg.trust_caller_id and caller else None
        self.rec = CallRecord(call_id, self.session_id, self.cfg.agent_id, caller_hash(caller) if caller else "", languages=[self.language])
        await self._save()
        if self.cfg.recording == "consent":
            self.state = "consent"
            await self._say(self._p("disclosure", brand=self.cfg.brand) + " " + self._p("consent_ask"))
        else:
            self.state = "listening"
            await self._say(self._p("disclosure", brand=self.cfg.brand) + " " + self._p("how_help"))

    def _heard(self, language: str | None) -> None:
        if language and language in NAMES and language != self.language:
            self.language = language
            if self.rec and language not in self.rec.languages:
                self.rec.languages.append(language)

    async def _transcript(self, text: str, final: bool, language: str | None) -> None:
        text = text.strip()
        if not text:
            return
        if self.playing and (final or len(text) >= self.cfg.barge_in_min_chars):
            await self._barge_in()
        if not final:
            return
        detected = detect(text) or (language if isinstance(language, str) else None)
        if self.state == "consent":
            self._heard(detected)
            await self._consent(consent_answer(text))
            return
        self._heard(detected)
        if self._max_time():
            await self._say(self._p("too_long"), interruptible=False)
            await self.send({"type": "hangup", "reason": "time_limit"})
            await self._finish("time_limit")
            return
        self._silence_prompts = 0
        self._queue.append(text)
        if self._turn is None or self._turn.done():
            self._turn = asyncio.ensure_future(self._drain())

    def _max_time(self) -> bool:
        return self.clock() - self._started > self.cfg.max_minutes * 60

    async def _barge_in(self) -> None:
        """The caller spoke over the agent: stop talking at once. What they actually heard is kept in the conversation."""
        if self.playing:
            await self.send({"type": "stop_speaking"})
            self.playing = False
            if self.rec:
                self.rec.barge_ins += 1

    async def _speech_ended(self, msg: dict[str, Any]) -> None:
        if msg.get("utteranceId") not in (None, self.speaking_id):
            return
        heard = msg.get("spokenChars")
        if msg.get("completed", True) is False and isinstance(heard, int) and 0 <= heard < len(self.speaking_text):
            await self._trim_history(self.speaking_text[:heard].rstrip() + " [interrupted]")
        self.playing = False

    async def _trim_history(self, kept: str) -> None:
        """If the caller cut the agent off, the saved reply is what they heard, so the agent does not assume they know the rest."""
        msgs = await self.rt.store.load_messages(self.session_id)
        for m in reversed(msgs):
            if m["role"] == "assistant" and isinstance(m["content"], (str, list)):
                m["content"] = kept
                await self.rt.store.save_messages(self.session_id, msgs)
                return

    async def _consent(self, answer: bool | None) -> None:
        if answer is None:
            self._consent_tries += 1
            if self._consent_tries < 2:
                await self._say(self._p("consent_unclear"))
                return
            answer = False
            self.rec.consent = "unclear"  # type: ignore[union-attr]
        elif self.rec:
            self.rec.consent = "granted" if answer else "refused"
        if answer:
            await self.send({"type": "record", "on": True})
            if self.rec:
                self.rec.recorded = True
        await self._save()
        self.state = "listening"
        await self._say(self._p("recording_on" if answer else "recording_off") + " " + self._p("how_help"))

    async def _dtmf(self, digits: str) -> None:
        for d in digits:
            if self.state == "consent":
                if d in "12":
                    await self._consent(d == "1")
                    return
                continue
            if d == "0":
                await self._barge_in()
                await self._person("The caller pressed 0 on the keypad to ask for a person.")
                return
            if d in "9*":
                await self._barge_in()
                await self._say(self.last_say or self._p("nothing_to_repeat"))
            elif d != "#":
                await self._say(self._p("unknown_key"))

    async def _silence(self) -> None:
        if self.state != "listening" or self.playing:
            return
        self._silence_prompts += 1
        if self._silence_prompts > self.cfg.max_silence_prompts:
            await self._say(self._p("goodbye"), interruptible=False)
            await self.send({"type": "hangup", "reason": "silence"})
            await self._finish("silence")
        else:
            await self._say(self._p("reprompt"))

    async def _ended(self, reason: str) -> None:
        await self._finish("caller_hung_up")

    # ---- a turn ----
    async def _drain(self) -> None:
        async with self._lock:
            while self._queue and self.state != "ended":
                text = self._queue.pop(0)
                if self._queue:                 # the caller said more while we were busy: answer once, to all of it
                    text = " ".join([text, *self._queue])
                    self._queue.clear()
                await self._one_turn(text)

    async def _one_turn(self, text: str) -> None:
        began = self.clock()
        self.state = "thinking"
        filler = asyncio.ensure_future(self._filler())
        try:
            agent = await self.resolve_agent(self.cfg.agent_id, self.session_id)
            if agent is None:
                raise RuntimeError("voice agent is not available")
            agent = await self.rt.active_agent(agent, self.session_id)
            refuse_shadow(agent)
            styles = {"voice": DEFAULT_STYLE, **agent.channel_styles}
            run = await self.rt.run(dataclasses.replace(agent, channel_styles=styles), self.session_id, text, self.customer_id, channel="voice")
        except Exception:
            filler.cancel()
            await self._say(self._p("error"), interruptible=False)
            await self._transfer(None, "error")
            return
        finally:
            filler.cancel()
        if self.rec:
            self.rec.turns += 1
        if self._queue:  # the caller spoke again before the answer was ready: it stays in the conversation but is not read out
            return
        lang = next((e.data.get("replyIn") for e in reversed(run.trace.events) if e.type == "language"), None)
        if lang and lang in NAMES:
            self._heard(lang)
        if self.rec and lang and lang not in self.rec.languages:
            self.rec.languages.append(lang)
        reply = speakable(run.reply) or self._p("how_help")
        if self.rec:
            self.rec.latency_ms.append(int((self.clock() - began) * 1000))
        self.state = "listening"
        await self._say(reply, lang or self.language)
        if run.status == "escalated" or run.status == "with_person":
            await self._transfer(run.handoff_id, "handoff")
        await self._save()

    async def _filler(self) -> None:
        await asyncio.sleep(self.cfg.filler_after)
        if self.state == "thinking":
            await self._say(self._p("filler"))

    async def _person(self, why: str) -> None:
        """The caller asked for a person (keypad). Recorded as a hand-off like any other."""
        agent = await self.resolve_agent(self.cfg.agent_id, self.session_id)
        run = await self.rt.escalate(agent, self.session_id, self.customer_id, why, "customer_request", why, channel="voice")
        if self.rec:
            self.rec.turns += 1
        await self._say(speakable(run.reply), self.language)
        await self._transfer(run.handoff_id, "handoff")

    async def _transfer(self, handoff_id: str | None, why: str) -> None:
        """Send the call to the phone queue for this hand-off, or, if the team is closed or no number is set, promise a callback."""
        queue, after_hours = None, False
        if handoff_id:
            h = await self.rt.handoffs.get(handoff_id)
            if h is not None:
                queue, after_hours = h.queue, h.after_hours
            if self.rec:
                self.rec.handoff_id = handoff_id
        number = self.cfg.transfer.get(queue or "") or self.cfg.transfer.get("default")
        if number and not after_hours:
            self.state = "transferring"
            await self.send({"type": "transfer", "to": number, "queue": queue})
            await self._finish("handed_off")
        else:
            await self._say(self._p("callback"), interruptible=False)
            await self.send({"type": "hangup", "reason": "callback"})
            await self._finish("callback")
