"""Data residency: the policy file, the report of data flows, and strict start-up refusal."""
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.residency import ResidencyError, build_report, host_of, parse_policy
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

POLICY = "region: eu\nstrict: true\nhosts:\n  - {match: '*.eu.example.com', region: eu}\n  - {match: api.us.example.com, region: us}\n  - {match: db.internal, region: eu}\n"


def report(env, policy=POLICY):
    return build_report(env, parse_policy(policy) if policy else None)


def by_name(r):
    return {f["name"]: f for f in r["flows"]}


def test_a_compliant_deployment_reports_every_flow_with_its_region():
    r = report({"NORTHCX_DATABASE_URL": "postgresql+asyncpg://u:p@db.internal:5432/n", "ANTHROPIC_API_KEY": "k", "ANTHROPIC_BASE_URL": "https://llm.eu.example.com",
                "NORTHCX_EMBEDDINGS_URL": "https://emb.eu.example.com/v1", "NORTHCX_CONNECTOR_HOSTS": "crm.eu.example.com"})
    assert r["compliant"] and not r["problems"] and r["region"] == "eu"
    f = by_name(r)
    assert f["Database"]["host"] == "db.internal" and f["Database"]["region"] == "eu" and f["Language model"]["host"] == "llm.eu.example.com"
    assert all(x["status"] == "ok" for x in r["flows"]) and "u:p" not in str(r)  # credentials in addresses never appear


def test_unmapped_and_disallowed_destinations_are_problems():
    r = report({"ANTHROPIC_API_KEY": "k", "NORTHCX_SMS_NUMBER": "+14155550100", "NORTHCX_WEBHOOK_URL": "https://hooks.us.example.com/x", "NORTHCX_INBOX_WEBHOOK_URL": "https://api.us.example.com/in"})
    f = by_name(r)
    assert f["Language model"]["host"] == "api.anthropic.com" and f["Language model"]["status"] == "unmapped"  # the default address is checked too
    assert f["SMS provider"]["host"] == "api.twilio.com" and f["SMS provider"]["status"] == "unmapped"
    assert f["Human inbox webhook"]["status"] == "not_allowed" and f["Human inbox webhook"]["region"] == "us"
    assert not r["compliant"] and any("not allowed" in p for p in r["problems"]) and any("does not map" in p for p in r["problems"])


def test_local_addresses_and_unset_things_are_not_flows_or_problems():
    r = report({"NORTHCX_EMBEDDINGS_URL": "http://localhost:8080/v1", "NORTHCX_OTLP_ENDPOINT": "http://127.0.0.1:4318"})
    assert r["compliant"] and {f["region"] for f in r["flows"]} == {"local"}
    assert report({})["flows"] == [] and report({})["compliant"]  # an offline demo has no live model flow


def test_whatsapp_and_overrides_use_the_real_address():
    r = report({"NORTHCX_WHATSAPP_PHONE_ID": "123456"})
    assert by_name(r)["WhatsApp"]["host"] == "graph.facebook.com"
    r = report({"NORTHCX_WHATSAPP_PHONE_ID": "123456", "NORTHCX_WHATSAPP_API_URL": "https://wa.eu.example.com/v21.0"})
    assert by_name(r)["WhatsApp"]["status"] == "ok"


def test_without_a_policy_flows_are_listed_but_unchecked():
    r = report({"NORTHCX_SMTP_URL": "smtp://mail.example.com:587"}, policy=None)
    assert not r["configured"] and r["flows"][0]["status"] == "unchecked" and r["flows"][0]["host"] == "mail.example.com"


@pytest.mark.parametrize("bad", ["", "- a", "region: EU", "region: eu\nbogus: 1", "region: eu\nallowed_regions: []", "region: eu\nstrict: yes please",
                                 "region: eu\nhosts: [{match: '*', region: eu}]", "region: eu\nhosts: [{match: 'a.com'}]", "region: eu\nhosts: [{match: 'a.com', region: 'No Good'}]",
                                 "region: eu\nhosts: [{match: 'a b', region: eu}]", ": : :"])
def test_bad_policy_files_are_refused(bad):
    with pytest.raises(ResidencyError):
        parse_policy(bad)


def test_host_parsing_handles_urls_ports_and_junk():
    assert host_of("https://User:pw@Api.Example.com:8443/x?y=1") == "api.example.com" and host_of("smtp.example.com:587") == "smtp.example.com"
    assert host_of("") is None and host_of("   ") is None


def test_the_shipped_example_parses():
    from pathlib import Path
    p = parse_policy((Path(__file__).parent.parent / "examples" / "config" / "residency.example.yaml").read_text())
    assert p.region == "eu" and p.strict and p.region_of("x.eu.example.com") == "eu" and p.region_of("evil.com") is None


def api(res):
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10), residency=res)), {"authorization": "Bearer " + "boot" * 10}


def test_the_endpoint_reports_for_auditors_only():
    c, h = api(report({"NORTHCX_WEBHOOK_URL": "https://hooks.eu.example.com/x"}))
    r = c.get("/v1/residency", headers=h)
    assert r.status_code == 200 and r.json()["compliant"] and r.json()["flows"][0]["region"] == "eu"
    assert c.get("/v1/residency").status_code == 401
    assert api(None)[0].get("/v1/residency", headers=h).json()["configured"] is False


PROVIDERS = """providers:
  - {name: local, type: openai-compatible, baseUrl: 'http://ollama:11434/v1', allowInsecureHttp: true, where: local}
  - {name: eu-cloud, type: openai-compatible, baseUrl: 'https://llm.eu.example.com/v1', where: public-cloud}
  - {name: claude, type: anthropic, where: public-cloud}
"""


def test_every_model_in_the_providers_file_is_a_flow_with_its_own_address():
    r = build_report({"ANTHROPIC_API_KEY": "k"}, parse_policy(POLICY), PROVIDERS)
    f = by_name(r)
    assert f["Language model: eu-cloud"]["host"] == "llm.eu.example.com" and f["Language model: eu-cloud"]["status"] == "ok"
    assert f["Language model: local"]["host"] == "ollama" and f["Language model: local"]["status"] == "unmapped"   # a private host name still has to be declared
    assert f["Language model: claude"]["host"] == "api.anthropic.com"
    assert "Language model" not in f                                                                                  # the file lists the Claude provider, so it is not listed twice


def test_a_routine_destination_is_a_flow_but_a_mail_address_is_not_an_address_to_check():
    r = report({"NORTHCX_AUTOMATION_DESTINATIONS": "ops=https://hooks.eu.example.com/x,boss=mailto:boss@example.com,bad=ftp://x"})
    f = by_name(r)
    assert f["Routine destination (ops)"]["host"] == "hooks.eu.example.com" and f["Routine destination (ops)"]["status"] == "ok"
    assert list(f) == ["Routine destination (ops)"]


def test_the_network_page_lists_every_destination_the_report_can_show():
    import re
    from pathlib import Path

    from northcx.residency import FLOWS
    page = (Path(__file__).parents[3] / "docs" / "11-operations" / "NorthCX_Network-Needs.md").read_text()
    missing = [var for _, var, _, _ in FLOWS if var not in page]
    missing += [s for s in ("NORTHCX_DATABASE_URL", "NORTHCX_CONNECTOR_HOSTS", "NORTHCX_MCP_HOSTS", "NORTHCX_AUTOMATION_DESTINATIONS", "NORTHCX_PROVIDERS_FILE", "NORTHCX_CRAWL_HOSTS") if s not in page]
    assert not missing, f"Network-Needs.md does not mention: {missing}"
    assert re.search(r"api\.twilio\.com", page) and "graph.facebook.com" in page and "api.telegram.org" in page and "api.anthropic.com" in page
