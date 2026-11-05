"""Guards the moves of route handlers between modules: every route must still exist and every URL must still reach the same handler."""
import json
from pathlib import Path

from route_snapshot import build_app, snapshot

GOLDEN = Path(__file__).parent / "golden" / "routes.json"


def test_every_route_still_dispatches_to_the_same_handler():
    want = json.loads(GOLDEN.read_text())
    got = json.loads(json.dumps(snapshot(build_app())))
    assert got["routes"] == want["routes"], "a route was added, removed or renamed: if that is deliberate, run scripts/gen_route_golden.py"
    assert got["dispatch"] == want["dispatch"], "a URL now reaches a different handler (registration order or a path pattern changed)"


def test_the_snapshot_is_not_trivially_small():
    want = json.loads(GOLDEN.read_text())
    assert len(want["routes"]) > 120 and any("WS" == r[0] for r in want["routes"])
