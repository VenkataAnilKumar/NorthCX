import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("crp", Path(__file__).resolve().parents[3] / "scripts" / "check_restricted_paths.py")
crp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crp)

BASE = ["THIRD_PARTY.md", "NOTICE", "LICENSE"]


def test_clean_repo_passes():
    assert crp.check(BASE + ["src/a.py", "third_party/x/LICENSE", "third_party/x/a.py"]) == []


def test_ee_and_enterprise_directories_are_rejected():
    problems = crp.check(BASE + ["src/ee/thing.py", "app/Enterprise/x.rb", "backend/ee/LICENSE"])
    assert len(problems) == 3


def test_a_file_named_ee_is_fine():
    assert crp.check(BASE + ["docs/ee"]) == []


def test_third_party_needs_a_licence_and_provenance_files_must_exist():
    problems = crp.check(["THIRD_PARTY.md", "third_party/y/code.py"])
    assert any("no licence" in p for p in problems)
    assert any("Missing NOTICE" in p for p in problems) and any("Missing LICENSE" in p for p in problems)


def test_real_repository_passes():
    assert crp.check(crp.tracked_files(str(Path(__file__).resolve().parents[3]))) == []
