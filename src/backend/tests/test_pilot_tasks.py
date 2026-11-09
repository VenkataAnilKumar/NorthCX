"""E6 first slice (PI1 to PI4, PI10, PI14): Research tasks with questions, a plan, approval, steps, pause and stop, and a versioned cited result."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from northcx.access import AccessControl
from northcx.knowledge import InMemoryKnowledge, Source
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.tasks import MAX_PLAN_STEPS, InMemoryTasks, Task, TaskError, TaskService
from northcx.trace import TraceStore

QUESTIONS = text(json.dumps({"questions": [{"q": "Which product line?", "chips": ["Home", "Pro"]}, {"q": "Since when?", "chips": ["2024", "2025"]}]}))
NO_QUESTIONS = text(json.dumps({"questions": []}))
PLAN = text(json.dumps({"steps": [{"text": "Look up the warranty terms", "source": "knowledge"}, {"text": "Check recent hand-offs about warranty", "source": "conversations"}]}))


def stack(script):
    loop = asyncio.new_event_loop()
    llm = ScriptedLLM(script)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    kb = InMemoryKnowledge()
    loop.run_until_complete(kb.create_source(Source("faq", "FAQ")))
    loop.run_until_complete(kb.upsert("faq", "w", "Warranty", None, "Every product has a two year warranty.", None))
    ac = AccessControl(bootstrap_key="boot" * 10)
    app = create_app(rt, rt.traces, {}, access=ac, knowledge=kb)
    key = lambda name, role="developer": {"authorization": "Bearer " + loop.run_until_complete(ac.issue(name, role, "t"))[1]}  # noqa: E731
    return TestClient(app), app, llm, key, loop


def wait(app, loop, task_id):
    loop.run_until_complete(app.state.tasks.wait(task_id))


def test_the_whole_research_lifecycle_with_nothing_running_before_approval():
    script = [QUESTIONS, PLAN, tool_call("search_knowledge", {"query": "warranty"}, "t1"), text("The warranty is two years [1]."), text("Nothing recent."), text("Result: two years [1]. No recent hand-offs.")]
    c, app, llm, key, loop = stack(script)
    h = key("ann")
    t = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "How does our warranty work?"}).json()
    assert t["status"] == "needs_answers" and [q["chips"] for q in t["questions"]] == [["Home", "Pro"], ["2024", "2025"]]
    t = c.post(f"/v1/workspace/tasks/{t['id']}/answers", headers=h, json={"answers": ["Home", "2025"]}).json()
    assert t["status"] == "planned" and [s["text"] for s in t["plan"]] == ["Look up the warranty terms", "Check recent hand-offs about warranty"]
    assert len(llm.requests) == 2 and t["steps"] == [] and t["results"] == []            # questions and plan only: nothing was run
    edited = c.put(f"/v1/workspace/tasks/{t['id']}/plan", headers=h, json={"steps": [{"text": "Look up the warranty terms", "source": "knowledge"},
                                                                                      {"text": "Check recent hand-offs about warranty", "source": "conversations"}]}).json()
    assert edited["status"] == "planned"
    assert c.post(f"/v1/workspace/tasks/{t['id']}/approve", headers=h).json()["status"] in ("approved", "running", "done")
    wait(app, loop, t["id"])
    done = c.get(f"/v1/workspace/tasks/{t['id']}", headers=h).json()
    assert done["status"] == "done" and [s["status"] for s in done["steps"]] == ["done", "done"]
    assert done["steps"][0]["tools"] == ["search_knowledge"] and done["steps"][0]["sources"][0]["title"] == "Warranty"
    assert done["results"][0]["v"] == 1 and "two years" in done["results"][0]["text"] and done["results"][0]["sources"][0]["title"] == "Warranty"
    audit = [e["action"] for e in c.get("/v1/audit?limit=50", headers={"authorization": "Bearer " + "boot" * 10}).json()["entries"]]
    assert {"workspace.task.create", "workspace.task.plan", "workspace.task.edit", "workspace.task.approve"} <= set(audit)


def test_a_clear_task_goes_straight_to_a_plan_and_a_task_can_only_be_run_when_planned():
    c, app, llm, key, loop = stack([NO_QUESTIONS, PLAN])
    h = key("ann")
    t = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "Summarise the warranty policy"}).json()
    assert t["status"] == "planned" and t["questions"] == []
    other = key("zed")
    assert c.post(f"/v1/workspace/tasks/{t['id']}/answers", headers=other, json={"answers": []}).status_code == 404   # another person's task is not found


def test_a_task_that_is_not_planned_cannot_be_approved_and_bad_input_is_refused():
    c, app, llm, key, loop = stack([QUESTIONS])
    h = key("ann")
    t = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "How does our warranty work?"}).json()
    assert c.post(f"/v1/workspace/tasks/{t['id']}/approve", headers=h).status_code == 409       # still waiting for answers
    assert c.put(f"/v1/workspace/tasks/{t['id']}/plan", headers=h, json={"steps": [{"text": "x"}]}).status_code == 409
    assert c.post(f"/v1/workspace/tasks/{t['id']}/answers", headers=h, json={"answers": ["a", "b", "c", "d"]}).status_code == 400
    assert c.post("/v1/workspace/tasks", headers=h, json={"prompt": "", "style": "research"}).status_code == 400
    assert c.post("/v1/workspace/tasks", headers=h, json={"prompt": "x", "style": "do"}).status_code == 400   # Do is not available yet


def test_pause_stops_between_steps_and_approve_resumes_where_it_left_off():
    c, app, llm, key, loop = stack([NO_QUESTIONS, PLAN])
    h = key("ann")
    t = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "warranty"}).json()
    tid = t["id"]

    def pause_during_step_one(req):
        app.state.tasks._flags[tid] = "pause"       # the person pressed pause while step one was running
        return text("Step one found two years.")
    llm.script += [pause_during_step_one, text("Step two found nothing."), text("Final result.")]
    c.post(f"/v1/workspace/tasks/{tid}/approve", headers=h)
    wait(app, loop, tid)
    paused = c.get(f"/v1/workspace/tasks/{tid}", headers=h).json()
    assert paused["status"] == "paused" and [s["status"] for s in paused["steps"]] == ["done"] and paused["results"] == []
    c.post(f"/v1/workspace/tasks/{tid}/approve", headers=h)         # resume
    wait(app, loop, tid)
    done = c.get(f"/v1/workspace/tasks/{tid}", headers=h).json()
    assert done["status"] == "done" and [s["n"] for s in done["steps"]] == [1, 2] and done["results"][0]["text"] == "Final result."
    assert "Step one found two years." in str(llm.requests[-1].messages)       # the result is written from both steps' findings, including the first, before the pause


def test_stop_ends_the_run_and_it_can_be_started_again_with_the_old_result_kept():
    c, app, llm, key, loop = stack([NO_QUESTIONS, PLAN])
    h = key("ann")
    tid = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "warranty"}).json()["id"]

    def stop_during_step_one(req):
        app.state.tasks._flags[tid] = "stop"
        return text("partial")
    llm.script += [stop_during_step_one]
    c.post(f"/v1/workspace/tasks/{tid}/approve", headers=h)
    wait(app, loop, tid)
    stopped = c.get(f"/v1/workspace/tasks/{tid}", headers=h).json()
    assert stopped["status"] == "stopped" and stopped["results"] == [] and stopped["note"] == "stopped by the person"
    llm.script += [text("one"), text("two"), text("Second run result.")]
    c.post(f"/v1/workspace/tasks/{tid}/approve", headers=h)
    wait(app, loop, tid)
    again = c.get(f"/v1/workspace/tasks/{tid}", headers=h).json()
    assert again["status"] == "done" and again["results"][0]["v"] == 1 and len(again["steps"]) == 2
    assert c.post(f"/v1/workspace/tasks/{tid}/stop", headers=h).status_code == 409        # nothing running to stop


def test_a_failing_step_ends_the_run_with_the_reason_and_leaves_the_plan_alone():
    c, app, llm, key, loop = stack([NO_QUESTIONS, PLAN])
    h = key("ann")
    tid = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "warranty"}).json()["id"]

    def boom(req):
        raise RuntimeError("model unavailable")
    llm.script += [boom, boom, boom]
    c.post(f"/v1/workspace/tasks/{tid}/approve", headers=h)
    wait(app, loop, tid)
    t = c.get(f"/v1/workspace/tasks/{tid}", headers=h).json()
    assert t["status"] in ("failed", "stopped") and len(t["plan"]) == 2 and t["results"] == []


def test_a_task_belongs_to_its_owner_and_can_be_erased():
    c, app, llm, key, loop = stack([NO_QUESTIONS, PLAN, NO_QUESTIONS, PLAN])
    ann, ben = key("ann"), key("ben")
    a = c.post("/v1/workspace/tasks", headers=ann, json={"prompt": "ann's"}).json()["id"]
    b = c.post("/v1/workspace/tasks", headers=ben, json={"prompt": "ben's"}).json()["id"]
    assert [t["id"] for t in c.get("/v1/workspace/tasks", headers=ann).json()["tasks"]] == [a]
    for call in (lambda: c.get(f"/v1/workspace/tasks/{b}", headers=ann), lambda: c.post(f"/v1/workspace/tasks/{b}/approve", headers=ann), lambda: c.delete(f"/v1/workspace/tasks/{b}", headers=ann)):
        assert call().status_code == 404
    assert c.delete(f"/v1/workspace/tasks/{a}", headers=ann).json() == {"deleted": True} and c.get(f"/v1/workspace/tasks/{a}", headers=ann).status_code == 404
    assert c.get(f"/v1/workspace/tasks/{b}", headers=ben).status_code == 200


def test_a_task_left_running_by_a_previous_server_is_shown_as_stopped():
    c, app, llm, key, loop = stack([NO_QUESTIONS, PLAN])
    h = key("ann")
    tid = c.post("/v1/workspace/tasks", headers=h, json={"prompt": "x"}).json()["id"]
    t = loop.run_until_complete(app.state.tasks.repo.get(tid))
    t.status = "running"
    loop.run_until_complete(app.state.tasks.repo.save(t))
    shown = c.get(f"/v1/workspace/tasks/{tid}", headers=h).json()
    assert shown["status"] == "stopped" and "restarted" in shown["note"]


def test_the_step_limit_is_enforced():
    svc = TaskService(InMemoryTasks(), None)
    many = [{"text": f"step {i}"} for i in range(20)]
    t = Task("t1", "o", "research", "p", "planned", plan=[{"n": 1, "text": "x", "source": "both"}])
    out = asyncio.run(svc.edit_plan(t, many))
    assert len(out.plan) == MAX_PLAN_STEPS
    with pytest.raises(TaskError):
        asyncio.run(svc.edit_plan(t, [{"text": "  "}]))


async def test_tasks_survive_the_database_and_stay_in_their_tenant(app_engine):
    from contextlib import contextmanager

    from northcx.db import PgTasks
    from northcx.tenancy import TENANT

    @contextmanager
    def as_tenant(name):
        token = TENANT.set(name)
        try:
            yield
        finally:
            TENANT.reset(token)
    repo = PgTasks(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await repo.save(Task(f"t-{tenant}", "staff:1", "research", f"{tenant} task", "planned", plan=[{"n": 1, "text": "x", "source": "both"}]))
    with as_tenant("acme"):
        got = await repo.get("t-acme")
        assert got.prompt == "acme task" and got.plan[0]["text"] == "x" and await repo.get("t-globex") is None
        assert [t.id for t in await repo.list("staff:1", 10)] == ["t-acme"]
        got.status = "done"
        await repo.save(got)
        assert (await repo.get("t-acme")).status == "done" and await repo.delete("t-acme") and not await repo.delete("t-globex")
    with as_tenant("globex"):
        assert (await repo.get("t-globex")).prompt == "globex task"
