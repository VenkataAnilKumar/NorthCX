"""Scenario simulations: scripted conversations with checks, run against an agent."""
from .judge import Judge, JudgeVerdict, judge_agreement
from .runner import SimConfig, SimulationRunner, run_scenarios
from .scenario import Scenario, ScenarioError, load_scenarios, parse_scenario
from .report import ScenarioResult, SuiteResult, format_report

__all__ = ["Judge", "JudgeVerdict", "judge_agreement", "SimConfig", "SimulationRunner", "run_scenarios", "Scenario",
           "ScenarioError", "load_scenarios", "parse_scenario", "ScenarioResult", "SuiteResult", "format_report"]
