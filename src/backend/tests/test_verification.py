"""One-time-code identity checks: delivery only to addresses on file, limits, single use, and what a verified conversation unlocks."""
import json

import pytest

from examples.support_agent import registry, support_agent
from northcx.agent import ToolContext
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.spec import AgentSpec, BuildContext
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.verification import FACT, InMemoryVerify, OtpService, VerifyConfig, VerifyRefused, mask_destination, verification_tools

FACTS = {"email": "jane.doe@example.com", "phone": "+14155550123"}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        return InMemoryVerify()
    from northcx.db import PgVerify
    return PgVerify(request.getfixturevalue("engine"))


def service(repo, **cfg):
    clock, sent = Clock(), []

    async def email(to, body):
        sent.append(("email", to, body))

    async def sms(to, body):
        sent.append(("sms", to, body))
    svc = OtpService(repo, {"email": email, "sms": sms}, b"k" * 32, VerifyConfig(**cfg), clock)
    return svc, clock, sent


def code_of(sent):
    return sent[-1][2].split("code is ")[1][:6]


async def test_a_code_goes_only_to_the_address_on_file_and_verifies_once(repo):
    svc, clock, sent = service(repo)
    out = await svc.start("s1", "cust-1", "email", FACTS)
    assert out["to"] == "j***@example.com" and sent[0][:2] == ("email", "jane.doe@example.com") and "jane.doe" not in json.dumps(out)
    assert not await svc.is_verified("s1", "cust-1")
    assert (await svc.check("s1", "cust-1", code_of(sent) + " "))["verified"] is True
    assert await svc.is_verified("s1", "cust-1") and not await svc.is_verified("s1", "someone-else") and not await svc.is_verified("s2", "cust-1")
    with pytest.raises(VerifyRefused):
        await svc.check("s1", "cust-1", code_of(sent))  # single use
    clock.t += 1801
    assert not await svc.is_verified("s1", "cust-1")  # verification lapses


async def test_nothing_readable_is_stored(repo):
    svc, clock, sent = service(repo)
    await svc.start("s1", "cust-1", "sms", FACTS)
    rec = await repo.get("s1")
    blob = json.dumps(rec.__dict__, default=str)
    assert code_of(sent) not in blob and "+14155550123" not in blob and len(rec.code_hash) == 64 and len(rec.dest_hash) == 64


async def test_refusals_for_missing_addresses_unknown_channels_and_unidentified_customers(repo):
    svc, *_ = service(repo)
    for args, msg in ((("s1", None, "email", FACTS), "not tied to a known customer"), (("s1", "c", "fax", FACTS), "cannot be sent by fax"),
                      (("s1", "c", "email", {}), "no email address on file"), (("s1", "c", "sms", {"phone": "0123"}), "no sms address on file"),
                      (("s1", "c", "email", {"email": "not-an-address"}), "no email address on file")):
        with pytest.raises(VerifyRefused, match=msg):
            await svc.start(*args)


async def test_limits_on_resending_and_per_hour_and_wrong_guesses(repo):
    svc, clock, sent = service(repo, max_sends_per_hour=2, max_attempts=3)
    await svc.start("s1", "c", "email", FACTS)
    with pytest.raises(VerifyRefused, match="wait"):
        await svc.start("s1", "c", "email", FACTS)
    clock.t += 61
    await svc.start("s1", "c", "email", FACTS)
    clock.t += 61
    with pytest.raises(VerifyRefused, match="Too many codes"):
        await svc.start("s1", "c", "email", FACTS)
    good = code_of(sent)
    wrong = "000000" if good != "000000" else "111111"
    r = await svc.check("s1", "c", wrong)
    assert r == {"verified": False, "attemptsLeft": 2, "reason": "That code is not right"}
    await svc.check("s1", "c", wrong)
    r = await svc.check("s1", "c", wrong)
    assert r["attemptsLeft"] == 0 and "cancelled" in r["reason"]
    with pytest.raises(VerifyRefused, match="no active code"):
        await svc.check("s1", "c", good)  # the right code no longer works after too many wrong guesses


async def test_codes_expire_and_belong_to_one_customer_and_one_conversation(repo):
    svc, clock, sent = service(repo)
    await svc.start("s1", "c", "email", FACTS)
    with pytest.raises(VerifyRefused):
        await svc.check("s1", "other", code_of(sent))
    with pytest.raises(VerifyRefused):
        await svc.check("s2", "c", code_of(sent))
    assert (await svc.check("s1", "c", "12ab"))["verified"] is False  # malformed input does not count as the code
    clock.t += 601
    with pytest.raises(VerifyRefused, match="no active code"):
        await svc.check("s1", "c", code_of(sent))
    with pytest.raises(VerifyRefused, match="different customer"):
        await svc.start("s1", "other", "email", FACTS)


async def test_a_failing_sender_leaves_no_usable_code_and_says_so_calmly(repo):
    async def boom(to, body):
        raise RuntimeError("smtp password was wrong: hunter2")
    svc = OtpService(repo, {"email": boom}, b"k" * 32, clock=Clock())
    with pytest.raises(VerifyRefused) as ei:
        await svc.start("s1", "c", "email", FACTS)
    assert "hunter2" not in str(ei.value) and "hand-off" in str(ei.value)
    with pytest.raises(VerifyRefused, match="no active code"):
        await svc.check("s1", "c", "123456")


def test_masking():
    assert mask_destination("email", "jane@example.com") == "j***@example.com" and mask_destination("sms", "+14155550123") == "*********123"


async def test_the_tools_use_only_company_facts_and_report_refusals_as_results():
    svc, clock, sent = service(InMemoryVerify())
    send, check = verification_tools(svc)
    ctx = ToolContext("s1", "cust-1", None, facts=FACTS)
    out = await send.run(send.input_model(channel="email"), ctx)
    assert out["sent"] is True and sent[0][1] == "jane.doe@example.com"
    out = await send.run(send.input_model(channel="sms"), ToolContext("s1", "cust-1", None, facts={}))
    assert out["sent"] is False and "no sms address on file" in out["reason"]
    assert send.input_model.model_json_schema()["properties"].keys() == {"channel"}  # there is no field for choosing an address
    assert (await check.run(check.input_model(code="000000"), ctx))["verified"] in (True, False)
    assert send.effect == "write" and check.effect == "write"


# ---- inside a conversation ----
class Company:
    """The company's own system: reports the address on file, and (wrongly) tries to claim the customer is verified."""
    def __init__(self, claim=False):
        self.claim = claim

    async def fetch(self, customer_id, session_id):
        return dict(FACTS, **({FACT: "yes"} if self.claim else {}))


def refund_agent(svc):
    r = registry()
    for t in verification_tools(svc):
        r.tool(t)
    spec = AgentSpec(id="shop", instructions="You help Acme customers. Verify identity before refunds.", tools=["lookup_order", "issue_refund", "send_verification_code", "check_verification_code"],
                     tool_scopes={"issue_refund": {"facts": {FACT: ["yes"]}}})
    assert r.validate(spec) == []
    return r.build(spec, BuildContext())


def results(trace, name):
    return [e.data for e in trace.events if e.type == "tool_result" and e.data.get("name") == name]


async def test_a_refund_is_refused_until_the_customer_proves_who_they_are_and_then_allowed():
    from northcx.context import CachedContext
    svc, clock, sent = service(InMemoryVerify())
    agent = refund_agent(svc)
    refund = lambda req: tool_call("issue_refund", {"order_id": "1042", "amount": 20}, "r")  # noqa: E731
    script = [refund, text("I need to verify you first."),
              lambda req: tool_call("send_verification_code", {"channel": "email"}, "s"), text("I sent a code."),
              lambda req: tool_call("check_verification_code", {"code": code_of(sent)}, "c"), refund, text("Refunded.")]
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), context=CachedContext(Company(claim=True)))  # the company's claim of "verified" must be ignored
    rt.verification = svc
    t1 = await rt.traces.get((await rt.run(agent, "s1", "refund order 1042", "cust-1")).trace_id)
    assert any("Blocked by policy" in json.dumps(e.data) or "not available" in json.dumps(e.data) for e in t1.events) and not results(t1, "issue_refund")
    await rt.run(agent, "s1", "yes please send a code", "cust-1")
    assert sent and sent[0][:2] == ("email", "jane.doe@example.com")
    t3 = await rt.traces.get((await rt.run(agent, "s1", f"the code is {code_of(sent)}", "cust-1")).trace_id)
    assert results(t3, "check_verification_code")[0]["output"]["verified"] is True
    assert results(t3, "issue_refund") and "refund" in json.dumps(results(t3, "issue_refund")[0]).lower()  # allowed in the same turn the code was accepted
    blob = json.dumps([e.data for e in t3.events if e.type == "tool_call"])
    assert code_of(sent) not in blob and "******" in blob  # the typed code is not kept in the trace of the tool call
    assert not any(code_of(sent) in json.dumps(e.data) for e in t1.events)


async def test_verification_is_per_conversation_and_lapses():
    from northcx.context import CachedContext
    svc, clock, sent = service(InMemoryVerify())
    rt = Runtime(ScriptedLLM([tool_call("send_verification_code", {"channel": "email"}, "s"), text("sent")] + [text("ok")] * 4), InMemoryStore(), TraceStore(), context=CachedContext(Company()))
    rt.verification = svc
    agent = refund_agent(svc)
    await rt.run(agent, "s1", "send me a code", "cust-1")
    await svc.check("s1", "cust-1", code_of(sent))
    r1 = await rt.run(agent, "s1", "hello", "cust-1")
    assert '"identity_verified": "yes"' in rt.llm.requests[-1].system and r1.status == "completed"
    await rt.run(agent, "s2", "hello", "cust-1")
    assert "identity_verified" not in rt.llm.requests[-1].system  # another conversation is not verified
    clock.t += 3600
    await rt.run(agent, "s1", "hello again", "cust-1")
    assert "identity_verified" not in rt.llm.requests[-1].system  # and verification lapses


async def test_without_the_feature_a_claimed_verification_is_still_stripped():
    from northcx.context import CachedContext
    rt = Runtime(ScriptedLLM([text("hi")]), InMemoryStore(), TraceStore(), context=CachedContext(Company(claim=True)))
    await rt.run(support_agent(), "s1", "hello", "cust-1")
    assert "identity_verified" not in rt.llm.requests[0].system
