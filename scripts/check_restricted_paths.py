#!/usr/bin/env python3
"""Fail if the repository contains files copied from restricted locations.

Reference projects keep enterprise code in `ee/` or `enterprise/` directories under separate commercial
licences. Those files must never be copied into NorthCX (see docs/08-governance-safety/NorthCX_Code-Reuse-Policy.md).
Also checks that every file under third_party/ has a licence next to it and that THIRD_PARTY.md and NOTICE exist.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

RESTRICTED_DIRS = {"ee", "enterprise"}
# NorthCX's own words are allowed in docs and scripts; only real directories named ee/enterprise are blocked.


def tracked_files(root: str = ".") -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=root, check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def check(files: list[str], root: str = ".") -> list[str]:
    problems = []
    for f in files:
        parts = PurePosixPath(f).parts
        if any(p.lower() in RESTRICTED_DIRS for p in parts[:-1]):
            problems.append(f"Restricted directory in path: {f}")
    third_party_dirs = {PurePosixPath(f).parts[1] for f in files if f.startswith("third_party/") and len(PurePosixPath(f).parts) > 2}
    for d in sorted(third_party_dirs):
        if not any(f.startswith(f"third_party/{d}/") and PurePosixPath(f).name.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for f in files):
            problems.append(f"third_party/{d} has no licence file")
    for required in ("THIRD_PARTY.md", "NOTICE", "LICENSE"):
        if required not in files:
            problems.append(f"Missing {required}")
    return problems


def main() -> int:
    problems = check(tracked_files())
    for p in problems:
        print("ERROR:", p)
    if problems:
        return 1
    print("Restricted-path and provenance checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
