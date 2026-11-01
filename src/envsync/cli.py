"""Command line interface: `envsync sync|check module:Class`."""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from typing import List, Optional

from pydantic_settings import BaseSettings

from .sync import check_env, sync_env


def _load(target: str) -> type:
    module, _, name = target.partition(":")
    if not module or not name:
        raise SystemExit(f"error: expected 'module:Class', got {target!r}")
    sys.path.insert(0, os.getcwd())  # console scripts don't have cwd on sys.path
    try:
        cls = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError) as exc:
        raise SystemExit(f"error: cannot load {target}: {exc}")
    if not (isinstance(cls, type) and issubclass(cls, BaseSettings)):
        raise SystemExit(f"error: {target} is not a pydantic-settings BaseSettings subclass")
    return cls


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="envsync", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_ in (("sync", "write .env.example and merge into .env"), ("check", "exit 1 if files have drifted")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("target", help="import path, e.g. app.settings:Settings")
        s.add_argument("--env", help="default: the class's env_file, else .env")
        s.add_argument("--example", help="default: .env.example next to the env file")
    args = p.parse_args(argv)
    cls = _load(args.target)

    if args.command == "sync":
        res = sync_env(cls, args.env, args.example)
        print("updated" if any(res) else "already in sync")
        return 0
    report = check_env(cls, args.env, args.example)
    for line in report.notes:
        print(f"note: {line}")
    for line in report.problems:
        print(f"drift: {line}", file=sys.stderr)
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
