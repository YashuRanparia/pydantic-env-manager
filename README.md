# pydantic-env-manager

**Stop hand-editing `.env.example`. Your `Settings` class already knows every variable. Let it write the files.**

```bash
pip install pydantic-env-manager
pydantic-env-manager sync app.settings:Settings
```

That's the whole setup. Declare each variable once, in your Pydantic v2 `BaseSettings` class, and `.env.example` and `.env` follow.

## Sound familiar?

- A teammate adds `STRIPE_WEBHOOK_SECRET` to the code and forgets `.env.example`. You find out when staging crashes.
- A new hire clones the repo, copies `.env.example`, and spends an hour finding which variables are missing.
- `.env.example` says `PORT=3000`. The code says `8000`. Nobody knows which is right.
- You don't want a tool that rewrites your `.env` and wipes the values you tuned.

`pydantic-env-manager` fixes this, and it's safe to run on a real project.

## What you get

| File | What happens |
|---|---|
| `.env.example` | Regenerated from `Settings` on every run, with type, default and required-ness for each variable. It never holds a secret. |
| `.env` | Merge-only. Missing keys are appended. Your values, comments and order stay exactly as you left them. Nothing is deleted. |

## See it work

```python
# app/settings.py
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")

    port: int = Field(8000, description="HTTP port")
    debug: bool = False
    api_key: SecretStr  # required, no default
```

```bash
pydantic-env-manager sync  app.settings:Settings   # write .env.example, merge missing keys into .env
pydantic-env-manager check app.settings:Settings   # write nothing; exit 1 if files have drifted (CI-friendly)
```

Your generated `.env.example`:

```
# APP_PORT (int, default: 8000) - HTTP port
APP_PORT=8000

# APP_DEBUG (bool, default: false)
APP_DEBUG=false

# APP_API_KEY (SecretStr, secret, required)
APP_API_KEY=
```

Your existing `.env` keeps `APP_PORT=9000` and every comment you wrote. Only the keys it was missing are added.

## Why you can trust it with your `.env`

- **Your `.env` is never overwritten.** Existing values, comments and order are preserved. Unrecognised keys are kept too.
- **Secrets are never written.** `SecretStr` and `SecretBytes` values stay blank in every file.
- **Running it twice changes nothing.** Unchanged files aren't rewritten, and writes are atomic, so a crash can't leave a half-written file.
- **One dependency.** It needs only `pydantic-settings`. The CLI uses the standard library.

## Catch drift before it ships

`check` writes nothing and exits `1` if `.env.example` is stale or `.env` is missing keys. Add it to CI and a forgotten variable fails the build instead of production:

```bash
pydantic-env-manager check app.settings:Settings
```

It also works as a pre-commit hook. See the [usage guide](https://github.com/YashuRanparia/pydantic-env-manager/blob/main/docs/usage.md).

## Prefer to stay in Python?

```python
from pydantic_env_manager import sync_env, check_env

sync_env(Settings)    # SyncResult(example_changed, env_changed)
check_env(Settings)   # CheckReport(problems, notes, missing)
```

For local dev, subclass `EnvManagedSettings` and set `env_sync_on_init = True`. Both files then sync whenever your settings load. It's opt-in and skipped when `CI` or `PROD` is set. If a write fails, it logs a warning and your app still starts.

## Great with AI coding agents

Deny your agent access to `.env` and point it at `.env.example`. That file always matches your code and lists every variable with its type, default and required-ness. It holds no secret values, so the agent gets the full picture and none of your credentials.

## Try it in two minutes

1. `pip install pydantic-env-manager`
2. Run `pydantic-env-manager sync your_module:Settings`
3. Open `.env.example` to see your variables. Your `.env` only gains missing keys; none of your existing values change.

Requires Python ≥ 3.9 and `pydantic-settings` ≥ 2. Full details are in the [usage guide](https://github.com/YashuRanparia/pydantic-env-manager/blob/main/docs/usage.md).

## License

MIT
