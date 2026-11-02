"""Scenario simulations: scripted conversations with checks, run against an agent."""
from .judge import Judge, JudgeVerdict, judge_agreement
from .runner import SimConfig, SimulationRunner, run_scenarios
from .scenario import Scenario, ScenarioError, load_scenarios, parse_scenario
from .report import ScenarioResult, SuiteResult, format_report
from .gate import GateStatus, evaluate_gate
from .service import Busy, SimulationService
from .store import InMemorySimRuns, SimRun, SimRunRepo, run_from_suite

__all__ = ["Judge", "JudgeVerdict", "judge_agreement", "SimConfig", "SimulationRunner", "run_scenarios", "Scenario",
           "ScenarioError", "load_scenarios", "parse_scenario", "ScenarioResult", "SuiteResult", "format_report", "GateStatus", "evaluate_gate", "Busy",
           "SimulationService", "InMemorySimRuns", "SimRun", "SimRunRepo", "run_from_suite"]
