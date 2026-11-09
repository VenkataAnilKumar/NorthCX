"""Manage tenants from the command line (WP2.2; the platform API under /platform/v1 comes with WP2.8).

    python -m northcx.tenants list
    python -m northcx.tenants create ID "Name"          (needs NORTHCX_TENANCY_PREVIEW=1: tenant isolation is not finished)
    python -m northcx.tenants suspend ID | activate ID
    python -m northcx.tenants bind ID KIND ADDRESS      (an inbound number, bot id or email domain belongs to one tenant)
    python -m northcx.keys create --tenant ID ...       (a key for that tenant's first administrator)

Needs NORTHCX_DATABASE_URL."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .audit import AuditEntry
from .db import PgAudit, PgTenants, create_engine, database_url_from_env, migrate
from .tenancy import BINDING_KINDS, TenantError, TenantService


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="northcx.tenants")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("create")
    c.add_argument("id")
    c.add_argument("name")
    for name in ("suspend", "activate"):
        sub.add_parser(name).add_argument("id")
    b = sub.add_parser("bind")
    b.add_argument("id")
    b.add_argument("kind", choices=BINDING_KINDS)
    b.add_argument("address")
    a = p.parse_args(argv)
    url = database_url_from_env()
    if not url:
        print("error: set NORTHCX_DATABASE_URL", file=sys.stderr)
        return 2
    migrate(url)

    async def go() -> int:
        engine = create_engine(url)
        try:
            svc, audit = TenantService(PgTenants(engine), preview=os.environ.get("NORTHCX_TENANCY_PREVIEW") == "1"), PgAudit(engine)
            who = dict(actor="cli", role="admin", tenant_id="default")
            if a.cmd == "list":
                for t in await svc.repo.list():
                    print(f"{t.id:<24} {t.status:<10} {t.name}")
            elif a.cmd == "create":
                t = await svc.create(a.id, a.name)
                await audit.append(AuditEntry(action="tenant.create", target=t.id, detail={"name": t.name, "via": "cli"}, **who))
                print(f"Created tenant '{t.id}'. Create its first administrator key with: python -m northcx.keys create --tenant {t.id} --name <name> --role admin")
            elif a.cmd in ("suspend", "activate"):
                t = await svc.set_status(a.id, "suspended" if a.cmd == "suspend" else "active")
                await audit.append(AuditEntry(action=f"tenant.{a.cmd}", target=t.id, detail={"via": "cli"}, **who))
                print(f"Tenant '{t.id}' is {t.status}.")
            else:
                bd = await svc.bind(a.id, a.kind, a.address)
                await audit.append(AuditEntry(action="tenant.bind", target=a.id, detail={"kind": bd.kind, "address": bd.address, "via": "cli"}, **who))
                print(f"Bound {bd.kind} {bd.address} to '{a.id}'.")
            return 0
        except (TenantError, KeyError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        finally:
            await engine.dispose()

    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main())
