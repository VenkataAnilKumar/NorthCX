import os
import sys
from pathlib import Path
from northcx.rollout import RolloutService
from northcx.connectors import ConnectorError, allowed_hosts_from, load_connectors
from northcx.templates import TemplateError
from northcx.skills import SkillError, load_skills
from northcx.memory import memory_tools
from northcx.verification import verification_tools
from northcx.knowledge import knowledge_tool
from northcx.simulation import ScenarioError, SimulationService, load_scenarios
from northcx.spec import BuildContext, SpecError, load_specs
from northcx.versions import LiveAgents, ReleaseService
from types import SimpleNamespace


def build_agents(c: SimpleNamespace) -> None:
    """Agent specs, scenarios, simulations and releases."""
    demo = c.demo
    examples_dir = c.examples_dir
    knowledge_repo = c.knowledge_repo
    llm = c.llm
    registry = c.registry
    releases_repo = c.releases_repo
    rollout_repo = c.rollout_repo
    runtime = c.runtime
    scenario_repo = c.scenario_repo
    secrets = c.secrets
    sim_runs = c.sim_runs
    verify_service = c.verify_service
    versions_repo = c.versions_repo
    # Agents and scenarios are files; the registry maps their tool names to code (the example registry for now).
    specs_dir = os.environ.get("NORTHCX_AGENTS_DIR") or str(examples_dir)
    scenarios_dir = os.environ.get("NORTHCX_SCENARIOS_DIR") or str(examples_dir / "scenarios")
    try:
        reg = registry()
        if os.environ.get("NORTHCX_CONNECTORS_DIR"):
            for tool in load_connectors(os.environ["NORTHCX_CONNECTORS_DIR"], allowed_hosts_from(os.environ.get("NORTHCX_CONNECTOR_HOSTS"))):
                reg.tool(tool)  # a tool name that already exists is refused
        if os.environ.get("NORTHCX_SKILLS_DIR"):
            for sk in load_skills(os.environ["NORTHCX_SKILLS_DIR"]):
                reg.skill(sk)
        if verify_service is not None:
            for t_ in verification_tools(verify_service):
                if t_.name not in reg.tool_names():
                    reg.tool(t_)
        if "search_knowledge" not in reg.tool_names():
            reg.tool(knowledge_tool(knowledge_repo))
        if runtime.memories is not None:
            for t in memory_tools(runtime.memories):
                if t.name not in reg.tool_names():
                    reg.tool(t)
        print(f"Tool secrets available: {', '.join(secrets.names()) or 'none'}")
        specs = {s.id: reg.pin_skills(s, overwrite=True) for s in load_specs(specs_dir)}  # spec files follow the skill files; the digest includes them
        baseline = {}
        for i, s in specs.items():  # agents defined by spec files; they serve until a version is released
            baseline[i] = reg.build(s, BuildContext(llm=llm))
            baseline[i].digest = s.digest()
        scenarios = load_scenarios(scenarios_dir) if Path(scenarios_dir).exists() else []
    except (SpecError, ScenarioError, SkillError, ConnectorError, TemplateError) as e:
        sys.exit(f"Invalid configuration: {e}")

    def factory(agent_id, sim_llm):
        return reg.build(specs[agent_id], BuildContext(llm=sim_llm))

    # Always available: scenarios can live in files, in the database (the Studio editor), or both.
    simulations = SimulationService(scenarios, factory, sim_runs, {i: s.digest() for i, s in specs.items()},
                                    live_llm=None if demo else llm, judge_llm=None if demo else llm,
                                    spec_builder=lambda spec, sim_llm: reg.build(spec, BuildContext(llm=sim_llm)), managed=scenario_repo)
    release_service = ReleaseService(versions_repo, releases_repo, reg, specs, simulations, strict_promotion=os.environ.get("NORTHCX_STRICT_PROMOTION") == "1")
    held = {e.strip() for e in os.environ.get("NORTHCX_RELEASE_APPROVALS", "").split(",") if e.strip()}
    if held - {"dev", "staging", "production"}:
        sys.exit("NORTHCX_RELEASE_APPROVALS must list environments from: dev, staging, production")
    if held:
        from northcx.db import PgReleaseRequests
        from northcx.release_requests import ReleaseApprovals
        release_service.approvals = ReleaseApprovals(held, PgReleaseRequests(c.engine) if c.db_url else None)
        print(f"Releases to {', '.join(sorted(held))} need a second person's approval.")

    def build_live(spec):
        agent = reg.build(spec, BuildContext(llm=llm))
        agent.digest = spec.digest()
        return agent

    rollout_service = RolloutService(rollout_repo, release_service)
    agents = LiveAgents(baseline, release_service, build_live)
    c.agents = agents
    c.reg = reg
    c.release_service = release_service
    c.rollout_service = rollout_service
    c.simulations = simulations
