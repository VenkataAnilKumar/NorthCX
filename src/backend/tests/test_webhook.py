import json
import time

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
    assert await box.flush() == 0  # too soon: the retry back-off has not passed
    up["ok"] = True
    assert await box.flush() == 0
    later = time.time() + 3600
    assert await box.flush(now=later) == 1
    assert await box.repo.undelivered() == [] and await box.flush(now=later) == 0
    assert (await box.list("s"))[0].attempts == 2


async def test_retries_back_off_and_eventually_stop():
    def handler(req):
        return httpx.Response(503)

    box = Outbox(InMemoryOutbox(), notifier(handler, attempts=1))
    m = await box.publish("s", "k", {})
    t = time.time()
    assert await box.flush(now=t + 10) == 0 and (await box.list("s"))[0].attempts == 1  # first back-off is 30 s
    await box.flush(now=t + 31)
    assert (await box.list("s"))[0].attempts == 2
    await box.flush(now=t + 31 + 59)  # the next wait is 60 s
    assert (await box.list("s"))[0].attempts == 2
    for i in range(20):  # keep failing until it gives up
        await box.flush(now=t + 10_000 * (i + 2), max_attempts=4)
    assert (await box.list("s"))[0].attempts == 4 and [x.id for x in await box.repo.undelivered()] == [m.id]  # kept, but not retried


async def test_one_failing_notifier_does_not_stop_the_others():
    from northcx.notify import CompositeNotifier
    seen = []

    class Good:
        async def deliver(self, message):
            seen.append(message.id)

    class Bad:
        async def deliver(self, message):
            raise RuntimeError("boom")

    box = Outbox(InMemoryOutbox(), CompositeNotifier(Bad(), Good()))
    await box.publish("s", "k", {})
    assert seen == [1] and len(await box.repo.undelivered()) == 1  # the good one ran; the message is retried because one failed
