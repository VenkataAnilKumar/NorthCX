"""Rewrites the golden route-dispatch snapshot (src/backend/tests/golden/routes.json).

Run it from the repository root with the backend's Python, only when a route is deliberately added, removed or renamed:
    src/backend/.venv/bin/python scripts/gen_route_golden.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "backend"))
sys.path.insert(0, str(ROOT / "src" / "backend" / "tests"))

from route_snapshot import build_app, snapshot  # noqa: E402

out = ROOT / "src" / "backend" / "tests" / "golden" / "routes.json"
out.parent.mkdir(parents=True, exist_ok=True)
data = snapshot(build_app())
out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
print(f"wrote {out.relative_to(ROOT)}: {len(data['routes'])} routes, {len(data['dispatch'])} dispatch probes")
