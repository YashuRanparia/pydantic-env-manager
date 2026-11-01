import logging

import pytest
from pydantic import AliasChoices, AliasPath, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from envsync import SyncedSettings, check_env, sync_env
from envsync.cli import main
from envsync.envfile import EXTRAS_HEADING, merge
from envsync.schema import collect


class S(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")
    port: int = Field(8000, description="HTTP port")
    debug: bool = False
    name: str  # required
    token: SecretStr = SecretStr("hunter2")
    url: str = Field("x", validation_alias="DB_URL")  # alias bypasses prefix
    multi: str = Field("a", validation_alias=AliasChoices("FIRST", "second"))
    skipped: str = Field("a", validation_alias=AliasPath("a", 0))


def by_key():
    return {s.key: s for s in collect(S)}


def test_key_resolution():
    specs = by_key()
    assert set(specs) == {"APP_PORT", "APP_DEBUG", "APP_NAME", "APP_TOKEN", "DB_URL", "FIRST"}


def test_case_sensitive():
    class C(BaseSettings):
        model_config = SettingsConfigDict(case_sensitive=True)
        Mixed: int = 1

    assert [s.key for s in collect(C)] == ["Mixed"]


def test_spec_values():
    s = by_key()
    assert (s["APP_PORT"].default, s["APP_DEBUG"].default) == ("8000", "false")
    assert s["APP_NAME"].required and s["APP_NAME"].default == ""
    assert s["APP_TOKEN"].secret and s["APP_TOKEN"].default == ""  # secret never leaks


def test_sync_creates_both_files(tmp_path):
    env, ex = tmp_path / ".env", tmp_path / ".env.example"
    assert sync_env(S, env, ex) == (True, True)
    example = ex.read_text()
    assert "# APP_PORT (int, default: 8000) - HTTP port\nAPP_PORT=8000" in example
    assert "# APP_NAME (str, required)\nAPP_NAME=\n" in example
    assert "hunter2" not in example + env.read_text()
    assert "# REQUIRED\nAPP_NAME=\n" in env.read_text()


def test_sync_is_idempotent(tmp_path):
    env, ex = tmp_path / ".env", tmp_path / ".env.example"
    sync_env(S, env, ex)
    assert sync_env(S, env, ex) == (False, False)


def test_env_merge_preserves_and_moves_extras(tmp_path):
    env, ex = tmp_path / ".env", tmp_path / ".env.example"
    env.write_text(
        "# my port\nAPP_PORT=9000  # inline\nOTHER=1\n\n# keep me\nexport APP_NAME='bob'\n"
        'MULTI="line1\nline2"\n# about extra\nEXTRA=2\n'
    )
    sync_env(S, env, ex)
    out = env.read_text()
    assert out.startswith("# my port\nAPP_PORT=9000  # inline\n")  # untouched, in order
    assert "# keep me\nexport APP_NAME='bob'\n" in out
    assert out.index("APP_DEBUG=false") < out.index(EXTRAS_HEADING)  # missing keys before extras
    tail = out[out.index(EXTRAS_HEADING):]
    assert tail == f'{EXTRAS_HEADING}\nOTHER=1\nMULTI="line1\nline2"\n# about extra\nEXTRA=2\n'
    assert out.count(EXTRAS_HEADING) == 1
    assert sync_env(S, env, ex).env_changed is False


def test_merge_noop_returns_text_untouched():
    text = "APP_PORT=1\n\n\n"
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    assert merge(text, specs) == text


def test_merge_case_insensitive_and_crlf():
    specs = [s for s in collect(S) if s.key in ("APP_PORT", "APP_DEBUG")]
    out = merge("app_port=1\r\n", specs)
    assert out == "app_port=1\r\n\r\nAPP_DEBUG=false\r\n"


def test_no_trailing_newline():
    specs = [s for s in collect(S) if s.key in ("APP_PORT", "APP_DEBUG")]
    assert merge("APP_PORT=1", specs) == "APP_PORT=1\n\nAPP_DEBUG=false\n"


def test_check(tmp_path):
    env, ex = tmp_path / ".env", tmp_path / ".env.example"
    assert check_env(S, env, ex).problems  # nothing generated yet
    sync_env(S, env, ex)
    assert check_env(S, env, ex).problems == []
    env.write_text(env.read_text() + "STRAY=1\n")
    r = check_env(S, env, ex)
    assert r.problems == [] and "STRAY" in r.notes[0]  # extras never fail
    env.write_text("APP_PORT=1\n")
    assert "missing" in check_env(S, env, ex).problems[0]
    ex.write_text("stale\n")
    assert any("out of date" in p for p in check_env(S, env, ex).problems)


def test_check_skips_absent_env(tmp_path):
    ex = tmp_path / ".env.example"
    sync_env(S, tmp_path / "tmp.env", ex)
    assert check_env(S, tmp_path / ".env", ex).problems == []


def test_check_does_not_write(tmp_path):
    check_env(S, tmp_path / ".env", tmp_path / ".env.example")
    assert list(tmp_path.iterdir()) == []


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cli_settings.py").write_text(
        "from pydantic_settings import BaseSettings\nclass Settings(BaseSettings):\n    port: int = 1\n"
    )
    assert main(["check", "cli_settings:Settings"]) == 1
    assert main(["sync", "cli_settings:Settings"]) == 0
    assert main(["check", "cli_settings:Settings"]) == 0
    assert (tmp_path / ".env").exists() and (tmp_path / ".env.example").exists()
    with pytest.raises(SystemExit):
        main(["check", "cli_settings:Nope"])


def _boot_cls(tmp_path):
    class B(SyncedSettings):
        model_config = SettingsConfigDict(env_file=str(tmp_path / ".env"))
        sync_out = True
        port: int = 1

    return B


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PROD", raising=False)


def test_boot_sync_writes(tmp_path, clean_env):
    _boot_cls(tmp_path)()
    assert (tmp_path / ".env").exists() and (tmp_path / ".env.example").exists()


@pytest.mark.parametrize("var", ["CI", "PROD"])
def test_boot_sync_skipped_in_ci_or_prod(tmp_path, clean_env, monkeypatch, var):
    monkeypatch.setenv(var, "true")
    _boot_cls(tmp_path)()
    assert list(tmp_path.iterdir()) == []


def test_boot_sync_failure_only_warns(tmp_path, clean_env, caplog):
    cls = _boot_cls(tmp_path / "missing_dir")
    with caplog.at_level(logging.WARNING):
        assert cls().port == 1  # app still starts
    assert "sync failed" in caplog.text


def test_boot_sync_off_by_default(tmp_path, clean_env):
    class Off(SyncedSettings):
        model_config = SettingsConfigDict(env_file=str(tmp_path / ".env"))

    Off()
    assert list(tmp_path.iterdir()) == []
