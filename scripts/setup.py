#!/usr/bin/env python3
"""Set up NorthCX in one command: write a working `.env` (and a model providers file for a local model) with generated secrets.

    python3 scripts/setup.py                       # asks four plain questions
    python3 scripts/setup.py --demo                # the offline demo model: no key, no AI, for trying the console
    python3 scripts/setup.py --anthropic-key sk-ant-...
    python3 scripts/setup.py --local-model-url http://host.docker.internal:11434/v1 --local-model <model>
    python3 scripts/setup.py --check               # check an existing .env

Standard library only, so it runs before anything is installed. It never overwrites an existing `.env` unless told to (`--force`, which keeps the old file).
"""
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import string
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALNUM = string.ascii_letters + string.digits
MIN_KEY = 24


def generate_password(n: int = 24) -> str:
    """Letters and digits only: the database password is placed in a connection URL."""
    return "".join(secrets.choice(ALNUM) for _ in range(n))


def providers_yaml(url: str, model: str) -> str:
    return f"""# Written by scripts/setup.py. A local model server that speaks the OpenAI chat format (Ollama, vLLM, llama.cpp, LM Studio).
# The model must support tool calling. See docs/09-models/NorthCX_Local-Models-Guide.md.
providers:
  - name: local
    type: openai-compatible
    baseUrl: {url}
    allowInsecureHttp: {"true" if url.startswith("http://") and not any(h in url for h in ("//localhost", "//127.0.0.1", "//[::1]")) else "false"}
    defaultModel: {model}
    default: true
    where: local
    capabilities: {{tools: true, parallelTools: false, images: false, maxContextTokens: 32000}}
    prices: {{{model}: {{inputPerMillion: 0, outputPerMillion: 0, currency: USD}}}}
"""


def build(model: dict[str, str], hosts: str = "") -> dict[str, str]:
    """The settings to write: generated secrets, the model choice, optional connector hosts."""
    env = {"NORTHCX_DB_PASSWORD": generate_password(), "NORTHCX_API_KEY": secrets.token_urlsafe(32), "NORTHCX_TOKEN_SECRET": secrets.token_urlsafe(32)}
    env.update(model)
    if hosts:
        env["NORTHCX_CONNECTOR_HOSTS"] = hosts
    return env


def render(env: dict[str, str]) -> str:
    lines = ["# Written by scripts/setup.py. Keep this file private: it holds the admin key and the database password."]
    lines += [f"{k}={v}" for k, v in env.items()]
    return "\n".join(lines) + "\n"


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def problems(env: dict[str, str]) -> list[str]:
    """What is wrong with a `.env`, in words that say what to do."""
    out = []
    pw = env.get("NORTHCX_DB_PASSWORD", "")
    if not pw:
        out.append("NORTHCX_DB_PASSWORD is empty. Set letters and digits only, or run this script again.")
    elif not pw.isalnum():
        out.append("NORTHCX_DB_PASSWORD must be letters and digits only (it goes into a connection URL).")
    if len(env.get("NORTHCX_API_KEY", "")) < MIN_KEY:
        out.append(f"NORTHCX_API_KEY is missing or shorter than {MIN_KEY} characters. It is the admin key; make a long random one, or run this script again.")
    if not (env.get("ANTHROPIC_API_KEY") or env.get("NORTHCX_DEMO") == "1" or env.get("NORTHCX_PROVIDERS_FILE")):
        out.append("No model is set. Set ANTHROPIC_API_KEY, or NORTHCX_PROVIDERS_FILE for a local model, or NORTHCX_DEMO=1 for the offline demo.")
    return out


def ask(question: str, options: list[str]) -> int:
    print(question)
    for i, o in enumerate(options, 1):
        print(f"  {i}. {o}")
    while True:
        got = input("Number: ").strip()
        if got.isdigit() and 1 <= int(got) <= len(options):
            return int(got)
        print(f"Type a number from 1 to {len(options)}.")


def choose_model(args: argparse.Namespace) -> tuple[dict[str, str], str | None]:
    """The model settings, and the text of a providers file when a local model is chosen."""
    if args.demo:
        return {"NORTHCX_DEMO": "1"}, None
    if args.anthropic_key:
        return {"ANTHROPIC_API_KEY": args.anthropic_key}, None
    if args.local_model_url:
        if not args.local_model:
            sys.exit("Give the model's name with --local-model (a model that supports tool calling).")
        return {"NORTHCX_PROVIDERS_FILE": "/config/providers.yaml"}, providers_yaml(args.local_model_url, args.local_model)
    if args.non_interactive:
        sys.exit("Choose a model: --demo, --anthropic-key KEY, or --local-model-url URL with --local-model NAME.")
    pick = ask("Which model should answer?", ["The offline demo (no AI; for trying the console)", "Anthropic (Claude), with an API key", "A model on your own server (Ollama, vLLM and similar)"])
    if pick == 1:
        return {"NORTHCX_DEMO": "1"}, None
    if pick == 2:
        return {"ANTHROPIC_API_KEY": getpass.getpass("Anthropic API key (typing is hidden): ").strip()}, None
    url = input("Address of the server, such as http://host.docker.internal:11434/v1 : ").strip()
    name = input("Model name (it must support tool calling): ").strip()
    return {"NORTHCX_PROVIDERS_FILE": "/config/providers.yaml"}, providers_yaml(url, name)


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write a working .env for NorthCX with generated secrets.")
    ap.add_argument("--dir", default=str(ROOT), help="where .env goes (default: the repository root)")
    ap.add_argument("--demo", action="store_true", help="use the offline demo model (no key, no AI)")
    ap.add_argument("--anthropic-key", help="an Anthropic API key")
    ap.add_argument("--local-model-url", help="address of a local model server (OpenAI chat format)")
    ap.add_argument("--local-model", help="the local model's name (it must support tool calling)")
    ap.add_argument("--connector-hosts", default="", help="hosts your agents' tools may call, comma separated (default: none)")
    ap.add_argument("--force", action="store_true", help="replace an existing .env (the old one is kept as .env.bak-<time>)")
    ap.add_argument("--non-interactive", action="store_true", help="never ask; fail if something is missing")
    ap.add_argument("--check", action="store_true", help="check an existing .env and say what is wrong")
    args = ap.parse_args(argv)
    target = Path(args.dir) / ".env"
    if args.check:
        if not target.exists():
            print(f"{target} does not exist. Run this script without --check to create it.")
            return 1
        found = problems(parse_env(target.read_text()))
        print("\n".join(found) if found else f"{target} looks complete.")
        return 1 if found else 0
    if target.exists():
        if not args.force:
            print(f"{target} already exists, so nothing was changed. Add --force to replace it (the old file is kept), or --check to check it.")
            return 1
        target.rename(target.with_name(f".env.bak-{int(time.time())}"))
    model, providers = choose_model(args)
    env = build(model, args.connector_hosts)
    if providers is not None:
        conf = Path(args.dir) / "config" / "providers.yaml"
        if conf.exists() and not args.force:
            print(f"{conf} already exists; not replacing it.")
        else:
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_text(providers)
    write_private(target, render(env))
    print(f"Wrote {target} (only you can read it). The admin key is in it as NORTHCX_API_KEY: you sign in to the console with it.")
    print("Next:\n  docker compose up -d --build --wait\nThen open http://localhost:3001 (Studio) or http://localhost:3002 (Workspace).")
    if "NORTHCX_DEMO" in model:
        print("The demo model is keyword rules, not an AI. Run this script again with --force and a real model when you are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
