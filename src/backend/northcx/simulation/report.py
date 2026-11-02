from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Failure:
    where: str  # "step 2 (say)" or "scenario"
    check: str
    expected: Any
    actual: Any

    def __str__(self) -> str:
        return f"{self.where}: {self.check}: expected {self.expected!r}, got {self.actual!r}"


@dataclass
class TrialResult:
    passed: bool
    failures: list[Failure] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    judge: dict[str, Any] | None = None
    model_calls: int = 0
    seconds: float = 0.0


@dataclass
class ScenarioResult:
    name: str
    required: bool
    passed: bool
    trials: list[TrialResult]
    pass_rate: float
    source: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def failures(self) -> list[Failure]:
        return [f for t in self.trials for f in t.failures]


@dataclass
class SuiteResult:
    mode: str
    results: list[ScenarioResult]

    @property
    def passed(self) -> bool:
        """The gate: every required scenario passed."""
        return all(r.passed for r in self.results if r.required)

    @property
    def counts(self) -> dict[str, int]:
        return {"total": len(self.results), "passed": sum(r.passed for r in self.results),
                "failed": sum(not r.passed for r in self.results),
                "required_failed": sum((not r.passed) and r.required for r in self.results)}

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "passed": self.passed, "counts": self.counts, "results": [asdict(r) for r in self.results]}


def format_report(suite: SuiteResult) -> str:
    lines = []
    for r in suite.results:
        mark = "PASS" if r.passed else ("FAIL" if r.required else "warn")
        rate = f" ({r.pass_rate:.0%} of {len(r.trials)} trials)" if len(r.trials) > 1 else ""
        lines.append(f"{mark}  {r.name}{rate}" + ("" if r.required else "  [not required]"))
        for n in r.notes:
            lines.append(f"      note: {n}")
        if not r.passed:
            for f in r.failures[:8]:
                lines.append(f"      - {f}")
    c = suite.counts
    lines.append(f"\n{c['passed']}/{c['total']} scenarios passed; {c['required_failed']} required failed ({suite.mode} model). "
                 + ("GATE: pass" if suite.passed else "GATE: fail"))
    return "\n".join(lines)
