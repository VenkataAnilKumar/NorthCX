import json

import httpx

from northcx.notify import WebhookNotifier, sign, verify
from northcx.outbox import InMemoryOutbox, Outbox, OutboxMessage

SECRET = "s3cret"


def notifier(handler, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return WebhookNotifier("https://hooks.test/northcx", SECRET, client=client, backoff=0, **kw)


async def test_payload_is_signed_and_verifiable():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(body=req.content, ts=req.headers["x-northcx-timestamp"], sig=req.headers["x-northcx-signature"])
        return httpx.Response(200)

    await notifier(handler).deliver(OutboxMessage("sess", "approval_result", {"reply": "hi"}, id=7))
    assert verify(SECRET, seen["ts"], seen["body"], seen["sig"])
    assert not verify("wrong", seen["ts"], seen["body"], seen["sig"])
    assert not verify(SECRET, seen["ts"], seen["body"] + b" ", seen["sig"])  # tampered body
    assert not verify(SECRET, seen["ts"], seen["body"], seen["sig"], now=float(seen["ts"]) + 10_000)  # replay window
    body = json.loads(seen["body"])
    assert (body["id"], body["sessionId"], body["kind"], body["payload"]) == (7, "sess", "approval_result", {"reply": "hi"})
    assert sign(SECRET, "1", b"x") != sign(SECRET, "2", b"x")


async def test_retries_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500 if len(calls) < 3 else 200)

    await notifier(handler).deliver(OutboxMessage("s", "k", {}))
    assert len(calls) == 3


async def test_gives_up_after_the_configured_attempts():
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ConnectError("down")

    try:
        await notifier(handler, attempts=2).deliver(OutboxMessage("s", "k", {}))
        raise AssertionError("should have failed")
    except RuntimeError as e:
        assert "failed" in str(e)
    assert len(calls) == 2


async def test_failed_pushes_stay_undelivered_until_flushed():
    up = {"ok": False}

    def handler(req):
        return httpx.Response(200 if up["ok"] else 503)

    box = Outbox(InMemoryOutbox(), notifier(handler, attempts=1))
    m = await box.publish("s", "approval_result", {"reply": "x"})
    assert [x.id for x in await box.repo.undelivered()] == [m.id]  # stored even though the push failed
    assert await box.flush() == 0
    up["ok"] = True
    assert await box.flush() == 1
    assert await box.repo.undelivered() == [] and await box.flush() == 0
    assert (await box.list("s"))[0].attempts == 3
