"""Choices: options an agent offers the customer to tap or answer with a number (docs/01-chat/NorthCX_Choices-and-Media.md).

The agent lists the built-in tool `offer_choices`; the runtime reads the options from the turn, checks them with the reply and returns
them in `RunResult.choices`. Each channel shows them its own way: buttons on the web widget, WhatsApp and Telegram, a numbered list
in the text on SMS and email. Choosing an option sends its words as the customer's next message."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .agent import Tool

OFFER_CHOICES = "offer_choices"
MIN_OPTIONS, MAX_OPTIONS, MAX_LABEL = 2, 10, 20
WHATSAPP_BUTTONS = 3          # up to this many options are reply buttons; more are a list
WHATSAPP_BODY = 1024          # the text of a button or list message
TELEGRAM_CALLBACK_BYTES = 64


class OfferChoices(BaseModel):
    options: list[str] = Field(description=f"{MIN_OPTIONS} to {MAX_OPTIONS} short answers the customer can tap, each at most {MAX_LABEL} characters. Write your question in your reply.")

    @field_validator("options")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = [o.strip() for o in v]
        if not MIN_OPTIONS <= len(out) <= MAX_OPTIONS:
            raise ValueError(f"offer {MIN_OPTIONS} to {MAX_OPTIONS} options")
        if any(not o or len(o) > MAX_LABEL for o in out):
            raise ValueError(f"each option must be 1 to {MAX_LABEL} characters")
        if len({o.casefold() for o in out}) != len(out):
            raise ValueError("each option must be different")
        return out


def offer_choices_tool() -> Tool:
    """Read-only: it changes nothing; the options are shown to the customer with the agent's reply."""
    return Tool(OFFER_CHOICES, "Offer the customer a few short options to tap or answer with, such as which order or yes or no. Ask the question in your reply; use this only when the answer is one of a few known choices.",
                OfferChoices, lambda d, ctx: {"offered": len(d.options)}, effect="read")


def history_note(choices: list[str]) -> str:
    """What the stored conversation keeps about the options, so a reply of "2" or a tapped button is understood on the next turn."""
    return "[Options offered: " + ", ".join(f"{i}. {c}" for i, c in enumerate(choices, 1)) + "]"


def numbered(reply: str, choices: list[str]) -> str:
    """The reply with the options as a numbered list, for a channel without buttons (SMS and email)."""
    if not choices:
        return reply
    return reply.rstrip() + "\n\n" + "\n".join(f"{i}. {c}" for i, c in enumerate(choices, 1)) + "\nReply with a number or write your own answer."


def whatsapp_payload(to: str, body: str, choices: list[str]) -> dict:
    """The WhatsApp Cloud API interactive message: 1 to 3 options are reply buttons, 4 to 10 a list."""
    if len(choices) <= WHATSAPP_BUTTONS:
        action = {"buttons": [{"type": "reply", "reply": {"id": f"c{i}", "title": c}} for i, c in enumerate(choices, 1)]}
        interactive = {"type": "button", "body": {"text": body[:WHATSAPP_BODY]}, "action": action}
    else:
        action = {"button": "Choose", "sections": [{"title": "Options", "rows": [{"id": f"c{i}", "title": c} for i, c in enumerate(choices, 1)]}]}
        interactive = {"type": "list", "body": {"text": body[:WHATSAPP_BODY]}, "action": action}
    return {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "interactive", "interactive": interactive}


def telegram_callback(choice: str) -> str:
    """A Telegram button carries at most 64 bytes of data; the option's own words are used, cut at a character boundary."""
    return choice.encode("utf-8")[:TELEGRAM_CALLBACK_BYTES].decode("utf-8", "ignore")


def telegram_keyboard(choices: list[str]) -> dict:
    return {"inline_keyboard": [[{"text": c, "callback_data": telegram_callback(c)}] for c in choices]}
