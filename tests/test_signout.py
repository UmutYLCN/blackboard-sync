"""Full sign-out removes the session and all login data, and only that."""

from __future__ import annotations

import os
import sys

import pytest

from blackboard_sync import signout
from blackboard_sync.menubar import jobs
from blackboard_sync.session import save_session


def seed(config):
    config.ensure_data_dir()
    save_session(config.session_file, config.base_url,
                 [{"name": "auth", "value": "x", "domain": "blackboard.example.edu"}], {"id": "1"})
    for profile in (config.profile_dir, config.inapp_profile_dir):
        (profile / "Default" / "Cookies").parent.mkdir(parents=True)
        (profile / "Default" / "Cookies").write_bytes(b"idp")
    config.state_file.write_text('{"keep": 1}')
    config.settings_file.write_text('{"keep": 2}')
    config.dest.mkdir(parents=True, exist_ok=True)
    (config.dest / "lecture.pdf").write_bytes(b"pdf")


def test_sign_out_removes_session_and_all_login_data_only(config):
    seed(config)
    cleared = []
    assert signout.sign_out(config, clear_web=lambda: cleared.append(1)) == []
    assert not config.session_file.exists()
    assert not config.profile_dir.exists() and not config.inapp_profile_dir.exists()
    assert cleared == [1]
    assert config.state_file.read_text() == '{"keep": 1}'
    assert config.settings_file.read_text() == '{"keep": 2}'
    assert (config.dest / "lecture.pdf").read_bytes() == b"pdf"
    signout.sign_out(config, clear_web=lambda: None)  # nothing left: still fine


def test_sign_out_through_the_menu_job(config, monkeypatch):
    seed(config)
    monkeypatch.setattr(signout, "clear_webkit_data", lambda: None)
    assert jobs.logout(config) == []
    assert not config.session_file.exists() and not config.profile_dir.exists()
    assert config.state_file.exists()


def test_sign_out_never_touches_paths_outside_the_data_directory(config, tmp_path):
    seed(config)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    if sys.platform != "win32":
        config.profile_dir.rename(config.data_dir / "moved")
        os.symlink(outside, config.profile_dir)  # a link where the profile should be
    signout.sign_out(config, clear_web=lambda: None)
    assert (outside / "precious.txt").read_text() == "keep"
    assert not config.profile_dir.is_symlink()
    assert {p.name for p in signout.login_data_dirs(config)} == {"browser-profile", "inapp-profile"}
    assert all(p.parent == config.data_dir for p in signout.login_data_dirs(config))


def test_locked_profile_becomes_a_warning_after_the_rest_is_removed(config, monkeypatch):
    seed(config)
    real = signout.shutil.rmtree

    def rmtree(path, *a, **kw):
        if str(path).endswith("browser-profile"):
            raise PermissionError(13, "in use", str(path))
        return real(path, *a, **kw)

    monkeypatch.setattr(signout.shutil, "rmtree", rmtree)
    sleeps = []
    warnings = signout.sign_out(config, clear_web=lambda: None, sleep=sleeps.append)
    assert warnings == [signout.LOCKED_WARNING]
    assert len(sleeps) == signout.RETRIES - 1
    assert not config.session_file.exists() and not config.inapp_profile_dir.exists()
    assert config.profile_dir.exists()
    assert config.state_file.exists()


def test_a_file_released_during_the_retries_is_removed(config, monkeypatch):
    seed(config)
    real = signout.shutil.rmtree
    calls = []

    def rmtree(path, *a, **kw):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError(13, "in use", str(path))
        return real(path, *a, **kw)

    monkeypatch.setattr(signout.shutil, "rmtree", rmtree)
    assert signout.sign_out(config, clear_web=lambda: None, sleep=lambda s: None) == []
    assert not config.profile_dir.exists()


def test_webkit_failure_is_a_warning_not_a_crash(config):
    seed(config)

    def boom():
        raise RuntimeError("no WebKit")

    assert signout.sign_out(config, clear_web=boom) == [signout.LOCKED_WARNING]
    assert not config.session_file.exists()


def test_session_file_failure_still_raises(config, monkeypatch):
    seed(config)
    monkeypatch.setattr(type(config.session_file), "unlink",
                        lambda self, missing_ok=False: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(OSError):
        signout.sign_out(config, clear_web=lambda: None)
