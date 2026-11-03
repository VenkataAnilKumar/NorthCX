"""Multilingual conversations (R9): detection, same-language replies, unsupported languages, hand-off language, insights."""
import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.insights import InMemoryFeedback, InMemoryInsightsSource, InMemoryTags, InsightsService, compute, facts_from_trace
from northcx.language import choose, conversation_language, detect, instruction
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.spec import AgentSpec
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

SAMPLES = {
    "en": "Where is my order? I need a refund please",
    "es": "¿Dónde está mi pedido? Necesito un reembolso, gracias",
    "fr": "Où est ma commande ? Je voudrais un remboursement, merci",
    "de": "Wo ist meine Bestellung? Ich brauche bitte Hilfe",
    "pt": "Onde está o meu pedido? Preciso de um reembolso, obrigado",
    "it": "Dove è il mio ordine? Ho bisogno di un rimborso, grazie",
    "nl": "Waar is mijn bestelling? Ik heb hulp nodig, dank",
    "ru": "Где мой заказ? Мне нужен возврат",
    "ja": "注文はどこですか？返金してください",
    "zh": "我的订单在哪里？我需要退款",
    "ko": "제 주문은 어디에 있나요? 환불이 필요합니다",
    "ar": "أين طلبي؟ أحتاج إلى استرداد",
    "hi": "मेरा ऑर्डर कहाँ है? मुझे रिफंड चाहिए",
}


@pytest.mark.parametrize("code,msg", sorted(SAMPLES.items()))
def test_each_supported_language_is_recognised(code, msg):
    assert detect(msg) == code


def test_short_or_unclear_text_says_nothing():
    for t in ["", "ok", "hola", "12345", "👍👍", "order 1042 ???", "the", "yes please"]:
        assert detect(t) is None, t
    assert conversation_language("ok", ["¿Dónde está mi pedido? Necesito ayuda, gracias"]) == "es"  # keeps the conversation's language
    assert conversation_language("ok", ["hi", "ok"]) is None and conversation_language("Where is my order, please help me", ["hola"]) == "en"


def test_choice_and_instruction():
    assert choose("es", ["en", "es"]).reply_in == "es" and choose(None, ["en", "es"]).reply_in == "en" and choose(None, ["en"]).supported
    c = choose("ja", ["en", "es"])
    assert (c.reply_in, c.supported) == ("en", False)
    assert "Spanish" in instruction(choose("es", ["en", "es"])) and "does not support" in instruction(c) and "Japanese" in instruction(c) and "person" in instruction(c)


def test_specs_validate_languages_and_old_digests_do_not_change():
    base = AgentSpec(id="a", instructions="i")
    assert "languages" not in base.canonical() and AgentSpec(id="a", instructions="i", languages=["en", "es"]).digest() != base.digest()
    for bad, msg in [(["xx"], "Unknown language"), (["en", "en"], "twice")]:
        with pytest.raises(ValueError, match=msg):
            AgentSpec(id="a", instructions="i", languages=bad)


def agent(*langs):
    return dataclasses.replace(support_agent(), languages=list(langs))


async def run(rt, a, sid, msg, **kw):
    return await rt.run(a, sid, msg, "c", **kw)


async def test_the_agent_is_told_which_language_to_reply_in():
    llm = ScriptedLLM([text("Hola"), text("Hola de nuevo"), text("Sorry"), text("Hi")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    a = agent("en", "es")
    await run(rt, a, "s1", SAMPLES["es"])
    assert "write every reply to the customer in Spanish" in llm.requests[0].system
    first = next(t for t in rt.traces._traces.values() if t.session_id == "s1")
    lang = next(e.data for e in first.events if e.type == "language")
    assert lang == {"detected": "es", "replyIn": "es", "supported": True}
    await run(rt, a, "s1", "ok")  # too short to tell: the conversation stays Spanish
    assert "in Spanish" in llm.requests[1].system
    await run(rt, a, "s2", SAMPLES["ja"])  # not supported: reply in the default and offer a person
    assert "does not support yet" in llm.requests[2].system and "Reply in English" in llm.requests[2].system
    await run(rt, a, "s3", SAMPLES["en"])
    assert "in English" in llm.requests[3].system


async def test_no_languages_means_no_language_handling_and_system_messages_are_skipped():
    llm = ScriptedLLM([text("ok"), text("ok")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    await run(rt, agent(), "s1", SAMPLES["es"])
    assert "Language:" not in llm.requests[0].system
    await run(rt, agent("en", "es"), "s2", "[system] approval granted", trusted=True)
    assert "Language:" not in llm.requests[1].system


async def conversations():
    llm = ScriptedLLM([text("Hola"), tool_call("handoff_to_human", {"reason": "wants a person"}, "h"), text("Bonjour"), text("Hi")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    a = agent("en", "es", "fr")
    await run(rt, a, "s-es", SAMPLES["es"])
    await run(rt, a, "s-es-h", SAMPLES["es"] + " quiero una persona")
    await run(rt, a, "s-fr", SAMPLES["fr"])
    await run(rt, a, "s-en", SAMPLES["en"])
    return rt


async def test_handoffs_carry_the_customers_language():
    rt = await conversations()
    h = (await rt.handoffs.list(None, "s-es-h", 5))[0]
    assert h.package["language"] == "es"


async def test_insights_break_conversations_down_by_language_and_search_filters():
    rt = await conversations()
    svc = InsightsService(InMemoryInsightsSource(rt, InMemoryFeedback()))
    o = await svc.overview(time.time() - 60, time.time() + 60)
    langs = o["languages"]
    assert langs["detected"]["numerator"] == 4 and set(langs["byLanguage"]) == {"en", "es", "fr"}
    assert langs["byLanguage"]["es"]["conversations"] == 2 and langs["byLanguage"]["es"]["containmentRate"]["numerator"] == 1  # one of the two Spanish conversations reached a person
    rows = await svc.search(time.time() - 60, time.time() + 60, InMemoryTags(), language="fr")
    assert [r["sessionId"] for r in rows] == ["s-fr"] and rows[0]["language"] == "fr"
    assert len(await svc.search(time.time() - 60, time.time() + 60, InMemoryTags())) == 4
    assert "languages" not in compute([], [], [], 0, 1)
    assert {facts_from_trace(t).language for t in rt.traces._traces.values()} == {"es", "fr", "en"}


async def test_the_api_filters_by_language():
    rt = await conversations()
    c = TestClient(create_app(rt, rt.traces, {"support": agent("en", "es", "fr")}))
    rows = c.get("/v1/conversations/search?language=es").json()["conversations"]
    assert {r["sessionId"] for r in rows} == {"s-es", "s-es-h"}
