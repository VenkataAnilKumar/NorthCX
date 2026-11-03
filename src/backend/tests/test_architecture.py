"""Structural rules that keep the product easy to change."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "northcx"


def test_only_the_model_adapter_imports_the_ai_sdk():
    offenders = []
    for f in ROOT.rglob("*.py"):
        if f.name == "llm.py" and f.parent == ROOT:
            continue
        if re.search(r"^\s*(import|from)\s+anthropic\b", f.read_text(), re.M):
            offenders.append(str(f.relative_to(ROOT)))
    assert offenders == []


def test_the_runtime_depends_only_on_the_model_interface():
    for name in ("runtime.py", "summarize.py", "reliability.py", "guardrails.py"):
        assert "AnthropicLLM" not in (ROOT / name).read_text(), name
