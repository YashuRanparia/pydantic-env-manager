# Plan: Project Setup

| | |
|---|---|
| **Status** | Draft, awaiting approval |
| **Related** | [Scope: v1](../scopes/v1.md), [CLAUDE.md](../../CLAUDE.md) |
| **Goal** | A runnable, testable, installable empty package, so feature work starts on solid ground |

## 1. Decisions needed first

| # | Item | Proposed default |
|---|---|---|
| 1 | Package name | Blocks the `src/<name>/` directory and the PyPI name. Check availability on PyPI before choosing. Candidates: `envsync`, `pydantic-env-sync`. Import name should be a valid identifier (e.g. `envsync`). |
| 2 | Build backend | `hatchling` (zero config for `src/` layout). `setuptools` is the alternative. |
| 3 | Lint / format | `ruff` (dev-only). Skip `black`, `flake8`, `isort`, `mypy` for now. |
| 4 | License | MIT (maximises adoption). Confirm. |
| 5 | Git | Repo is not yet a git repository. `git init` and a first commit are pending your approval. |

## 2. Steps

### Step 1: Scaffold (no logic)
```
pyproject.toml
README.md              # stub: one-line pitch + link to docs
LICENSE
.gitignore             # Python, .venv, dist/, .env (never commit the real one)
src/<name>/__init__.py # __version__ only
src/<name>/py.typed
tests/test_smoke.py    # imports the package, asserts version exists
```

`pyproject.toml` essentials:
- `requires-python = ">=3.9"`
- `dependencies = ["pydantic-settings>=2"]` (only runtime dependency)
- `[project.scripts] <name> = "<name>.cli:main"`
- `[project.optional-dependencies] dev = ["pytest", "ruff"]`
- `[tool.pytest.ini_options]` with `testpaths = ["tests"]`
- `[tool.ruff] target-version = "py39"`

### Step 2: Dev environment
- Create a virtualenv and install editable: `pip install -e ".[dev]"`.
- Verify with `pytest` (smoke test passes) and `ruff check .`.
- Verify the entry point resolves (`<name> --help` once `cli.py` has a stub).

### Step 3: Empty module stubs
Create `schema.py`, `envfile.py`, `render.py`, `cli.py` with only a docstring and the planned public signatures (`NotImplementedError`). This fixes the layout from [v1 scope §5](../scopes/v1.md) and nothing more.

### Step 4: Test fixtures
- `tests/conftest.py` with a small sample `Settings` class covering: default, required field, `SecretStr`, `env_prefix`, alias.
- A `tmp_path`-based helper for reading and writing env files.
- The acceptance checklist in [v1 scope §6](../scopes/v1.md) becomes a list of `xfail` or `skip` placeholder tests, so progress is visible.

### Step 5: CI (GitHub Actions)
- One workflow: matrix Python 3.9 / 3.10 / 3.11 / 3.12 / 3.13.
- Steps: install `.[dev]`, `ruff check`, `pytest`.
- Add a Python 3.9 + `pydantic-settings` minimum-version job later, once real code exists.

### Step 6: First commit
- `git init`, review `git status` with you, then commit the scaffold. Per your standing rule I will show the diff and ask before committing or pushing.

## 3. Deliberately skipped (add when needed)

| Skipped | Add when |
|---|---|
| `mypy` / `pyright` | The code has enough typing surface to be worth gating |
| `pre-commit` config | Contributors other than you appear |
| `tox` / `nox` | Local multi-version testing becomes a pain; CI already covers the matrix |
| Docs site (mkdocs) | Docs outgrow the `docs/` markdown files |
| PyPI release workflow | v1 is feature-complete |
| `CHANGELOG.md` | First release |

## 4. Definition of done

- [ ] `pip install -e ".[dev]"` succeeds on Python 3.9
- [ ] `pytest` passes (smoke test) and `ruff check .` is clean
- [ ] `<name> --help` runs
- [ ] Module layout matches [v1 scope §5](../scopes/v1.md)
- [ ] CI is green on the matrix
- [ ] `CLAUDE.md` updated with the real test and lint commands

## 5. Order of work after setup

1. `schema.py` (key resolution + `VarSpec`)
2. `render.py` (`.env.example`)
3. `envfile.py` (line-preserving merge)
4. `cli.py` (`sync`, `check`)
5. `SyncedSettings` / `sync_out`
6. README with demo and usage
