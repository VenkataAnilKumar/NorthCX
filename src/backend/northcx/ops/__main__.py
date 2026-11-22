"""`python -m northcx backup --out FILE` and `python -m northcx restore FILE [--replace]`."""
from __future__ import annotations

import argparse
import os
import sys
import time

from northcx.ops.backup import OpsError, backup, restore
from northcx.secrets import env_or_file


def database_url() -> str:
    """The owner connection: the migration URL when one is set (it bypasses row-level security), else the server's own."""
    url = env_or_file("NORTHCX_MIGRATION_DATABASE_URL") or env_or_file("NORTHCX_DATABASE_URL")
    if not url:
        sys.exit("Set NORTHCX_DATABASE_URL (the same value the server uses).")
    return url


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="python -m northcx", description="Back up or restore the whole NorthCX database.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup", help="write the whole database to one file")
    b.add_argument("--out", required=True, help="the file to write (it must not exist)")
    r = sub.add_parser("restore", help="load a backup into an empty database")
    r.add_argument("file")
    r.add_argument("--replace", action="store_true", help="empty the database first if it already holds data")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "backup":
            m = backup(database_url(), args.out)
            print(f"Backed up {sum(t['rows'] for t in m['tables'].values())} rows in {len(m['tables'])} tables (schema revision {m['revision']}) to {args.out}.")
            print("The file holds personal data and is not encrypted: store it where the database's own protections apply.")
        else:
            m = restore(database_url(), args.file, replace=args.replace)
            print(f"Restored {sum(t['rows'] for t in m['tables'].values())} rows in {len(m['tables'])} tables from {time.strftime('%Y-%m-%d %H:%M', time.gmtime(m['createdAt']))} UTC and upgraded to the current schema.")
            print("Meaning search: " + ", ".join(m["excluded"]) + " is not saved; it is rebuilt from the knowledge sources (re-index them if search by meaning is empty).")
    except OpsError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
