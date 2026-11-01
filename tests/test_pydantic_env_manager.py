import logging
from typing import ClassVar

import pytest
from pydantic import AliasChoices, AliasPath, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic_env_manager import EnvManagedSettings, check_env, sync_env
from pydantic_env_manager.cli import main
from pydantic_env_manager.envfile import EXTRAS_HEADING, merge
from pydantic_env_manager.schema import collect


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


def test_classvar_constants_are_not_env_vars():
    class C(BaseSettings):
        name: str = "x"
        MAX_RETRIES: ClassVar[int] = 3

    assert [s.key for s in collect(C)] == ["NAME"]
    assert C().MAX_RETRIES == 3


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
    r = check_env(S, env, ex)
    assert "missing" in r.problems[0] and "APP_PORT" not in r.missing and "APP_NAME" in r.missing
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
    class B(EnvManagedSettings):
        model_config = SettingsConfigDict(env_file=str(tmp_path / ".env"))
        env_sync_on_init = True
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
    class Off(EnvManagedSettings):
        model_config = SettingsConfigDict(env_file=str(tmp_path / ".env"))

    Off()
    assert list(tmp_path.iterdir()) == []


# --- edge cases ---------------------------------------------------------------


def test_unchanged_files_not_rewritten(tmp_path):
    env, ex = tmp_path / ".env", tmp_path / ".env.example"
    sync_env(S, env, ex)
    before = (env.stat().st_ino, env.stat().st_mtime_ns, ex.stat().st_ino, ex.stat().st_mtime_ns)
    sync_env(S, env, ex)
    assert before == (env.stat().st_ino, env.stat().st_mtime_ns, ex.stat().st_ino, ex.stat().st_mtime_ns)


def test_write_is_atomic_on_failure(tmp_path, monkeypatch):
    env, ex = tmp_path / ".env", tmp_path / ".env.example"
    env.write_text("APP_PORT=1\n")
    monkeypatch.setattr("pydantic_env_manager.sync.os.replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        sync_env(S, env, ex)
    assert env.read_text() == "APP_PORT=1\n"  # original intact
    assert not ex.exists()
    assert [p.name for p in tmp_path.iterdir()] == [".env"]  # no temp files left behind


def test_no_temp_files_after_success(tmp_path):
    sync_env(S, tmp_path / ".env", tmp_path / ".env.example")
    assert sorted(p.name for p in tmp_path.iterdir()) == [".env", ".env.example"]


def test_file_modes(tmp_path):
    sync_env(S, tmp_path / ".env", tmp_path / ".env.example")
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / ".env.example").stat().st_mode & 0o777 == 0o644


def test_existing_env_mode_preserved(tmp_path):
    env = tmp_path / ".env"
    env.write_text("X=1\n")
    env.chmod(0o640)
    sync_env(S, env, tmp_path / ".env.example")
    assert env.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize(
    "default, expected",
    [
        ("plain", "plain"),
        ("", ""),
        ("has space", '"has space"'),
        ("a#b", '"a#b"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ("two\nlines", '"two\\nlines"'),
        ("$HOME", '"$HOME"'),
    ],
)
def test_quote(default, expected):
    from pydantic_env_manager.render import quote

    assert quote(default) == expected


def test_special_char_defaults_in_example(tmp_path):
    class Q(BaseSettings):
        a: str = "has space # not a comment"
        b: str = 'q"uote'

    ex = tmp_path / ".env.example"
    sync_env(Q, tmp_path / ".env", ex)
    text = ex.read_text()
    assert 'A="has space # not a comment"\n' in text
    assert 'B="q\\"uote"\n' in text


def test_assorted_field_types(tmp_path):
    import enum
    from typing import Dict, List, Optional

    class Color(enum.Enum):
        RED = "red"

    class T(BaseSettings):
        opt: Optional[str] = None
        opt_req: Optional[int]
        items: List[int] = [1, 2]
        mapping: Dict[str, int] = {"a": 1}
        color: Color = Color.RED
        secret_req: SecretStr

    specs = {s.key: s for s in collect(T)}
    assert set(specs) == {"OPT", "OPT_REQ", "ITEMS", "MAPPING", "COLOR", "SECRET_REQ"}
    assert specs["OPT"].default == ""
    assert specs["OPT_REQ"].required
    assert specs["SECRET_REQ"].required and specs["SECRET_REQ"].default == ""
    ex = tmp_path / ".env.example"
    sync_env(T, tmp_path / ".env", ex)
    assert sync_env(T, tmp_path / ".env", ex) == (False, False)  # still idempotent


def test_empty_settings_class(tmp_path):
    class Empty(BaseSettings):
        pass

    assert collect(Empty) == []
    assert sync_env(Empty, tmp_path / ".env", tmp_path / ".env.example") == (True, True)
    assert sync_env(Empty, tmp_path / ".env", tmp_path / ".env.example") == (False, False)
    assert check_env(Empty, tmp_path / ".env", tmp_path / ".env.example").problems == []


def test_merge_empty_env():
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    assert merge("", specs) == "APP_PORT=8000\n"


def test_merge_malformed_and_duplicate_lines_kept():
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    text = "garbage line\nAPP_PORT=1\nAPP_PORT=2\n=novalue\n"
    out = merge(text, specs)
    assert out == text  # nothing missing, nothing extra: byte-for-byte


def test_merge_comment_stays_with_moved_extra():
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    out = merge("# about x\nX=1\nAPP_PORT=1\n", specs)
    assert out == f"APP_PORT=1\n\n{EXTRAS_HEADING}\n# about x\nX=1\n"


def test_merge_never_duplicates_existing_extras_heading():
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    first = merge("APP_PORT=1\nX=1\n", specs)
    assert merge(first, specs) == first
    assert first.count(EXTRAS_HEADING) == 1


def test_merge_unterminated_quote_does_not_crash():
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    out = merge('BROKEN="never closed\nAPP_PORT=1\n', specs)
    assert "APP_PORT=1" in out and "BROKEN" in out


def test_merge_value_with_hash_and_equals_untouched():
    specs = [s for s in collect(S) if s.key == "APP_PORT"]
    text = "APP_PORT=a=b#c\n"
    assert merge(text, specs) == text


def test_crlf_example_preserved(tmp_path):
    ex = tmp_path / ".env.example"
    ex.write_bytes(b"old\r\n")
    sync_env(S, tmp_path / ".env", ex)
    data = ex.read_bytes()
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")


def test_check_missing_example_is_a_problem(tmp_path):
    (tmp_path / ".env").write_text("")
    assert any("out of date" in p for p in check_env(S, tmp_path / ".env", tmp_path / ".env.example").problems)


def test_env_file_taken_from_model_config(tmp_path):
    class C(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(tmp_path / "custom.env"))
        a: int = 1

    sync_env(C)
    assert (tmp_path / "custom.env").exists() and (tmp_path / ".env.example").exists()


def test_cli_bad_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["check", "no_colon_here"])
    with pytest.raises(SystemExit):
        main(["check", "does_not_exist_mod:Settings"])
