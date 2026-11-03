"""Language detection and same-language replies (R9).

Detection is deliberate and offline: non-Latin scripts are recognised by their characters, and the main Latin-script languages by common
function words. It returns nothing when unsure (a one-word message, a mix), and the conversation then keeps the language it had. An agent
lists the languages it is written and tested for; a customer writing in another language gets the first (default) one, and the agent is
told so it can offer a person.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NAMES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "it": "Italian", "nl": "Dutch",
         "ru": "Russian", "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi"}

# Frequent words that are rare in the other listed languages. Words shared by several languages are left out on purpose.
WORDS = {
    "en": "the and is are you your with this that have for not what can please thanks hello where when my order refund help need".split(),
    "es": "el la los las es son usted con esto que tengo para por no qué puedo gracias hola dónde cuándo mi pedido reembolso ayuda necesito quiero".split(),
    "fr": "le la les est sont vous votre avec ceci que j'ai pour pas quoi puis-je merci bonjour où quand ma commande remboursement aide besoin je suis".split(),
    "de": "der die das ist sind sie ihre mit dies dass ich habe für nicht was kann bitte danke hallo wo wann meine bestellung rückerstattung hilfe brauche".split(),
    "pt": "o os é são você seu com isto que tenho para por não o-que posso obrigado olá onde quando meu pedido reembolso ajuda preciso quero uma".split(),
    "it": "il lo gli è sono lei suo con questo che ho per non cosa posso grazie ciao dove quando mio ordine rimborso aiuto ho bisogno vorrei una".split(),
    "nl": "de het een is zijn u uw met dit dat ik heb voor niet wat kan alstublieft dank hallo waar wanneer mijn bestelling terugbetaling hulp nodig".split(),
}
MIN_WORDS, MIN_MARGIN = 3, 2
_TOKEN = re.compile(r"[\w'’-]+", re.UNICODE)


@dataclass(frozen=True)
class Detected:
    code: str
    confident: bool


def _script(text: str) -> str | None:
    counts: dict[str, int] = {}
    letters = 0
    for ch in text:
        if not ch.isalpha():
            continue
        letters += 1
        name = unicodedata.name(ch, "")
        for key, label in (("HIRAGANA", "ja"), ("KATAKANA", "ja"), ("HANGUL", "ko"), ("CJK", "zh"), ("CYRILLIC", "ru"), ("ARABIC", "ar"), ("DEVANAGARI", "hi")):
            if name.startswith(key):
                counts[label] = counts.get(label, 0) + 1
                break
    if not letters or not counts:
        return None
    if counts.get("ja"):  # Japanese text mixes kana with Han characters
        return "ja"
    best, n = max(counts.items(), key=lambda kv: kv[1])
    return best if n / letters >= 0.4 else None


def detect(text: str) -> str | None:
    """The language code, or None when the text is too short or too mixed to say."""
    text = (text or "").strip()[:2000]
    script = _script(text)
    if script:
        return script
    tokens = [t.lower().replace("’", "'") for t in _TOKEN.findall(text)]
    if len(tokens) < MIN_WORDS:
        return None
    scores = {code: sum(1 for t in tokens if t in words) for code, words in ((c, set(w)) for c, w in WORDS.items())}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (top, s1), (_, s2) = ranked[0], ranked[1]
    return top if s1 >= 2 and s1 - s2 >= MIN_MARGIN else None


def conversation_language(message: str, history: list[str]) -> str | None:
    """The language of this message, else of the most recent earlier customer message that had a clear one."""
    return detect(message) or next((d for d in (detect(h) for h in reversed(history)) if d), None)


@dataclass(frozen=True)
class Choice:
    detected: str | None  # what the customer is writing in, if known
    reply_in: str  # what the agent should write in
    supported: bool


def choose(detected: str | None, supported: list[str]) -> Choice:
    default = supported[0]
    if detected is None:
        return Choice(None, default, True)
    if detected in supported:
        return Choice(detected, detected, True)
    return Choice(detected, default, False)


def instruction(choice: Choice) -> str:
    name = NAMES.get(choice.reply_in, choice.reply_in)
    if choice.supported:
        return f"\n\nLanguage: write every reply to the customer in {name}, including questions and error messages. Keep names, order numbers and tool inputs exactly as given."
    other = NAMES.get(choice.detected or "", choice.detected or "another language")
    return (f"\n\nLanguage: the customer is writing in {other}, which this service does not support yet. Reply in {name}, say briefly in {name} that you can help in "
            f"{name} and offer to bring in a person if they prefer. Keep names, order numbers and tool inputs exactly as given.")


def check_codes(codes: list[str]) -> list[str]:
    bad = [c for c in codes if c not in NAMES]
    if bad:
        raise ValueError(f"Unknown language code(s) {', '.join(bad)} (known: {', '.join(sorted(NAMES))})")
    if len(set(codes)) != len(codes):
        raise ValueError("A language is listed twice")
    return codes
