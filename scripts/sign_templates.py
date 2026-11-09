"""Sign the built-in templates (WP22.9).

  python scripts/sign_templates.py --generate-key KEY.pem   make a release key: keep KEY.pem secret, the public half is written to the library
  python scripts/sign_templates.py --key KEY.pem            sign every built-in template (run it whenever a built-in changes)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))
import yaml  # noqa: E402

from northcx import template_signing as ts  # noqa: E402
from northcx.templates import LIBRARY  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--generate-key")
ap.add_argument("--key")
a = ap.parse_args()
if a.generate_key:
    priv, pub = ts.generate_key()
    Path(a.generate_key).write_bytes(priv)
    (LIBRARY / ts.KEY_FILE).write_bytes(pub)
    print(f"wrote {a.generate_key} (keep it secret) and {LIBRARY / ts.KEY_FILE}; now sign with --key")
elif a.key:
    priv = Path(a.key).read_bytes()
    out = {}
    for f in sorted(LIBRARY.glob("*.y*ml")):
        for d in (x for x in yaml.safe_load_all(f.read_text()) if x):
            h, v = ts.content_hash(d), str(d.get("version", "1"))
            out[d["id"]] = {"version": v, "hash": h, "signature": ts.sign(priv, d["id"], v, h)}
    (LIBRARY / ts.SIGNATURES_FILE).write_text(json.dumps({"algorithm": "ed25519", "templates": out}, indent=2, sort_keys=True) + "\n")
    print(f"signed {len(out)} templates")
else:
    ap.error("give --generate-key or --key")
