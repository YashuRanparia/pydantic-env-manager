# Problem Statement and Proposed Solution

| | |
|---|---|
| **Status** | Draft |
| **Package name** | `pydantic-env-manager` (import `pydantic_env_manager`); decided, `envsync` is taken on PyPI |
| **Target stack** | Python ≥ 3.9, Pydantic v2, `pydantic-settings` ≥ 2 |
| **Related** | [Scope: v1](scopes/v1.md) |

---

## 1. Background

Python applications that use Pydantic's `BaseSettings` declare their configuration once, in code: names, types, defaults, required-ness and secrets. In practice teams also maintain environment files by hand:

- `.env`: real values, contains secrets, never committed.
- `.env.example`: a committed template so teammates know what to set.

These files describe the same thing as the `Settings` class, but nothing keeps them in step.

## 2. Problem

### 2.1 Drift between code and env files
When a developer adds, renames or removes a field in `Settings`, the env files must be edited manually. This is routinely forgotten, which leads to:

- New teammates cloning the repo and getting a `.env.example` that is missing variables, so the app fails on startup.
- Existing developers pulling a change and hitting a "field required" error because their `.env` lacks the new key.
- `.env.example` accumulating stale variables nobody removed.

### 2.2 Duplicated source of truth
Types, defaults and descriptions exist in `Settings` and are re-typed (or omitted) in `.env.example`. Two copies mean two chances to be wrong.

### 2.3 AI agents and secrets
AI coding tools (Claude Code, Cursor, Copilot, Continue) are increasingly used on codebases. Teams reasonably block agents from reading `.env` because it holds secrets. But the agent then lacks accurate knowledge of which variables exist, their types and their defaults. The only safe place to expose that is `.env.example`, which is only useful if it is accurate and complete.

### 2.4 Existing options fall short

| Option | Gap |
|---|---|
| Hand-maintained `.env.example` | Drifts; no enforcement |
| Ad-hoc 10-line scripts | Not standardised; usually overwrite files or lose comments |
| Secret-sync services (e.g. dotenv-vault) | Solve sharing secrets across a team, not schema/template consistency |
| `pydantic-settings` itself | Reads env files; does not write or reconcile them |

## 3. Goals

1. Make the `Settings` class the **single source of truth** for env configuration.
2. Produce an accurate, annotated, **secret-free `.env.example`** automatically.
3. Keep the real `.env` **complete** (all keys present) without ever destroying user data.
4. Detect drift in CI and pre-commit via a non-zero exit code.
5. Stay lightweight: one runtime dependency (`pydantic-settings`).

### Non-goals
- Storing, encrypting or distributing secrets.
- Replacing `pydantic-settings` loading logic.
- Managing environment-specific files (`.env.test`, `.env.prod`) in v1.

## 4. Proposed solution

A small library and CLI that introspects a `BaseSettings` subclass and reconciles two files against it.

```
            ┌───────────────────┐
            │  Settings class   │  ← single source of truth
            └─────────┬─────────┘
                      │ introspect (schema)
                      ▼
            ┌───────────────────┐
            │  VarSpec list     │  key, type, default, required, secret, description
            └───────┬───────────┘
          ┌─────────┴──────────┐
          ▼                    ▼
  ┌───────────────┐    ┌──────────────────┐
  │ .env.example  │    │ .env             │
  │ regenerated   │    │ merged           │
  │ (fully owned) │    │ (append-only)    │
  └───────────────┘    └──────────────────┘
```

### 4.1 Two files, two ownership models

| File | Ownership | Behaviour |
|---|---|---|
| `.env.example` | Tool owns it entirely | Regenerated deterministically from `Settings`. Safe to overwrite. |
| `.env` | User owns it | Merge only. Existing values, comments and order are preserved. Missing keys are appended. Nothing is deleted. |

This split is the key design decision: the template can be regenerated freely, while the file that holds real secrets is only ever added to.

### 4.2 Interfaces

- **CLI**: `sync` writes both files; `check` verifies without writing and exits non-zero on drift (usable as a CI step or pre-commit hook).
- **Python API**: `sync_env(...)` for explicit calls, and an opt-in `env_sync_on_init=True` that syncs on application boot during local development.

### 4.3 Safety principles

1. **Never destroy `.env` content.** No deletions, no value overwrites.
2. **Never write secrets.** `SecretStr` fields are always blank in generated output.
3. **Idempotent.** Running twice produces no further change; unchanged files are not rewritten.
4. **Atomic writes.** Write to a temp file and rename, so a crash cannot corrupt a file.
5. **Boot sync cannot hurt production.** It is opt-in, skipped when `CI` or `PROD` is set, and a failure only logs a warning.

### 4.4 AI-agent friendliness
The annotated `.env.example` is the agent-readable schema. Teams block `.env` from agents and point them at `.env.example`, which is guaranteed current because it is generated, and contains types, defaults and required markers but no secrets. No separate format is introduced in v1.

## 5. Why this approach

- **Generation over documentation.** A generated file cannot go stale; a documented convention can.
- **Asymmetric treatment of the two files** removes the main risk of such tools (clobbering a developer's `.env`).
- **Minimal dependency footprint** (`pydantic-settings` only, stdlib `argparse`) keeps adoption friction low.

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Parser mangles unusual `.env` syntax (quotes, `export`, multi-line values) | Line-preserving parser; untouched lines are written back byte-for-byte; dedicated tests |
| Boot-time writes surprise users | Opt-in flag, CI/PROD guard, warn-don't-crash |
| Fields with aliases or prefixes produce wrong key names | Single key-resolution function, covered by tests |
| Adoption depends on trust | Small API surface, full pytest coverage, no secret handling |

## 7. Future directions (not in v1)

Nested models (`env_nested_delimiter`), multiple Settings classes and other sources, `.env.test` / `.env.prod` variants, machine-readable schema output, agent-config helpers (e.g. ignore rules), a pre-commit package, and further ways to run it from Python (`python -m <name>`, class-method sugar on `EnvManagedSettings`, import-string targets for `sync_env`).
