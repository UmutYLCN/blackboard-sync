"""Staying signed in by itself: the background sign-in, the keep-alive and what the app does with them.

The browser is faked: real-browser behaviour is measured by hand (docs/DEVELOPMENT.md).
"""

import json
import os
import plistlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from blackboard_sync import cli, login as login_mod
from blackboard_sync import session_refresh as sr
from blackboard_sync.errors import EXIT_LOCKED, EXIT_LOGIN_REQUIRED, EXIT_OK
from blackboard_sync.login import DEVTOOLS_PORT_FILE, SINGLETON_LOCK, ProfileBusy, profile_in_use, profile_lock
from blackboard_sync.menubar import jobs, main_window_model, settings_form
from blackboard_sync.menubar.model import SESSION_JOB, AppModel, RunOutcome
from blackboard_sync.session import load_session, save_session, session_expires_at
from blackboard_sync.settings import Settings, load_settings, save_settings
from blackboard_sync.sync import run_lock

from .conftest import BASE_URL

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
DEST = Path(os.path.abspath("/Users/student/Documents"))
SETTINGS = Settings(base_url=BASE_URL, dest=DEST)
USER = {"id": "_1_1", "userName": "ada"}
# Chromium's SingletonLock is a link on macOS, and making one takes extra rights on Windows.
needs_links = pytest.mark.skipif(sys.platform == "win32", reason="SingletonLock is a macOS link")
OLD = [{"name": "BbRouter", "value": "old", "domain": "blackboard.example.edu", "path": "/"}]
NEW = [{"name": "BbRouter", "value": "new", "domain": "blackboard.example.edu", "path": "/", "secure": True,
        "expires": -1}]


class FakeLocator:
    def __init__(self, page):
        self.page = page

    def count(self):
        return 1 if self.page.password else 0


class FakePage:
    """Only what may be done with a page; filling in a form would fail here."""

    def __init__(self, url="about:blank", password=False):
        self.url, self.password = url, password
        self.opened = []

    def goto(self, url, **kwargs):
        self.opened.append(url)

    def locator(self, selector):
        assert "password" in selector
        return FakeLocator(self)


class FakeContext:
    def __init__(self, cookies, page):
        self._cookies, self.pages = cookies, [page]
        self.cleared = []

    def clear_cookies(self, domain=None):
        self.cleared.append(domain)

    def cookies(self, url):
        return self._cookies


class FakeBrowser:
    def __init__(self, context):
        self.contexts = [context]
        self.closed = False

    def new_browser_cdp_session(self):
        browser = self

        class Session:
            def send(self, method):
                browser.closed = True

        return Session()

    def close(self):
        pass


class FakeProcess:
    def __init__(self, stubborn=0):
        self.stubborn = stubborn
        self.stopped = []

    def wait(self, timeout=None):
        if self.stubborn:
            self.stubborn -= 1
            raise subprocess.TimeoutExpired("browser", timeout)

    def terminate(self):
        self.stopped.append("terminate")

    def kill(self):
        self.stopped.append("kill")


def browser_app(tmp_path, name="Google Chrome.app", exe="Google Chrome"):
    apps = tmp_path / "apps"
    contents = apps / name / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": exe}))
    return apps


class Rig:
    """A signed-in student's data folder and a fake browser to sign in with."""

    def __init__(self, config, tmp_path, monkeypatch, process=None):
        monkeypatch.setattr(sr, "POLL_SECONDS", 0)
        monkeypatch.setattr(login_mod, "is_windows", lambda platform=None: False)
        monkeypatch.setattr(sr, "is_windows", lambda platform=None: False)
        self.config = config
        config.ensure_data_dir()
        config.profile_dir.mkdir()
        save_session(config.session_file, BASE_URL, OLD, USER)
        self.apps = [browser_app(tmp_path)]
        self.process = process or FakeProcess()
        self.started = []

    def spawn(self, argv, **kwargs):
        self.started.append((argv, kwargs))
        (self.config.profile_dir / DEVTOOLS_PORT_FILE).write_text("40000\n/devtools/browser/x\n")
        return self.process

    def run(self, browser, check_user=lambda base, cookies: USER, timeout=5):
        self.browser = browser
        return sr.silent_sign_in(self.config, timeout=timeout, spawn=self.spawn, connect=lambda url: browser,
                                 check_user=check_user, app_dirs=self.apps, platform="darwin")


@pytest.fixture
def rig(config, tmp_path, monkeypatch):
    return Rig(config, tmp_path, monkeypatch)


# -- the background sign-in -------------------------------------------------------------------------
def test_a_valid_single_sign_on_saves_new_cookies_with_no_window(rig):
    page = FakePage()
    context = FakeContext(NEW, page)
    result = rig.run(FakeBrowser(context))

    assert result.ok and result.reason == sr.REFRESHED
    assert [c["value"] for c in load_session(rig.config.session_file, BASE_URL)["cookies"]] == ["new"]
    assert page.opened == [BASE_URL + "/"]
    # The old session may still work; only a new one is a refresh.
    assert context.cleared == ["blackboard.example.edu"]
    assert rig.browser.closed and not rig.process.stopped

    argv, options = rig.started[0]
    assert Path(argv[0]).parts[-4:] == ("Google Chrome.app", "Contents", "MacOS", "Google Chrome")
    assert f"--user-data-dir={rig.config.profile_dir}" in argv  # the profile that holds the sign-on
    assert "--headless=new" in argv and "--restore-last-session" in argv
    assert "/usr/bin/open" not in argv  # LaunchServices would make it a frontmost app
    assert options["start_new_session"] is True


def test_a_password_page_ends_it_at_once_and_keeps_the_old_session(rig):
    page = FakePage("https://login.school.edu/sso", password=True)
    result = rig.run(FakeBrowser(FakeContext(OLD, page)), check_user=lambda base, cookies: None, timeout=30)

    assert result.reason == sr.NEEDS_INTERACTION and not result.ok
    assert [c["value"] for c in load_session(rig.config.session_file, BASE_URL)["cookies"]] == ["old"]
    assert rig.browser.closed


def test_stuck_at_the_school_means_it_wants_the_student(rig):
    page = FakePage("https://login.school.edu/pick-an-account")
    result = rig.run(FakeBrowser(FakeContext([], page)), check_user=lambda base, cookies: None, timeout=0.05)
    assert result.reason == sr.NEEDS_INTERACTION


def test_stuck_on_blackboard_is_a_timeout(rig):
    page = FakePage(BASE_URL + "/ultra")
    result = rig.run(FakeBrowser(FakeContext(OLD, page)), check_user=lambda base, cookies: None, timeout=0.05)
    assert result.reason == sr.TIMED_OUT


def test_the_browser_is_always_stopped(config, tmp_path, monkeypatch):
    stubborn = FakeProcess(stubborn=2)
    rig = Rig(config, tmp_path, monkeypatch, process=stubborn)
    monkeypatch.setattr(sr, "BROWSER_QUIT_TIMEOUT", 0)
    rig.run(FakeBrowser(FakeContext(NEW, FakePage())))
    assert stubborn.stopped == ["terminate", "kill"]


def test_a_browser_that_does_not_start_is_reported(rig, monkeypatch):
    def nothing(profile, timeout):
        raise login_mod.BrowserStartError("no")

    monkeypatch.setattr(sr, "wait_for_devtools_port", nothing)
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.BROWSER_FAILED
    assert rig.process.stopped == []  # wait() returned: it was gone already


def test_no_browser_no_attempt(rig, tmp_path):
    rig.apps = [tmp_path / "empty"]
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.BROWSER_MISSING
    assert rig.started == []


def test_arc_is_not_started_in_the_background(rig, tmp_path):
    rig.apps = [browser_app(tmp_path / "arc", "Arc.app", "Arc")]
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.BROWSER_MISSING
    assert rig.started == []


def test_nothing_to_refresh_when_never_signed_in(rig):
    rig.config.session_file.unlink()
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.NOT_SIGNED_IN
    assert rig.started == []


def test_a_session_of_another_school_is_not_refreshed(rig):
    save_session(rig.config.session_file, "https://other.example.edu", OLD, USER)
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.NOT_SIGNED_IN


def test_signed_in_through_the_app_window_there_is_no_profile(rig):
    rig.config.profile_dir.rmdir()
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.NOT_SIGNED_IN


@needs_links
def test_a_browser_running_on_the_profile_is_left_alone(rig):
    os.symlink(f"host-{os.getpid()}", rig.config.profile_dir / SINGLETON_LOCK)
    assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.PROFILE_BUSY
    assert rig.started == []


def test_an_interactive_sign_in_holding_the_profile_is_left_alone(rig):
    with profile_lock(rig.config):
        assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.PROFILE_BUSY
    assert rig.started == []


def test_a_running_sync_keeps_its_session(rig):
    with run_lock(rig.config.lock_file):
        assert rig.run(FakeBrowser(FakeContext(NEW, FakePage()))).reason == sr.LOCKED
    assert rig.started == []


def test_the_profile_is_free_again_afterwards(rig):
    rig.run(FakeBrowser(FakeContext(NEW, FakePage())))
    with profile_lock(rig.config):
        pass


@needs_links
def test_a_lock_left_by_a_crash_does_not_count(tmp_path):
    os.symlink("host-123", tmp_path / SINGLETON_LOCK)
    assert not profile_in_use(tmp_path, alive=lambda pid: False)
    assert profile_in_use(tmp_path, alive=lambda pid: True)
    assert not profile_in_use(tmp_path / "missing")


def test_an_interactive_sign_in_waits_for_the_profile_then_gives_up(config):
    with profile_lock(config):
        with pytest.raises(ProfileBusy):
            with profile_lock(config, wait=0.05):
                pytest.fail("two sign-ins on one profile")


# -- the command ------------------------------------------------------------------------------------
@pytest.mark.parametrize("reason,code", [(sr.REFRESHED, EXIT_OK), (sr.NEEDS_INTERACTION, EXIT_LOGIN_REQUIRED),
                                         (sr.LOCKED, EXIT_LOCKED)])
def test_the_command_reports_how_it_ended(reason, code, tmp_path, monkeypatch, capsys):
    import signal

    monkeypatch.setattr(sr, "silent_sign_in", lambda config: sr.RefreshResult(reason, 3.21))
    before = signal.getsignal(signal.SIGTERM)
    try:
        assert cli.main(["--data-dir", str(tmp_path), "refresh-session", "--json"]) == code
    finally:
        signal.signal(signal.SIGTERM, before)
    assert json.loads(capsys.readouterr().out) == {"status": reason, "seconds": 3.2}


# -- the keep-alive ---------------------------------------------------------------------------------
class FakeHttp(requests.Session):
    def __init__(self, status=200, rotate=False, error=None):
        super().__init__()
        self.status, self.rotate, self.error = status, rotate, error
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if self.error:
            raise self.error
        if self.rotate:
            self.cookies.set("BbRouter", "expires:5000,id:x", domain="blackboard.example.edu", path="/")
        response = requests.Response()
        response.status_code, response.url = self.status, url
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps({"id": "_1_1"}).encode()
        return response


def signed_in(config, monkeypatch, http):
    config.ensure_data_dir()
    save_session(config.session_file, BASE_URL, OLD, USER)
    monkeypatch.setattr(sr, "http_session", lambda data: http)
    return http


def test_keep_alive_is_one_light_request_and_saves_rotated_cookies(config, monkeypatch):
    http = signed_in(config, monkeypatch, FakeHttp(rotate=True))
    alive = sr.keep_alive(config)
    assert alive == sr.KeepAlive(sr.ALIVE, 5000.0)
    assert len(http.urls) == 1 and http.urls[0].endswith("/users/me")


@pytest.mark.parametrize("http,status", [
    (FakeHttp(status=401), sr.EXPIRED),
    (FakeHttp(error=requests.ConnectionError("offline")), sr.UNREACHABLE),
    (FakeHttp(status=503), sr.UNREACHABLE),
])
def test_keep_alive_tells_a_lost_session_from_a_lost_network(config, monkeypatch, http, status):
    signed_in(config, monkeypatch, http)
    assert sr.keep_alive(config).status == status


def test_keep_alive_without_a_session_asks_nothing(config, monkeypatch):
    http = FakeHttp()
    monkeypatch.setattr(sr, "http_session", lambda data: http)
    assert sr.keep_alive(config).status == sr.NOT_SIGNED_IN and http.urls == []


def test_keep_alive_stays_out_of_a_running_sync(config, monkeypatch):
    http = signed_in(config, monkeypatch, FakeHttp())
    with run_lock(config.lock_file):
        assert sr.keep_alive(config).status == sr.LOCKED
    assert http.urls == []


def test_the_expiry_is_read_from_blackboards_cookie_only():
    router = {"name": "BbRouter", "value": "expires:1800000000,id:A,signature:b,timeout:10800"}
    assert session_expires_at({"cookies": [{"name": "JSESSIONID", "value": "expires:1"}, router]}) == 1800000000
    assert session_expires_at({"cookies": [{"name": "BbRouter", "value": "something else"}]}) is None
    assert session_expires_at({"cookies": [{"name": "BbRouter", "value": None}]}) is None
    assert session_expires_at({}) is None


def test_a_session_about_to_end_is_replaced_before_the_next_look():
    soon = (NOW + sr.EXPIRY_MARGIN - timedelta(minutes=1)).timestamp()
    later = (NOW + sr.EXPIRY_MARGIN + timedelta(minutes=1)).timestamp()
    assert sr.KeepAlive(sr.ALIVE, soon).wants_refresh(NOW)
    assert not sr.KeepAlive(sr.ALIVE, later).wants_refresh(NOW)
    assert not sr.KeepAlive(sr.ALIVE, None).wants_refresh(NOW)
    assert sr.KeepAlive(sr.EXPIRED).wants_refresh(NOW)
    assert not sr.KeepAlive(sr.UNREACHABLE, soon).wants_refresh(NOW)
    assert sr.EXPIRY_MARGIN > sr.KEEP_ALIVE_EVERY


# -- when: SessionCare ------------------------------------------------------------------------------
def test_keep_alive_schedule():
    care = sr.SessionCare(checked_at=NOW)
    assert not care.keep_alive_due(NOW + sr.KEEP_ALIVE_EVERY - timedelta(seconds=1))
    assert care.keep_alive_due(NOW + sr.KEEP_ALIVE_EVERY)
    assert care.keep_alive_due(NOW - timedelta(minutes=1))  # the clock went back
    assert not sr.SessionCare(enabled=False, checked_at=NOW).keep_alive_due(NOW + timedelta(days=1))


def test_a_failure_holds_the_next_attempt_back():
    care = sr.SessionCare()
    assert care.may_refresh(NOW)
    care.record(sr.RefreshResult(sr.NEEDS_INTERACTION), NOW)
    assert not care.may_refresh(NOW + sr.FAILED_RETRY_AFTER - timedelta(seconds=1))
    assert care.may_refresh(NOW + sr.FAILED_RETRY_AFTER)
    care.record(sr.RefreshResult(sr.REFRESHED), NOW)
    assert care.may_refresh(NOW) and care.refreshed_at == NOW
    assert not sr.SessionCare(enabled=False).may_refresh(NOW)


# -- the sync that signs in again -------------------------------------------------------------------
def stub_sync(monkeypatch, *statuses):
    runs = list(statuses)
    monkeypatch.setattr(jobs, "run_sync_guarded",
                        lambda job, settings, term_name="", term_id="", runner=None: RunOutcome(status=runs.pop(0)))
    return runs


def stub_refresh(monkeypatch, result):
    calls = []

    def refresh(settings, runner=None):
        calls.append(settings)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(jobs, "run_session_refresh", refresh)
    return calls


def test_a_sync_that_lost_its_session_signs_in_and_runs_once_more(monkeypatch):
    runs = stub_sync(monkeypatch, "login_required", "ok")
    done = sr.RefreshResult(sr.REFRESHED, 4.0)
    calls = stub_refresh(monkeypatch, done)
    outcome, refresh = jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=True)
    assert outcome.status == "ok" and refresh == done and len(calls) == 1 and runs == []


def test_when_the_school_wants_the_student_the_sync_stays_as_it_was(monkeypatch):
    runs = stub_sync(monkeypatch, "login_required", "ok")
    stub_refresh(monkeypatch, sr.RefreshResult(sr.NEEDS_INTERACTION))
    outcome, refresh = jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=True)
    assert outcome.status == "login_required" and refresh.reason == sr.NEEDS_INTERACTION
    assert runs == ["ok"]  # not run again


def test_a_second_lost_session_is_not_tried_twice(monkeypatch):
    stub_sync(monkeypatch, "login_required", "login_required")
    calls = stub_refresh(monkeypatch, sr.RefreshResult(sr.REFRESHED))
    outcome, _ = jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=True)
    assert outcome.status == "login_required" and len(calls) == 1


@pytest.mark.parametrize("may_refresh,wanted", [(False, True), (True, False)])
def test_no_attempt_when_held_back_or_paused(monkeypatch, may_refresh, wanted):
    stub_sync(monkeypatch, "login_required")
    calls = stub_refresh(monkeypatch, sr.RefreshResult(sr.REFRESHED))
    outcome, refresh = jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=may_refresh, wanted=lambda: wanted)
    assert outcome.status == "login_required" and refresh is None and calls == []


def test_no_attempt_for_other_results(monkeypatch):
    stub_sync(monkeypatch, "error")
    calls = stub_refresh(monkeypatch, sr.RefreshResult(sr.REFRESHED))
    assert jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=True)[0].status == "error" and calls == []


def test_pausing_during_the_sign_in_ends_it_as_a_pause(monkeypatch):
    stub_sync(monkeypatch, "login_required")
    stub_refresh(monkeypatch, jobs.SyncStopped())
    outcome, refresh = jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=True)
    assert outcome.status == "paused" and refresh is None


def test_paused_right_after_the_sign_in_no_sync_follows(monkeypatch):
    runs = stub_sync(monkeypatch, "login_required", "ok")
    done = sr.RefreshResult(sr.REFRESHED)
    stub_refresh(monkeypatch, done)
    answers = iter([True, False])
    outcome, refresh = jobs.run_sync_refreshing("sync", SETTINGS, may_refresh=True, wanted=lambda: next(answers))
    assert outcome.status == "paused" and refresh == done and runs == ["ok"]


def test_the_child_process_reports_through_json():
    def runner(cmd, **kwargs):
        assert cmd[-4:] == ["--base-url", BASE_URL, "refresh-session", "--json"]
        return subprocess.CompletedProcess(cmd, 3, json.dumps({"status": sr.TIMED_OUT, "seconds": 45.2}), "")

    assert jobs.run_session_refresh(SETTINGS, runner) == sr.RefreshResult(sr.TIMED_OUT, 45.2)


@pytest.mark.parametrize("failure,reason", [
    (subprocess.TimeoutExpired("x", 1), sr.TIMED_OUT), (OSError("gone"), sr.FAILED), (None, sr.FAILED),
])
def test_a_child_process_that_says_nothing_is_a_failure(failure, reason):
    def runner(cmd, **kwargs):
        if failure:
            raise failure
        return subprocess.CompletedProcess(cmd, 1, "not json", "")

    assert jobs.run_session_refresh(SETTINGS, runner).reason == reason


def test_a_session_check_only_signs_in_when_it_has_to(config, monkeypatch):
    calls = stub_refresh(monkeypatch, sr.RefreshResult(sr.REFRESHED))
    monkeypatch.setattr(sr, "keep_alive", lambda cfg: sr.KeepAlive(sr.ALIVE))
    assert jobs.run_session_check(config, SETTINGS, True) == jobs.SessionCheck(sr.ALIVE)
    monkeypatch.setattr(sr, "keep_alive", lambda cfg: sr.KeepAlive(sr.EXPIRED))
    assert jobs.run_session_check(config, SETTINGS, False) == jobs.SessionCheck(sr.EXPIRED)
    assert calls == []
    assert jobs.run_session_check(config, SETTINGS, True).refresh.ok and len(calls) == 1


def test_a_session_check_never_raises(config, monkeypatch):
    def boom(cfg):
        raise RuntimeError("no")

    monkeypatch.setattr(sr, "keep_alive", boom)
    assert jobs.run_session_check(config, SETTINGS, True).status == sr.UNREACHABLE


# -- the model --------------------------------------------------------------------------------------
def model_signed_in(**kwargs) -> AppModel:
    model = AppModel(DEST, NOW, **kwargs)
    model.session = {"saved_at": NOW.timestamp(), "user": {"displayName": "Ada"}}
    return model


LATER = NOW + sr.KEEP_ALIVE_EVERY


def test_the_session_is_looked_at_between_syncs():
    model = model_signed_in()
    assert not model.session_check_due(NOW)
    assert model.session_check_due(LATER)
    assert model.begin(SESSION_JOB) and not model.session_check_due(LATER)  # it holds the slot
    assert model.menu(LATER).entries  # and the menu has nothing to say about it
    assert model.activity() == "" and model.icon().value == "idle"


def test_a_finished_sync_counts_as_a_look():
    model = model_signed_in()
    model.begin("sync")
    model.finish_sync(RunOutcome(status="ok", finished_at=LATER), LATER)
    assert not model.session_check_due(LATER) and model.session_check_due(LATER + sr.KEEP_ALIVE_EVERY)


@pytest.mark.parametrize("change", ["paused", "signed_out", "setting_off", "busy", "unconfigured", "queued"])
def test_no_requests_while_it_should_be_quiet(change):
    model = model_signed_in()
    if change == "paused":
        model.pause()
    elif change == "signed_out":
        model.session = None
    elif change == "setting_off":
        model.apply_settings(DEST, False, auto_relogin=False)
    elif change == "busy":
        model.begin("sync")
    elif change == "unconfigured":
        model.configured = False
    else:
        model.pending = "sync"
    assert not model.session_check_due(LATER)


def test_a_failed_look_counts_too_so_it_does_not_repeat_every_tick():
    model = model_signed_in()
    model.begin(SESSION_JOB)
    assert model.finish_session_check(sr.UNREACHABLE, None, LATER) == []
    assert model.busy is None and not model.session_check_due(LATER)
    assert model.account()[0] == "Ada"  # a lost network is not a lost session


def test_a_session_replaced_in_the_background_leaves_no_trace_of_trouble():
    model = model_signed_in()
    model.auth_failed_at, model.login_prompted, model.session_expired = NOW, True, True
    model.begin(SESSION_JOB)
    assert model.finish_session_check(sr.EXPIRED, sr.RefreshResult(sr.REFRESHED), LATER) == []
    assert model.auth_failed_at is None and not model.login_prompted and not model.session_expired
    assert model.session_care.refreshed_at == LATER


@pytest.mark.parametrize("refresh", [sr.RefreshResult(sr.NEEDS_INTERACTION), None])
def test_a_session_that_is_gone_asks_for_sign_in_once(refresh):
    model = model_signed_in()
    model.begin(SESSION_JOB)
    notes = model.finish_session_check(sr.EXPIRED, refresh, LATER)
    assert [note.data for note in notes] == [{"action": "login"}]
    assert model.auth_failed_at == LATER and model.account()[0] is None
    model.begin(SESSION_JOB)
    assert model.finish_session_check(sr.EXPIRED, refresh, LATER) == []  # only once


def test_a_session_about_to_end_that_could_not_be_replaced_is_no_alarm():
    model = model_signed_in()
    model.begin(SESSION_JOB)
    assert model.finish_session_check(sr.ALIVE, sr.RefreshResult(sr.TIMED_OUT), LATER) == []
    assert model.account()[0] == "Ada" and not model.session_care.may_refresh(LATER)


def test_switching_it_back_on_may_try_again_at_once():
    model = model_signed_in()
    model.session_care.record(sr.RefreshResult(sr.TIMED_OUT), NOW)
    model.apply_settings(DEST, False, auto_relogin=False)
    assert not model.session_care.may_refresh(NOW)
    model.apply_settings(DEST, False, auto_relogin=True)
    assert model.session_care.may_refresh(NOW)


def test_homes_card_mentions_it_for_a_while():
    model = model_signed_in()
    model.last = RunOutcome(status="ok", finished_at=NOW)
    model.session_care.record(sr.RefreshResult(sr.REFRESHED), NOW)
    now = NOW + timedelta(minutes=5)
    assert main_window_model.home_state(model, now).detail.endswith("· Session refreshed automatically")
    later = NOW + main_window_model.SESSION_NOTE_FOR
    assert "refreshed" not in main_window_model.home_state(model, later).detail


# -- the setting ------------------------------------------------------------------------------------
def test_the_setting_is_on_by_default_and_saved(tmp_path):
    assert Settings(BASE_URL, DEST).auto_relogin is True
    save_settings(tmp_path, Settings(BASE_URL, DEST, auto_relogin=False))
    assert load_settings(tmp_path).auto_relogin is False
    data = json.loads((tmp_path / "settings.json").read_text())
    del data["auto_relogin"]  # settings of an older version
    assert Settings.from_dict(data).auto_relogin is True


def test_the_form_carries_the_setting():
    saved = Settings(BASE_URL, DEST, auto_relogin=False)
    values = settings_form.initial_values(saved, saved, False)
    assert values.auto_relogin is False
    assert settings_form.submit(values, saved).settings.auto_relogin is False
    values.auto_relogin = True
    assert settings_form.submit(values, saved).settings.auto_relogin is True


def test_the_load_model_takes_the_setting(config):
    config.ensure_data_dir()
    save_settings(config.data_dir, Settings(BASE_URL, DEST, auto_relogin=False))
    assert jobs.load_model(config, NOW, autostart=False).session_care.enabled is False


def test_the_row_is_only_where_the_app_does_it():
    rows = lambda **kw: [row.key for section in settings_form.settings_sections(**kw) for row in section.rows]
    assert "auto_relogin" in rows(auto_relogin=True)
    assert "auto_relogin" not in rows() and "auto_relogin" not in rows(appearance=True)  # Windows

