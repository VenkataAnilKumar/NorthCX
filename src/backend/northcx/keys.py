"""Manage API keys from the command line (needed to create the first admin key when the server uses a database).

    python -m northcx.keys create --name alice --role admin [--days 90]
    python -m northcx.keys list
    python -m northcx.keys revoke KEY_ID

Needs NORTHCX_DATABASE_URL. The secret is printed once and cannot be shown again."""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

from .access import ROLES, AccessControl
from .audit import AuditEntry
from .db import PgAudit, PgKeys, create_engine, database_url_from_env, migrate


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="northcx.keys")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--role", required=True, choices=sorted(ROLES))
    c.add_argument("--days", type=float, help="expire after this many days")
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    r.add_argument("key_id")
    a = p.parse_args(argv)
    url = database_url_from_env()
    if not url:
        print("error: set NORTHCX_DATABASE_URL", file=sys.stderr)
        return 2
    migrate(url)

    async def go() -> int:
        engine = create_engine(url)
        try:
            access, audit = AccessControl(PgKeys(engine)), PgAudit(engine)
            who = dict(actor="cli", role="admin")
            if a.cmd == "create":
                key, token = await access.issue(a.name, a.role, "cli", a.days)
                await audit.append(AuditEntry(action="key.create", target=key.prefix, detail={"name": key.name, "role": key.role, "via": "cli"}, **who))
                print(f"Created {a.role} key '{key.name}' ({key.prefix}).\nKey (shown once, store it safely):\n{token}")
            elif a.cmd == "list":
                for k in await access.keys.list():
                    state = "active" if k.active() else "revoked/expired"
                    used = time.strftime("%Y-%m-%d %H:%M", time.gmtime(k.last_used_at)) if k.last_used_at else "never"
                    print(f"{k.prefix:<14} {k.role:<16} {k.name:<24} {state:<16} last used {used}")
            else:
                key = await access.revoke(a.key_id, "cli")
                await audit.append(AuditEntry(action="key.revoke", target=key.prefix, detail={"name": key.name, "via": "cli"}, **who))
                print(f"Revoked {key.prefix} ('{key.name}').")
            return 0
        except (ValueError, KeyError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        finally:
            await engine.dispose()

    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main())
