"""Telegram channel (C4), through the Bot API webhook.

Same engine as SMS and WhatsApp (opt-out words, rate limits, duplicates, hand-offs, privacy erasure). Only private chats are
answered; groups and channels are ignored. Telegram signs nothing, so a secret token you choose is registered with the webhook
(`setWebhook`'s `secret_token`) and every call must carry it in `X-Telegram-Bot-Api-Secret-Token`. The customer is the Telegram
user (`tg:<id>`); no phone number is involved. Photos and files are not read.
"""
from __future__ import annotations

import hmac
import json
import re
from typing import Any

import httpx

from ..choices import telegram_keyboard
from .email import InboundResult
from .sms import PermanentSendError, SmsChannel, SmsConfig, SmsNotifier, SmsSendError, phone_hash

_ID = re.compile(r"^[0-9]{1,16}$")
_TOKEN = re.compile(r"^[0-9]{5,16}:[A-Za-z0-9_-]{20,80}$")
_SECRET = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


class TelegramProvider:
    def __init__(self, token: str, secret: str, client: httpx.AsyncClient | None = None, base_url: str = "https://api.telegram.org"):
        if not _TOKEN.match(token or ""):
            raise ValueError("NORTHCX_TELEGRAM_TOKEN must be the bot token from BotFather")
        if not _SECRET.match(secret or ""):
            raise ValueError("NORTHCX_TELEGRAM_SECRET must be 16-256 letters, digits, - or _ (it is registered with the webhook as secret_token)")
        u = httpx.URL(base_url)
        if u.scheme != "https" and not (u.scheme == "http" and u.host in ("localhost", "127.0.0.1")):
            raise ValueError("the Telegram API address must be https")
        self._token, self._secret, self.base = token, secret, base_url.rstrip("/")
        self.bot_id = token.split(":", 1)[0]
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=False)

    def valid_secret(self, header: str) -> bool:
        return bool(header) and hmac.compare_digest(header.encode(), self._secret.encode())

    async def send(self, to: str, from_: str, body: str) -> str:
        chat = to.removeprefix("tg:")
        if not _ID.match(chat):
            raise ValueError("invalid Telegram chat id")
        try:
            r = await self._client.post(f"{self.base}/bot{self._token}/sendMessage", json={"chat_id": int(chat), "text": body, "disable_web_page_preview": True})
        except httpx.HTTPError as e:
            raise SmsSendError(f"could not send message: {type(e).__name__}") from None  # (the error text can contain the bot token in the address)
        if 400 <= r.status_code < 500 and r.status_code != 429:  # the user blocked the bot, the chat is gone, ...
            raise PermanentSendError(f"the message was refused by Telegram ({r.status_code})")
        if r.status_code >= 300:
            raise SmsSendError(f"could not send message: provider returned {r.status_code}")
        try:
            return str(r.json()["result"]["message_id"])
        except (ValueError, KeyError, TypeError):
            return ""


async def _send_choices(self: TelegramProvider, to: str, from_: str, body: str, choices: list[str]) -> str:
    """The reply with its options as an inline keyboard, one button per row."""
    chat = to.removeprefix("tg:")
    if not _ID.match(chat):
        raise ValueError("invalid Telegram chat id")
    try:
        r = await self._client.post(f"{self.base}/bot{self._token}/sendMessage", json={"chat_id": int(chat), "text": body, "disable_web_page_preview": True, "reply_markup": telegram_keyboard(choices)})
    except httpx.HTTPError as e:
        raise SmsSendError(f"could not send message: {type(e).__name__}") from None
    if 400 <= r.status_code < 500 and r.status_code != 429:
        raise PermanentSendError(f"the message was refused by Telegram ({r.status_code})")
    if r.status_code >= 300:
        raise SmsSendError(f"could not send message: provider returned {r.status_code}")
    try:
        return str(r.json()["result"]["message_id"])
    except (ValueError, KeyError, TypeError):
        return ""


async def _answer_callback(self: TelegramProvider, callback_id: str) -> None:
    """Tell Telegram the tap was received, so the button stops showing a spinner."""
    try:
        r = await self._client.post(f"{self.base}/bot{self._token}/answerCallbackQuery", json={"callback_query_id": callback_id})
    except httpx.HTTPError as e:
        raise SmsSendError(f"could not answer the tap: {type(e).__name__}") from None
    if r.status_code >= 300:
        raise SmsSendError(f"could not answer the tap: provider returned {r.status_code}")


TelegramProvider.send_choices = _send_choices  # type: ignore[attr-defined]
TelegramProvider.answer_callback = _answer_callback  # type: ignore[attr-defined]


def parse_update(raw: bytes) -> dict[str, Any] | None:
    """The message in an update, or None if there is nothing to answer (edits, groups, channel posts, bots, other update kinds)."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError("unreadable request") from None
    if not isinstance(data, dict) or not isinstance(data.get("update_id"), int):
        raise ValueError("not a Telegram update")
    tap = data.get("callback_query")
    if isinstance(tap, dict):  # a button the customer tapped: its data is the option's own words
        m, callback = tap.get("message"), tap.get("id") if isinstance(tap.get("id"), str) else None
        sender, text = tap.get("from"), tap.get("data") if isinstance(tap.get("data"), str) else ""
        chat = m.get("chat") if isinstance(m, dict) else None
        if callback is None or not isinstance(chat, dict) or chat.get("type") != "private" or not isinstance(sender, dict) or sender.get("is_bot"):
            return None
        uid = sender.get("id")
        if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0 or chat.get("id") != uid:
            return None
        return {"id": f"tg:{data['update_id']}", "user": f"tg:{uid}", "text": text, "media": 0, "callback": callback}
    m = data.get("message")
    if not isinstance(m, dict):
        return None
    chat, sender = m.get("chat"), m.get("from")
    if not isinstance(chat, dict) or chat.get("type") != "private" or not isinstance(sender, dict) or sender.get("is_bot"):
        return None
    uid = sender.get("id")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0 or not isinstance(chat.get("id"), int) or chat["id"] != uid:
        return None
    text = m.get("text") if isinstance(m.get("text"), str) else (m.get("caption") if isinstance(m.get("caption"), str) else "")
    media = 0 if isinstance(m.get("text"), str) else sum(1 for k in ("photo", "document", "video", "audio", "voice", "sticker", "animation", "video_note") if k in m)
    return {"id": f"tg:{data['update_id']}", "user": f"tg:{uid}", "text": text, "media": media}


class TelegramNotifier(SmsNotifier):
    SPLIT = 3500


class TelegramChannel(SmsChannel):
    CHANNEL, PREFIX, REPLY_KIND = "telegram", "tg-", "telegram_reply"

    def __init__(self, runtime: Any, agents: Any, repo: Any, provider: TelegramProvider, config: SmsConfig):
        super().__init__(runtime, agents, repo, provider, config)  # config.from_number is the bot's numeric id

    def authentic(self, header: str) -> bool:  # type: ignore[override]
        return self.provider.valid_secret(header)

    async def receive_body(self, raw: bytes) -> list[InboundResult]:
        m = parse_update(raw)
        if m is None:
            return []
        if m.get("callback"):
            try:
                await self.provider.answer_callback(m["callback"])
            except SmsSendError:
                pass  # the spinner may stay, but the tap is still the customer's answer and is handled below
        async with self._lock(f"msg:{m['id']}"):
            if await self.repo.has_message(m["id"]):
                return [InboundResult("duplicate", reason="already handled")]
            res = await self._handle(m["user"], m["text"].strip(), m["media"])
            outcome = res.status if res.status != "ignored" else f"ignored:{res.reason}"
            await self.repo.record_message(m["id"], res.session_id or "-", "in", outcome[:32], m["user"] if res.session_id else phone_hash(m["user"])[:20])
            return [res]
