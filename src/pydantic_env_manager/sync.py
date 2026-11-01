"""Public API: sync_env, check_env and the SyncedSettings boot hook."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, ClassVar, List, NamedTuple, Optional, Tuple, Type, Union

from pydantic_settings import BaseSettings

from . import envfile
from .render import render_example
from .schema import collect

log = logging.getLogger(__name__)
PathLike = Union[str, "os.PathLike[str]"]


class SyncResult(NamedTuple):
    example_changed: bool
    env_changed: bool


class CheckReport(NamedTuple):
    problems: List[str]  # fail the check
    notes: List[str]  # informational only


def _paths(
    cls: Type[BaseSettings], env_file: Optional[PathLike], example_file: Optional[PathLike]
) -> Tuple[Path, Path]:
    if env_file is None:
        cfg = cls.model_config.get("env_file")
        env_file = (cfg[0] if isinstance(cfg, (list, tuple)) else cfg) or ".env"
    env_path = Path(env_file)
    return env_path, Path(example_file) if example_file else env_path.with_name(".env.example")


def _read(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path: Path, text: str, private: bool) -> bool:
    """Atomically write `text`; returns False (and touches nothing) if unchanged."""
    if _read(path) == text:
        return False
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        elif not private:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return True


def _example_text(cls: Type[BaseSettings], example: Path) -> str:
    old = _read(example) or ""
    eol = "\r\n" if "\r\n" in old else "\n"
    return render_example(collect(cls), f"{cls.__module__}.{cls.__qualname__}", eol)


def sync_env(
    cls: Type[BaseSettings], env_file: Optional[PathLike] = None, example_file: Optional[PathLike] = None
) -> SyncResult:
    """Regenerate .env.example and merge missing keys into .env."""
    env, example = _paths(cls, env_file, example_file)
    cs = bool(cls.model_config.get("case_sensitive"))
    merged = envfile.merge(_read(env) or "", collect(cls), cs)
    return SyncResult(
        _write(example, _example_text(cls, example), private=False),
        _write(env, merged, private=True),
    )


def check_env(
    cls: Type[BaseSettings], env_file: Optional[PathLike] = None, example_file: Optional[PathLike] = None
) -> CheckReport:
    """Report drift without writing anything. A missing .env is skipped (e.g. in CI)."""
    env, example = _paths(cls, env_file, example_file)
    problems: List[str] = []
    notes: List[str] = []
    if _read(example) != _example_text(cls, example):
        problems.append(f"{example} is out of date")
    env_text = _read(env)
    if env_text is None:
        notes.append(f"{env} not found, skipped")
    else:
        missing, extra = envfile.missing_and_extra(
            env_text, collect(cls), bool(cls.model_config.get("case_sensitive"))
        )
        if missing:
            problems.append(f"{env} is missing: {', '.join(missing)}")
        if extra:
            notes.append(f"{env} has keys not in settings: {', '.join(extra)}")
    return CheckReport(problems, notes)


def _skip_boot_sync() -> bool:
    return any(os.environ.get(v, "").lower() not in ("", "0", "false") for v in ("CI", "PROD"))


class SyncedSettings(BaseSettings):
    """BaseSettings that syncs .env / .env.example on creation when `sync_out = True`.

    Dev convenience only: skipped when CI or PROD is set; failures only warn.
    """

    sync_out: ClassVar[bool] = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if type(self).sync_out and not _skip_boot_sync():
            try:
                sync_env(type(self))
            except Exception as exc:  # never break the app over a dev convenience
                log.warning("pydantic-env-manager: sync failed: %s", exc)
