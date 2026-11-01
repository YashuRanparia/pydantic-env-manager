# pydantic-env-manager

Python library and CLI that keeps `.env.example` and `.env` in sync with a Pydantic v2 `BaseSettings` class (the single source of truth). Package name: `pydantic-env-manager` (import `pydantic_env_manager`).

Status: v1 implemented. Read these before changing anything:
- `.local/problem-and-solution.md` for the problem and design
- `.local/scopes/v1.md` for the agreed v1 scope, requirements, and acceptance checklist

## Stack

- Python ≥ 3.9 (no 3.10+ syntax: no `X | Y` types or `match` at runtime; use `from __future__ import annotations` / `typing.Optional`)
- `pydantic-settings` ≥ 2 is the **only** runtime dependency. CLI uses stdlib `argparse`.
- `src/` layout, `pyproject.toml`, `pytest` for tests

## Layout

```
src/pydantic_env_manager/  __init__.py  sync.py  schema.py  envfile.py  render.py  cli.py
tests/        test_pydantic_env_manager.py
docs/         usage.md
.local/       (gitignored) problem-and-solution.md  scopes/v1.md  plans/project-setup.md
```

## Commands

```bash
uv venv .venv && uv pip install --link-mode copy --python .venv/bin/python -e ".[dev]"  # setup
.venv/bin/python -m pytest -q    # tests
.venv/bin/ruff check .           # lint
```

## Hard rules (from the v1 scope)

1. **`.env.example` is tool-owned.** Regenerate it fully and deterministically; stale keys are dropped.
2. **`.env` is user-owned and merge-only.** Never delete a key, never overwrite a value, preserve comments and order. Unrelated lines are written back byte-for-byte. Keys not in Settings go to the end under `# Your additional env variables`.
3. **Never write secret values.** `SecretStr` fields are always blank in every output.
4. **Idempotent and atomic.** A second run changes nothing (don't rewrite unchanged files); write to a temp file, then rename.
5. **`env_sync_on_init=True` must never hurt the app.** Opt-in only, skipped when `CI` or `PROD` is set, failures log a warning and never raise.
6. **One key-resolution function** (`env_prefix` + alias/field name, uppercase unless `case_sensitive`) shared by both files. Don't duplicate this logic.

## Out of scope for v1 (don't build)

Nested models, multiple Settings classes or non-env sources, `.env.test`/`.env.prod`, machine-readable schema output, agent-config snippets, a pre-commit package, `typer`/`click`, `python -m` entry point, `EnvManagedSettings` class-method sugar, stricter agent-facing `check` (required/blank/`os.environ`/`--json`), import-string targets for `sync_env`. Raise it instead of adding it.

## Working conventions

- Keep it small: fewest files and the least code that meets `.local/scopes/v1.md`. No speculative abstractions.
- Any new behaviour needs a pytest case; the acceptance checklist in `.local/scopes/v1.md` is the minimum test list.
- If a requirement is ambiguous, update the docs (and the open-items table in `.local/scopes/v1.md`) rather than silently deciding in code.
