"""The Windows app's NotebookLM card and silent re-sign-in, with fakes (no Windows needed)."""

import json
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from blackboard_sync import deadlines, session_refresh as sr, signout, system
from blackboard_sync.config import Config
from blackboard_sync.login import WINDOWS_LOCK_FILE, profile_in_use
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar import settings_form as form
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    NOTEBOOKLM_CONNECT,
    NOTEBOOKLM_DUPLICATES,
    NOTEBOOKLM_SYNC,
    SESSION_JOB,
    AppModel,
    RunOutcome,
)
from blackboard_sync.menubar.settings_form import WindowStatus
from blackboard_sync.notebooklm import signin, store
from blackboard_sync.notebooklm.store import NotebookLMStatus
from blackboard_sync.settings import Settings
from blackboard_sync.windows import app as module, webui_state
from blackboard_sync.windows.app import TrayApp, cli_popen, cli_run, console_command

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
CONNECTED = NotebookLMStatus(connected=True)
ROOT = Path(__file__).resolve().parents[1]


class Worker:
    """Runs what would be a thread at once, so a test reads top to bottom."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A tray app with its work done in line and its questions answered by ``app.answers``."""
    monkeypatch.setattr(module.threading, "Thread", Worker)
    monkeypatch.setattr(jobs, "utcnow", lambda: NOW)
    tray = TrayApp.__new__(TrayApp)
    tray.config = Config(data_dir=tmp_path, dest=tmp_path / "files")
    tray.settings = Settings("https://bb.example", tmp_path / "files")
    tray.login_after_job = False
    tray.uninstalling = False
    tray.closed = False
    tray.window = None
    tray.root = SimpleNamespace(destroy=lambda: None, after=lambda *a: None)
    tray.icon = SimpleNamespace(stop=lambda: None)
    tray.model = AppModel(tray.settings.dest, NOW, configured=True)
    tray.model.session = {"user": {"name": "Umut"}}
    tray.save = lambda: None
    tray.refresh = lambda: None
    tray.post = lambda callback, *args: callback(*args)
    tray.notes = []
    tray.post_notifications = tray.notes.extend
    tray.notify = tray.notes.append
    tray.messages = []
    tray.answers = {}
    tray.web = SimpleNamespace(
        ask_destructive=lambda title, message, button: tray.answers.get("confirm", True),
        ask_duplicates=lambda title, text, remove: tray.asked_list(title, text, remove),
        ask_yes_no=lambda title, message: True,
        show_message=lambda kind, title, message: tray.messages.append((kind, title, message)))
    tray.lists = []

    def asked_list(title, text, remove):
        tray.lists.append((title, text, remove))
        return tray.answers.get("remove", False)

    tray.asked_list = asked_list
    return tray


@pytest.fixture
def config(tmp_path):
    return Config(base_url="https://blackboard.example.edu", dest=tmp_path / "files", data_dir=tmp_path / "data")


# -- the console twin -----------------------------------------------------------------------------
def test_children_run_as_the_console_twin_with_utf8_and_no_window(monkeypatch, tmp_path):
    """A windowed exe has no standard streams, and the code page would garble Turkish file names."""
    monkeypatch.setattr(module.runtime, "is_frozen", lambda: True)
    gui = tmp_path / module.GUI_EXE
    assert console_command([str(gui), "notebooklm", "sync"])[0] == str(tmp_path / module.CLI_EXE)
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda command, **options: calls.append((command, options)))
    monkeypatch.setattr(subprocess, "run", lambda command, **options: calls.append((command, options)))
    cli_popen([str(gui), "a"], text=True)
    cli_run([str(gui), "b"], text=True)
    for command, options in calls:
        assert command[0] == str(tmp_path / module.CLI_EXE)
        assert options["encoding"] == "utf-8" and options["errors"] == "replace" and options["text"]


def test_a_turkish_file_name_reaches_the_card_through_the_child_output(tmp_path):
    """The whole way through a real child process, as the Windows app starts it."""
    config = Config(data_dir=tmp_path, dest=tmp_path / "files")
    event = json.dumps({"event": "progress", "file": "Hafta 1/Öğrenci.pdf", "done": 1, "total": 2, "course": "Ç"},
                       ensure_ascii=False)
    script = tmp_path / "child.py"
    script.write_text("import sys\nsys.stdout.reconfigure(encoding='utf-8')\n"
                      f"print({event!r})\nprint('{{\"event\": \"result\", \"outcome\": \"\"}}')\n", encoding="utf-8")
    events = []

    def child(command, **options):
        return cli_popen([sys.executable, str(script)], **options)

    jobs.run_notebooklm(config, "sync", Settings("https://bb.example", tmp_path), on_event=events.append, popen=child)
    assert main.notebooklm_progress(events[0]).text.endswith("Öğrenci.pdf")


def test_the_shared_jobs_take_the_windows_runner(tmp_path, monkeypatch):
    calls = []

    def runner(command, **_options):
        calls.append(command)
        if "refresh-session" in command:
            return subprocess.CompletedProcess(command, 0, stdout='{"status": "refreshed", "seconds": 3}', stderr="")
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 3, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    settings = Settings("https://bb.example", tmp_path)
    outcome, refresh = jobs.run_sync_refreshing("sync", settings, may_refresh=True, runner=runner)
    assert [("refresh-session" in command) for command in calls] == [False, True, False]
    assert refresh.ok and outcome.status != "login_required"

    calls.clear()
    listed = lambda command, **_o: calls.append(command) or subprocess.CompletedProcess(command, 0, '{"status": "ok"}', "")
    assert jobs.run_notebooklm_duplicates(runner=listed) == {"status": "ok"} and len(calls) == 1


# -- NotebookLM beside the sync -------------------------------------------------------------------
@pytest.fixture
def runs(monkeypatch):
    """What ``run_notebooklm_guarded`` was asked to do; each run ends with ``runs.status``."""
    done = SimpleNamespace(calls=[], status=CONNECTED)

    def run(config, action, settings, auto=False, on_event=lambda event: None, popen=None):
        done.calls.append((action, auto, popen))
        on_event({"event": "progress", "file": "a.pdf", "done": 1, "total": 2, "finished": 1, "course": "CSE"})
        return done.status

    monkeypatch.setattr(jobs, "run_notebooklm_guarded", run)
    return done


def test_every_finished_sync_adds_to_notebooklm_on_the_console_twin(app, runs, monkeypatch):
    monkeypatch.setattr(jobs, "calendar_after_sync", lambda *a: False)
    monkeypatch.setattr(jobs, "refresh_hidden_folders", lambda *a: None)
    app.start_next = lambda: None
    app.model.notebooklm = CONNECTED
    app.model.begin("sync")
    app.job_done("sync", RunOutcome(status="ok", finished_at=NOW))
    assert runs.calls == [(NOTEBOOKLM_SYNC, True, cli_popen)]
    assert app.model.notebooklm_busy is None


@pytest.mark.parametrize("change", ["off", "not_connected", "failed", "paused"])
def test_no_automatic_run_when_it_should_not_run(app, runs, monkeypatch, change):
    monkeypatch.setattr(jobs, "calendar_after_sync", lambda *a: False)
    monkeypatch.setattr(jobs, "refresh_hidden_folders", lambda *a: None)
    app.start_next = lambda: None
    app.model.notebooklm = NotebookLMStatus() if change == "not_connected" else CONNECTED
    app.settings = replace(app.settings, notebooklm_auto=change != "off")
    app.model.begin("sync")
    if change == "paused":
        app.model.paused = True
    app.job_done("sync", RunOutcome(status="error" if change == "failed" else "ok", finished_at=NOW))
    assert runs.calls == []


def test_connecting_starts_the_first_full_run(app, runs):
    app.dispatch("notebooklm_connect")
    assert [call[:2] for call in runs.calls] == [(NOTEBOOKLM_CONNECT, False), (NOTEBOOKLM_SYNC, False)]


def test_a_sync_during_a_run_looks_again_afterwards(app, runs):
    app.model.notebooklm = CONNECTED
    app.model.begin_notebooklm(NOTEBOOKLM_SYNC)
    assert not app.model.wants_notebooklm(RunOutcome(status="ok"), True)
    app.notebooklm_done(NOTEBOOKLM_SYNC, CONNECTED)
    assert [call[:2] for call in runs.calls] == [(NOTEBOOKLM_SYNC, True)]


def test_progress_reaches_the_card(app):
    app.model.notebooklm = CONNECTED
    app.model.begin_notebooklm(NOTEBOOKLM_SYNC)
    app.notebooklm_event({"event": "progress", "file": "W/a.pdf", "done": 1, "total": 4, "finished": 1, "course": "CSE"})
    card = main.notebooklm_card(app.model, NOW)
    assert card.running and card.progress == 0.25 and card.counts == "CSE" and "a.pdf" in card.detail


def test_pause_stops_only_an_upload_run_and_quit_stops_any(app, monkeypatch):
    stopped = []
    monkeypatch.setattr(jobs.notebooklm_child, "stop", lambda: stopped.append(True))
    app.model.begin_notebooklm(NOTEBOOKLM_CONNECT)
    app.dispatch("pause")
    assert stopped == []
    app.dispatch("pause")
    app.model.notebooklm_busy = NOTEBOOKLM_SYNC
    app.dispatch("pause")
    assert stopped == [True]
    app.dispatch("quit")
    assert stopped == [True, True] and app.closed


def test_uninstall_waits_for_notebooklm(app, monkeypatch):
    app.model.begin_notebooklm(NOTEBOOKLM_SYNC)
    monkeypatch.setattr(module.package, "is_packaged", lambda: False)
    app.dispatch("uninstall")
    assert app.messages and app.messages[0][0] == "info" and not app.uninstalling


def test_open_goes_to_notebooklm(app, monkeypatch):
    opened = []
    monkeypatch.setattr(module.webbrowser, "open", opened.append)
    app.dispatch("notebooklm_open")
    assert opened == [store.APP_URL]


# -- disconnect and duplicates --------------------------------------------------------------------
def test_disconnect_asks_and_deletes_the_session(app, tmp_path):
    session = store.session_file(app.config)
    session.parent.mkdir(parents=True)
    session.write_text("{}")
    app.model.notebooklm = store.status(app.config)
    app.answers["confirm"] = False
    app.dispatch("notebooklm_disconnect")
    assert session.exists()
    app.answers["confirm"] = True
    app.dispatch("notebooklm_disconnect")
    assert not session.exists() and not app.model.notebooklm.connected


def test_disconnect_waits_while_a_run_uses_the_session(app):
    session = store.session_file(app.config)
    session.parent.mkdir(parents=True)
    session.write_text("{}")
    app.model.begin_notebooklm(NOTEBOOKLM_SYNC)
    app.dispatch("notebooklm_disconnect")
    assert session.exists()


def test_a_locked_session_file_is_said_on_the_card(app, monkeypatch):
    def locked(_config):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(store, "disconnect", locked)
    app.dispatch("notebooklm_disconnect")
    assert app.model.notebooklm.error and app.model.notebooklm.message == signout.LOCKED_WARNING


REPORT = {"status": "ok", "duplicates": 1, "courses": [{"course": "CSE301", "duplicates": [{
    "name": "a.pdf", "older": {"id": "s1", "created_at": "2026-10-01T00:00:00"},
    "newer": [{"id": "s2", "created_at": "2026-10-09T00:00:00", "verdict": "identical", "removable": True},
              {"id": "s3", "created_at": "2026-10-10T00:00:00", "verdict": "changed", "removable": False}]}]}]}


@pytest.fixture
def duplicates(monkeypatch, app):
    done = SimpleNamespace(calls=[], reports=[REPORT, {"status": "ok", "removed": ["s2"], "failed": []}])

    def run(source_ids=None, runner=None):
        done.calls.append((source_ids, runner))
        return done.reports.pop(0)

    monkeypatch.setattr(jobs, "run_notebooklm_duplicates", run)
    app.show_window = lambda section=None: None
    return done


def test_only_what_was_shown_as_removable_goes_and_only_after_both_questions(app, duplicates):
    app.answers["remove"] = True
    app.dispatch("notebooklm_duplicates")
    assert duplicates.calls == [(None, cli_run), (["s2"], cli_run)]
    assert "a.pdf" in app.lists[0][1] and "1" in app.lists[0][2]
    assert app.messages[-1][1] == "Duplicates removed." and "1 removed, 0 failed." in app.messages[-1][2]
    assert app.model.notebooklm_busy is None


@pytest.mark.parametrize("answers", [{"remove": False}, {"remove": True, "confirm": False}])
def test_nothing_is_removed_without_both_answers(app, duplicates, answers):
    app.answers.update(answers)
    app.dispatch("notebooklm_duplicates")
    assert [call[0] for call in duplicates.calls] == [None]


def test_a_failed_look_says_why_and_frees_the_slot(app, duplicates):
    duplicates.reports[:] = [{"status": "login_required", "message": "Sign in again"}]
    app.dispatch("notebooklm_duplicates")
    assert app.messages[-1][2] == "Sign in again" and app.model.notebooklm_busy is None and app.lists == []


def test_the_list_opens_the_window_if_it_was_closed_meanwhile(app, duplicates):
    shown = []
    app.show_window = shown.append
    app.dispatch("notebooklm_duplicates")
    assert shown == [main.GENERAL]


def test_nothing_removable_offers_no_button(app, duplicates):
    report = json.loads(json.dumps(REPORT))
    report["courses"][0]["duplicates"][0]["newer"][0]["removable"] = False
    duplicates.reports[:] = [report]
    app.dispatch("notebooklm_duplicates")
    assert app.lists[0][2] == ""


# -- the look at the session between syncs ----------------------------------------------------------
def checks(monkeypatch, *results):
    calls, queue = [], list(results)

    def run(config, settings, may_refresh, runner=None):
        calls.append((may_refresh, runner))
        return queue.pop(0)

    monkeypatch.setattr(jobs, "run_session_check", run)
    return calls


def test_the_look_runs_every_25_minutes_and_not_before(app, monkeypatch):
    calls = checks(monkeypatch, jobs.SessionCheck(sr.ALIVE), jobs.SessionCheck(sr.ALIVE))
    app.start_next = lambda: None
    app.start_session_check()
    assert calls == []
    monkeypatch.setattr(jobs, "utcnow", lambda: NOW + timedelta(minutes=25))
    app.start_session_check()
    assert calls == [(True, module.cli_runner)] and app.model.busy is None
    app.start_session_check()
    assert len(calls) == 1


def test_a_failed_refresh_is_tried_again_only_after_10_minutes(app, monkeypatch):
    """A lost session ends the looks; the syncs that follow try, once per ten minutes."""
    failed = jobs.SessionCheck(sr.EXPIRED, sr.RefreshResult(sr.NEEDS_INTERACTION))
    checks(monkeypatch, failed)
    app.start_next = lambda: None
    monkeypatch.setattr(jobs, "utcnow", lambda: NOW + timedelta(minutes=25))
    app.start_session_check()
    tried = []

    def sync(job, settings, may_refresh, wanted, runner):
        tried.append((may_refresh, runner))
        return RunOutcome(status="login_required", finished_at=NOW), None

    monkeypatch.setattr(jobs, "run_sync_refreshing", sync)
    app.job_done = lambda *a: app.model.finish_sync(RunOutcome(status="ok", finished_at=NOW), NOW)
    for minutes in (34, 36):
        monkeypatch.setattr(jobs, "utcnow", lambda minutes=minutes: NOW + timedelta(minutes=minutes))
        app.start_job("sync")
    assert tried == [(False, module.cli_runner), (True, module.cli_runner)]


def test_the_setting_off_means_no_look_at_all(app, monkeypatch):
    calls = checks(monkeypatch, jobs.SessionCheck(sr.ALIVE))
    monkeypatch.setattr(jobs, "utcnow", lambda: NOW + timedelta(hours=2))
    app.model.session_care.enabled = False
    app.start_session_check()
    assert calls == []


def test_a_lost_session_falls_back_to_the_sign_in_notification_once(app, monkeypatch):
    app.start_next = lambda: None
    failed = jobs.SessionCheck(sr.EXPIRED, sr.RefreshResult(sr.NEEDS_INTERACTION))
    app.session_done(failed)
    app.session_done(failed)
    assert len(app.notes) == 1 and app.model.auth_failed_at == NOW


def test_a_refreshed_session_says_so_on_the_card_and_clears_the_trouble(app, monkeypatch):
    app.start_next = lambda: None
    app.model.auth_failed_at = NOW
    app.model.last = RunOutcome(status="ok", finished_at=NOW)
    app.session_done(jobs.SessionCheck(sr.EXPIRED, sr.RefreshResult(sr.REFRESHED, 3.0)))
    assert app.notes == [] and app.model.auth_failed_at is None
    assert main.T_SESSION_REFRESHED in main.home_state(app.model, NOW + timedelta(minutes=5)).detail
    assert main.T_SESSION_REFRESHED not in main.home_state(app.model, NOW + timedelta(hours=3)).detail


def test_a_sync_that_refreshed_counts_the_same(app, monkeypatch):
    monkeypatch.setattr(jobs, "calendar_after_sync", lambda *a: False)
    monkeypatch.setattr(jobs, "refresh_hidden_folders", lambda *a: None)
    app.start_next = lambda: None
    app.model.begin("sync")
    app.job_done("sync", RunOutcome(status="ok", finished_at=NOW), sr.RefreshResult(sr.REFRESHED, 3.0))
    assert app.model.session_care.refreshed_at == NOW


def test_a_failed_refresh_during_a_sync_starts_the_ten_minutes(app, monkeypatch):
    monkeypatch.setattr(jobs, "calendar_after_sync", lambda *a: False)
    monkeypatch.setattr(jobs, "refresh_hidden_folders", lambda *a: None)
    app.start_next = lambda: None
    app.model.begin("sync")
    app.job_done("sync", RunOutcome(status="login_required", finished_at=NOW), sr.RefreshResult(sr.TIMED_OUT))
    assert app.model.session_care.failed_at == NOW
    assert not app.model.session_care.may_refresh(NOW + timedelta(minutes=9))


def test_signing_in_during_the_look_waits_for_it(app, monkeypatch):
    started = []
    original = app.start_job
    app.start_job = lambda job: started.append(job) if job == "login" and app.model.busy is None else original(job)
    app.start_next = lambda: None
    assert app.model.begin(SESSION_JOB)
    app.dispatch("login")
    assert app.login_after_job and started == []
    app.session_done(jobs.SessionCheck(sr.ALIVE))
    assert started == ["login"] and not app.login_after_job


def test_quit_and_settings_do_not_wait_for_the_look(app, monkeypatch):
    monkeypatch.setattr(jobs.notebooklm_child, "stop", lambda: False)
    assert app.model.begin(SESSION_JOB)
    assert not app.job_holds_app()
    app.dispatch("quit")
    assert app.closed and app.messages == []


def test_a_running_sync_still_holds_quit(app):
    assert app.model.begin("sync")
    assert app.job_holds_app()


def test_saving_the_setting_reaches_the_model(app, monkeypatch):
    monkeypatch.setattr(module.autostart, "set_enabled", lambda enabled: None)
    monkeypatch.setattr(module, "save_settings", lambda *a: None)
    app.start_next = lambda: None
    values = form.initial_values(None, app.settings, False)
    assert values.auto_relogin and values.notebooklm_auto  # both on by default
    assert app.settings_submitted(replace(values, auto_relogin=False, notebooklm_auto=False), False) is None
    assert app.model.session_care.enabled is False and app.settings.notebooklm_auto is False


def test_settings_may_be_saved_during_the_look(app, monkeypatch):
    monkeypatch.setattr(module.autostart, "set_enabled", lambda enabled: None)
    monkeypatch.setattr(module, "save_settings", lambda *a: None)
    app.start_next = lambda: None
    assert app.model.begin(SESSION_JOB)
    assert app.settings_submitted(form.initial_values(None, app.settings, False), False) is None


# -- the page ---------------------------------------------------------------------------------------
FORM = WindowStatus(account="", account_warning=False, account_title="", account_action="logout", account_enabled=True,
                    version="1", update_title="", update_action="check_updates", update_enabled=True,
                    notebooklm_connected=True)


def status(card):
    return main.MainStatus(first_run=False, account=main.AccountCard("U", "Umut", ""), sync_title="Sync now",
                           sync_enabled=True, recent=(), form=FORM,
                           home=main.HomeState(main.STATE_SYNCED, "Up to date", ""), pause_enabled=True, notebooklm=card)


def state(card):
    return webui_state.window_state(status(card), main.OVERVIEW, main.OVERVIEW, (), deadlines.DeadlinePage(),
                                    date(2026, 11, 6))


def model_card(paused=False, busy=None, notebooklm=None, progress=None):
    model = AppModel(Path("/d"), NOW, configured=True)
    model.notebooklm, model.paused, model.notebooklm_busy = notebooklm or NotebookLMStatus(), paused, busy
    model.notebooklm_progress = progress
    return main.notebooklm_card(model, NOW)


@pytest.mark.parametrize("card, kind, button, enabled, opens", [
    (model_card(), "off", "notebooklm_connect", True, False),
    (model_card(busy=NOTEBOOKLM_CONNECT), "running", "notebooklm_connect", False, False),
    (model_card(notebooklm=CONNECTED), "idle", "notebooklm_sync", True, True),
    (model_card(notebooklm=CONNECTED, paused=True), "idle", "notebooklm_sync", False, True),
    (model_card(notebooklm=CONNECTED, busy=NOTEBOOKLM_SYNC), "running", "notebooklm_sync", False, True),
    (model_card(notebooklm=CONNECTED, busy=NOTEBOOKLM_DUPLICATES), "running", "notebooklm_sync", False, True),
    (model_card(notebooklm=replace(CONNECTED, needs_login=True, message="Sign in")), "attention", "notebooklm_connect",
     True, False),
    (model_card(notebooklm=replace(CONNECTED, error=True, message="Down")), "attention", "notebooklm_sync", True, True),
])
def test_the_card_follows_every_state_and_clicks_stay_within_it(card, kind, button, enabled, opens):
    drawn = state(card)
    data = drawn["home"]["notebooklm"]
    json.dumps(data)
    assert data["kind"] == kind and data["button"]["id"] == button and data["button"]["enabled"] is enabled
    assert bool(data["open"]) is opens and data["warning"] is (kind == "attention")
    allowed = webui_state.ids(drawn)["notebooklm"]
    assert (button in allowed) is enabled and ("notebooklm_open" in allowed) is opens


def test_a_run_shows_how_far_it_has_come_or_that_there_is_no_telling():
    going = model_card(notebooklm=CONNECTED, busy=NOTEBOOKLM_SYNC,
                       progress=main.NotebookLMProgress("Adding", "CSE", 0.5))
    assert state(going)["home"]["notebooklm"]["progress"] == 0.5
    assert state(model_card(notebooklm=CONNECTED, busy=NOTEBOOKLM_SYNC))["home"]["notebooklm"]["progress"] is None


def test_settings_have_the_notebooklm_section_and_the_re_sign_in_switch():
    drawn = state(model_card())
    sections = {section["key"]: section for section in drawn["settings"]["sections"]}
    keys = [row["key"] for row in sections[form.SECTION_NOTEBOOKLM]["rows"]]
    assert keys == ["notebooklm_auto", "notebooklm_duplicates", "notebooklm_disconnect"]
    assert "auto_relogin" in [row["key"] for row in sections[form.SECTION_SYNC]["rows"]]
    assert {"auto_relogin", "notebooklm_auto"} <= set(drawn["settings"]["values"])
    assert {"notebooklm_duplicates", "notebooklm_disconnect"} <= webui_state.ids(drawn)["button"]


def test_notebooklm_buttons_wait_for_a_connection_and_a_free_slot():
    for changes in ({"notebooklm_connected": False}, {"notebooklm_busy": True}):
        current = status(model_card())
        current = replace(current, form=replace(FORM, **changes))
        drawn = webui_state.window_state(current, main.OVERVIEW, main.OVERVIEW, (), deadlines.DeadlinePage(),
                                         date(2026, 11, 6))
        assert not {"notebooklm_duplicates", "notebooklm_disconnect"} & webui_state.ids(drawn)["button"]


def test_the_page_acts_only_on_the_buttons_of_the_card():
    from tests.test_web_window import make_window

    window, _host, events = make_window()
    window.update_status(status(model_card()))
    window.run_action("notebooklm_sync")
    window.run_action("notebooklm_open")
    assert events == []  # not connected: neither button is on the card
    window.run_action("notebooklm_connect")
    assert ("action", "notebooklm_connect") in events
    window.update_status(status(model_card(notebooklm=CONNECTED)))
    window.run_action("notebooklm_open")
    assert ("action", "notebooklm_open") in events
    window.run_setting("notebooklm_duplicates", "")
    window.run_setting("notebooklm_disconnect", "")
    assert ("action", "notebooklm_duplicates") in events and ("action", "notebooklm_disconnect") in events


def test_a_question_that_cannot_be_undone_defaults_to_no_and_the_list_scrolls():
    from tests.test_web_window import make_window

    window, host, _events = make_window()
    window.show()
    answers = []

    def ask(call):
        thread = threading.Thread(target=lambda: answers.append(call()))
        thread.start()
        while window.dialog is None:
            pass
        return window.dialog, thread

    dialog, thread = ask(lambda: host.ask_destructive("Sure?", "Text", "Remove"))
    assert [button["default"] for button in dialog["buttons"] if button.get("default")] == [True]
    assert dialog["buttons"][0]["id"] == "cancel" and "danger" in dialog["buttons"][1]["style"]
    host.answer(dialog["id"], "confirm", False)
    thread.join(5)
    while window.dialog is not None:
        pass
    dialog, thread = ask(lambda: host.ask_duplicates("Two", "a.pdf", "Remove 1 copy…"))
    assert dialog["list"] == "a.pdf"
    host.answer(dialog["id"], "cancel", False)
    thread.join(5)
    assert answers == [True, False]


def test_the_preview_draws_every_card_state():
    source = (ROOT / "scripts" / "webui-preview.py").read_text(encoding="utf-8")
    for name in ("notebooklm-off", "notebooklm-signing-in", "notebooklm-running", "notebooklm-idle",
                 "notebooklm-attention", "duplicates-dialog"):
        assert f'"{name}"' in source


# -- what the core does differently on Windows ------------------------------------------------------
def test_a_browser_on_the_profile_is_seen_through_its_lock_file(tmp_path):
    (tmp_path / WINDOWS_LOCK_FILE).write_text("")

    def refused(_path, _mode):
        raise PermissionError(13, "used by another process")

    assert profile_in_use(tmp_path, platform="win32", opener=refused)
    assert not profile_in_use(tmp_path, platform="win32")  # nothing holds it: left by nothing that runs
    assert not profile_in_use(tmp_path / "missing", platform="win32")


@pytest.fixture
def windows_rig(config, tmp_path, monkeypatch):
    from blackboard_sync import login as login_mod
    from blackboard_sync.session import save_session

    monkeypatch.setattr(sr, "POLL_SECONDS", 0)
    config.ensure_data_dir()
    config.profile_dir.mkdir()
    save_session(config.session_file, "https://blackboard.example.edu",
                 [{"name": "s", "value": "v", "domain": "blackboard.example.edu", "path": "/"}], {"id": "u"})
    monkeypatch.setattr(sr, "profile_in_use", lambda *a, **k: False)
    return SimpleNamespace(config=config, tmp_path=tmp_path, login=login_mod)


@pytest.mark.parametrize("exe", ["opera.exe"])
def test_a_launcher_is_never_started_in_the_background(windows_rig, monkeypatch, exe):
    monkeypatch.setattr(sr, "discover_browser", lambda *a, **k: windows_rig.tmp_path / exe)
    started = []
    result = sr.silent_sign_in(windows_rig.config, spawn=lambda *a, **k: started.append(a), platform="win32")
    assert result.reason == sr.BROWSER_MISSING and started == []


def test_the_silent_browser_has_no_window_and_ends_with_its_process(windows_rig, monkeypatch, tmp_path):
    """No console, no focus, and on the student's real browser, as on the Mac."""
    from blackboard_sync.login import DEVTOOLS_PORT_FILE

    exe = tmp_path / "chrome.exe"
    monkeypatch.setattr(sr, "discover_browser", lambda *a, **k: exe)
    tied, started = [], []
    monkeypatch.setattr(sr, "end_with_this_process", lambda process, platform: tied.append((process, platform)))

    process = SimpleNamespace(wait=lambda timeout=None: 0, terminate=lambda: None, kill=lambda: None)

    def spawn(argv, **options):
        started.append((argv, options))
        (windows_rig.config.profile_dir / DEVTOOLS_PORT_FILE).write_text("40000\n/x\n")
        return process

    class Browser:
        contexts = []

        def close(self):
            pass

    result = sr.silent_sign_in(windows_rig.config, spawn=spawn, connect=lambda url: Browser(), platform="win32")
    argv, options = started[0]
    assert argv[0] == str(exe) and "--headless=new" in argv
    assert options["creationflags"] == system.CREATE_NO_WINDOW and "start_new_session" not in options
    assert tied == [(process, "win32")] and result.reason == sr.BROWSER_FAILED


def test_tying_a_process_does_nothing_elsewhere_and_never_fails_the_sign_in():
    system.end_with_this_process(object(), "darwin")
    system.end_with_this_process(object(), "win32")  # no handle to tie


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job objects")
def test_a_child_really_ends_with_the_process_on_windows(tmp_path):
    """Pause ends ``refresh-session`` at once; the browser it started must not stay behind."""
    pid_file = tmp_path / "pid"
    source = Path(__file__).resolve().parents[1] / "src"
    parent = (
        "import subprocess, sys, time\n"
        f"sys.path.insert(0, {str(source)!r})\n"
        "from blackboard_sync.system import end_with_this_process\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "end_with_this_process(child)\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(120)\n"
    )
    process = subprocess.Popen([sys.executable, "-c", parent])
    try:
        for _ in range(200):
            if pid_file.exists() and pid_file.read_text():
                break
            threading.Event().wait(0.1)
        pid = int(pid_file.read_text())
        process.terminate()
        process.wait(30)
        for _ in range(100):
            alive = str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
            if not alive:
                break
            threading.Event().wait(0.1)
        assert not alive
    finally:
        process.kill()


def test_the_google_sign_in_starts_the_browser_as_the_blackboard_one(config, monkeypatch, tmp_path):
    """The real exe with a free port and a private profile, in the app's private data folder."""
    from tests.test_notebooklm import SIGNED_IN, FakeBrowser

    exe = tmp_path / "msedge.exe"
    monkeypatch.setattr(signin, "find_browser", lambda *a, **k: exe)
    monkeypatch.setattr(signin, "wait_for_port", lambda port: None)
    monkeypatch.setattr(signin, "free_port", lambda: 12345)
    private, started = [], []
    monkeypatch.setattr(signin, "make_private_dir",
                        lambda path, platform=None: private.append((path, platform)) or path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(signin, "start_browser", lambda argv, label, platform, run, spawn: started.append((argv, label)))
    signin.login(config, connect=lambda url: FakeBrowser(SIGNED_IN), check=lambda c: None, platform="win32")
    argv, label = started[0]
    assert argv[0] == str(exe) and label == "Microsoft Edge"
    assert f"--user-data-dir={store.profile_dir(config)}" in argv and "--remote-debugging-port=12345" in argv
    assert (config.notebooklm_dir, "win32") in private and (store.profile_dir(config), "win32") in private
    assert store.session_file(config).exists()
    assert store.session_file(config).is_relative_to(config.data_dir)


# -- the package ------------------------------------------------------------------------------------
def test_the_windows_build_ships_the_library_and_checks_it():
    spec = (ROOT / "packaging" / "blackboard_sync_windows.spec").read_text(encoding="utf-8")
    assert 'copy_metadata("notebooklm-py")' in spec and "NOTEBOOKLM_IMPORTS" in spec
    assert '"blackboard_sync.notebooklm.gateway"' in spec
    assert "--check-notebooklm" in (ROOT / "scripts" / "smoke-test-msix.ps1").read_text(encoding="utf-8")
    assert "--check-notebooklm" in (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_the_library_is_installed_on_windows():
    wanted = "sys_platform == 'darwin' or sys_platform == 'win32'"
    assert f"notebooklm-py==0.8.5; {wanted}" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
    for name in ("notebooklm-py", "anyio", "click", "filelock", "h11", "httpcore", "httpx", "markdown-it-py", "mdurl",
                 "rich"):
        assert any(line.startswith(f"{name}==") and line.endswith(wanted) for line in lock), name
