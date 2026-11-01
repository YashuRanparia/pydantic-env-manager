# pydantic-env-manager

Keep `.env.example` and `.env` in sync with your Pydantic v2 `BaseSettings` class. Declare each variable once, in code; the files follow.

| File | What happens |
|---|---|
| `.env.example` | Regenerated from `Settings` every run: type, default and required-ness, never a secret. |
| `.env` | Merge-only. Missing keys are appended; your values, comments and order are kept; nothing is deleted. |

## Install

```bash
pip install pydantic-env-manager
```

Python ≥ 3.9 and `pydantic-settings` ≥ 2.

## Example

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

Generated `.env.example`:

```
# APP_PORT (int, default: 8000) - HTTP port
APP_PORT=8000

# APP_DEBUG (bool, default: false)
APP_DEBUG=false

# APP_API_KEY (SecretStr, secret, required)
APP_API_KEY=
```

## Python API

```python
from pydantic_env_manager import sync_env, check_env

sync_env(Settings)    # SyncResult(example_changed, env_changed)
check_env(Settings)   # CheckReport(problems, notes)
```

To sync whenever the settings object is created (local dev), subclass `EnvManagedSettings` and set `env_sync_on_init = True`. It is off by default, skipped when `CI` or `PROD` is set, and a write failure only logs a warning.

## Guarantees

- Your `.env` is never overwritten; existing values, comments and order are preserved.
- `SecretStr` / `SecretBytes` values are never written, in any file.
- Idempotent: a second run changes nothing. Writes are atomic.

Full details: [usage guide](https://github.com/YashuRanparia/pydantic-env-manager/blob/main/docs/usage.md).

## License

MIT
