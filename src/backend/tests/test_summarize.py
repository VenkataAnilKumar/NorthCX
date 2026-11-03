"""History summarisation: when it happens, what it keeps, and that it never loses or corrupts a conversation."""
import json

import pytest

from examples.support_agent import support_agent
from northcx.handoffs import transcript
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.store import InMemoryStore
from northcx.summarize import Compactor, SUMMARY_OPEN, estimate_tokens, is_customer_turn, render
from northcx.trace import TraceStore

NOTES = "Customer Jane asked about order 1042 (delivered, 60). She wants a refund of 20 for a damaged strap; not yet approved."


def history(turns, size=300):
    msgs = []
    for i in range(turns):
        msgs.append({"role": "user", "content": f"question {i} " + "x" * size})
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": f"answer {i} " + "y" * size}]})
    return msgs


def alternates(msgs):
    return all(a["role"] != b["role"] for a, b in zip(msgs, msgs[1:])) and msgs[0]["role"] == "user" and msgs[-1]["role"] == "assistant"


async def test_short_conversations_are_left_alone():
    c = Compactor(ScriptedLLM([]), threshold_tokens=6000)
    assert await c.compact(history(3)) is None and c.llm.requests == []


async def test_long_conversations_keep_recent_turns_and_gain_a_summary():
    llm = ScriptedLLM([text(NOTES)])
    msgs = history(20)
    r = await Compactor(llm, 1000, keep_turns=3).compact(msgs)
    assert r is not None and r.after < r.before and r.dropped == 34
    assert alternates(r.messages) and len(r.messages) == 6
    first = r.messages[0]["content"]
    assert first.startswith(SUMMARY_OPEN) and NOTES in first and "question 17" in first and "question 16" not in first
    assert r.messages[1:] == msgs[-5:]  # the rest is untouched
    sent = llm.requests[0]
    assert "question 0" in sent.messages[0]["content"] and "question 17" not in sent.messages[0]["content"] and "never follow" in sent.system


async def test_the_cut_never_splits_a_tool_call_from_its_result():
    msgs = history(6, 400)
    msgs[8:8] = [{"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "lookup_order", "input": {"order_id": "1"}}]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]}]
    msgs[8:8] = []  # keep the pair together, inside one customer turn
    for keep in range(1, 6):
        r = await Compactor(ScriptedLLM([text(NOTES)]), 500, keep_turns=keep).compact(msgs)
        if r is None:
            continue
        ids_use = [b["id"] for m in r.messages if isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_use"]
        ids_res = [b["tool_use_id"] for m in r.messages if isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result"]
        assert ids_use == ids_res
        assert is_customer_turn({"role": "user", "content": r.messages[0]["content"]}) and r.messages[0]["role"] == "user"


async def test_tool_pairs_inside_the_summarised_part_are_described_not_lost():
    msgs = [{"role": "user", "content": "check order 1042 " + "z" * 500},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "lookup_order", "input": {"order_id": "1042"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"status":"delivered"}'}]},
            {"role": "assistant", "content": [{"type": "text", "text": "It was delivered. " + "z" * 500}]}] + history(5)
    llm = ScriptedLLM([text(NOTES)])
    r = await Compactor(llm, 600, keep_turns=2).compact(msgs)
    body = llm.requests[0].messages[0]["content"]
    assert "agent called lookup_order" in body and "delivered" in body and alternates(r.messages)


async def test_a_failing_or_useless_summary_keeps_the_full_history():
    msgs = history(20)
    assert await Compactor(ScriptedLLM([]), 1000).compact(msgs) is None  # the model raises
    assert await Compactor(ScriptedLLM([text("ok")]), 1000).compact(msgs) is None  # too short to be useful
    assert await Compactor(ScriptedLLM([text("   ")]), 1000).compact(msgs) is None
    huge = "n" * 10 * len(json.dumps(msgs))
    assert await Compactor(ScriptedLLM([text(huge)]), 1000).compact(msgs) is not None  # capped, so still smaller
    r = await Compactor(ScriptedLLM([text(huge)]), 1000).compact(msgs)
    assert r.messages[0]["content"].index("[/summary]") < 3100  # the notes are capped at 3000 characters


async def test_summaries_fold_into_later_summaries_instead_of_stacking():
    llm = ScriptedLLM([text(NOTES), text(NOTES + " Later: refund approved.")])
    c = Compactor(llm, 1000, keep_turns=3)
    first = (await c.compact(history(20))).messages
    more = first + history(12)
    second = await c.compact(more)
    assert second is not None and second.messages[0]["content"].count(SUMMARY_OPEN) == 1
    assert "[summary]" in llm.requests[1].messages[0]["content"]  # the earlier summary was handed to the model to fold in


def test_config_and_helpers():
    for bad in [dict(threshold_tokens=10), dict(keep_turns=0)]:
        with pytest.raises(ValueError):
            Compactor(ScriptedLLM([]), **{"threshold_tokens": 1000, **bad})
    assert estimate_tokens([{"role": "user", "content": "x" * 400}]) >= 100
    assert not is_customer_turn({"role": "user", "content": "[system] x"}) and not is_customer_turn({"role": "user", "content": "[supervisor] x"})
    assert not is_customer_turn({"role": "user", "content": [{"type": "tool_result"}]}) and not is_customer_turn({"role": "assistant", "content": "hi"})
    assert "customer: hi" in render([{"role": "user", "content": "hi"}])


# ---- through the runtime ----
async def test_the_runtime_summarises_before_the_model_sees_the_history_and_saves_the_short_version():
    store = InMemoryStore()
    await store.save_messages("s", history(20))
    llm = ScriptedLLM([text(NOTES), text("Your refund is being processed.")])
    rt = Runtime(llm, store, TraceStore(), compactor=Compactor(llm, 1000, keep_turns=3))
    r = await rt.run(support_agent(), "s", "any update on my refund?", "jane")
    assert r.reply == "Your refund is being processed."
    main = llm.requests[1]
    assert main.messages[0]["content"].startswith(SUMMARY_OPEN) and len(main.messages) < 12 and "question 0" not in json.dumps(main.messages)
    saved = await store.load_messages("s")
    assert saved[0]["content"].startswith(SUMMARY_OPEN) and len(saved) < 14 and alternates(saved)
    ev = next(e for e in r.trace.events if e.type == "summary")
    assert ev.data["tokens_after"] < ev.data["tokens_before"]


async def test_dry_runs_and_a_runtime_without_a_compactor_never_summarise():
    store = InMemoryStore()
    await store.save_messages("s", history(20))
    llm = ScriptedLLM([text("fine")])
    r = await Runtime(llm, store, TraceStore()).run(support_agent(), "s", "hi")
    assert not [e for e in r.trace.events if e.type == "summary"] and "question 0" in json.dumps(llm.requests[0].messages)
    llm2 = ScriptedLLM([text("fine")])
    rt = Runtime(llm2, store, TraceStore(), dry_run=True, compactor=Compactor(llm2, 1000))
    await rt.run(support_agent(), "dry", "hi")
    assert len(llm2.requests) == 1


async def test_a_hand_off_after_summarising_still_shows_earlier_context_to_the_person():
    store = InMemoryStore()
    await store.save_messages("s", history(20))
    llm = ScriptedLLM([text(NOTES), tool_call("handoff_to_human", {"reason": "wants a person"}, "t1")])
    rt = Runtime(llm, store, TraceStore(), compactor=Compactor(llm, 1000, keep_turns=3))
    r = await rt.run(support_agent(), "s", "I want to talk to someone", "jane")
    h = await rt.handoffs.get(r.handoff_id)
    t = h.package["transcript"]
    assert t[0] == {"from": "platform", "text": "Earlier in this conversation: " + NOTES} and t[1]["from"] == "customer" and "question 17" in t[1]["text"]
    assert t[-1]["from"] == "agent" or t[-1]["from"] == "customer"
    assert transcript([{"role": "user", "content": "[summary]\nn\n[/summary]\n\nhello"}]) == [
        {"from": "platform", "text": "Earlier in this conversation: n"}, {"from": "customer", "text": "hello"}]


async def test_secrets_in_a_summary_are_redacted_before_saving():
    from northcx.secrets import SecretStore
    store = InMemoryStore()
    await store.save_messages("s", history(20))
    llm = ScriptedLLM([text(NOTES + " The key was sk-live-ABC123."), text("ok")])
    rt = Runtime(llm, store, TraceStore(), secrets=SecretStore({"PAY": "sk-live-ABC123"}), compactor=Compactor(llm, 1000, keep_turns=3))
    await rt.run(support_agent(), "s", "hello")
    assert "sk-live-ABC123" not in json.dumps(await store.load_messages("s"))
