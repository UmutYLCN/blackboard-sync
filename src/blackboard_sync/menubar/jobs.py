"""Running the CLI for the menu bar app, and the app's small amount of saved state.

Syncs and sign-ins run as ``python -m blackboard_sync sync --json`` / ``login``
child processes, so the app reuses the exact CLI code path, its lock file and
its exit codes, and a crash in a run cannot take the menu bar app down. The
school and folder from the settings window are passed as flags on every run.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, IO

from blackboard_sync import courses, deadlines, gcal, relocate, runtime, signout
from blackboard_sync.config import Config
from blackboard_sync.errors import EXIT_ERROR, LoginRequired
from blackboard_sync.i18n import tr
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    AppModel,
    CourseChange,
    Notification,
    RecentSeen,
    RunOutcome,
    UpdateState,
    load_activity,
    load_saved_state,
    login_arguments,
    parse_sync_output,
    parse_iso,
    shorten,
    sync_arguments,
)
from blackboard_sync.session import write_private_json, load_session
from blackboard_sync.settings import Settings, load_settings
from blackboard_sync.state import State
from blackboard_sync.system import sync_root, try_lock

log = logging.getLogger("blackboard_sync.menubar")

# A first sync of a whole term can take a while; this only guards against a hang.
SYNC_TIMEOUT = 2 * 60 * 60
LOGIN_TIMEOUT = 15 * 60  # `login` itself gives up after 10 minutes

Runner = Callable[..., subprocess.CompletedProcess]


def cli_command(*args: str, python: str | None = None) -> list[str]:
    return runtime.cli_command(*args, python=python)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SyncStopped(Exception):
    """The student pressed Duraklat while the sync child process ran."""


_running_lock = threading.Lock()
_running: subprocess.Popen | None = None
_stop_asked = False


def run_cancellable(command, *, timeout: float | None = None, capture_output: bool = True,
                    **kwargs) -> subprocess.CompletedProcess:
    """``subprocess.run`` that ``stop_sync`` can end; raises ``SyncStopped`` when it did.

    Only one sync child runs at a time (the app has one job slot), so one handle is enough.
    """
    global _running, _stop_asked
    if capture_output:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    proc = subprocess.Popen(command, **kwargs)
    with _running_lock:
        _running, _stop_asked = proc, False
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
    finally:
        with _running_lock:
            stopped, _running, _stop_asked = _stop_asked, None, False
    if stopped:
        raise SyncStopped()
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


def stop_sync() -> bool:
    """End the running sync child (Duraklat); False when none runs.

    It is safe to interrupt: every finished course is already saved, and a half-written
    download is a hidden temp file the next sync removes.
    """
    global _stop_asked
    with _running_lock:
        if _running is None or _running.poll() is not None:
            return False
        _stop_asked = True
        _running.terminate()
        return True


def run_sync(
    job: str,
    settings: Settings,
    runner: Runner = run_cancellable,
    now: Callable[[], datetime] = utcnow,
    term_name: str = "",
    term_id: str = "",
) -> RunOutcome:
    try:
        args = sync_arguments(job, settings, term_name, term_id)
        proc = runner(
            cli_command(*args),
            capture_output=True,
            text=True,
            timeout=SYNC_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except SyncStopped:
        return RunOutcome(status="paused", finished_at=now())
    except subprocess.TimeoutExpired:
        return RunOutcome(status="error", message=tr("The sync took too long and was stopped."), finished_at=now())
    except OSError as exc:
        return RunOutcome(status="error", message=str(exc), finished_at=now())
    return parse_sync_output(proc.stdout, proc.returncode, proc.stderr, now())


def run_login(settings: Settings, runner: Runner = subprocess.run) -> tuple[bool, str]:
    """Run ``blackboard-sync login``; returns (signed in, message)."""
    try:
        proc = runner(
            cli_command(*login_arguments(settings)),
            capture_output=True,
            text=True,
            timeout=LOGIN_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return False, tr("timed out")
    except OSError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    lines = [line for line in (proc.stderr or proc.stdout or "").strip().splitlines() if line.strip()]
    return False, lines[-1] if lines else tr("exit status {code}").format(code=proc.returncode)


def run_sync_guarded(job: str, settings: Settings, term_name: str = "", term_id: str = "") -> RunOutcome:
    """``run_sync`` that turns any unexpected exception into a failed outcome.

    Worker threads must always report back, or the model stays busy forever.
    """
    try:
        return run_sync(job, settings, term_name=term_name, term_id=term_id)
    except Exception as exc:
        log.exception("Sync job failed")
        return RunOutcome(status="error", message=str(exc), finished_at=utcnow())


def run_calendar_guarded(config: Config, action: str = "sync", *, cancel=None, **options) -> gcal.CalendarStatus:
    """Calendar failures never change the Blackboard outcome; workers always report back."""
    try:
        gcal.perform(config, action, cancel=cancel, **options)
    except Exception as exc:
        from dataclasses import replace
        from blackboard_sync.errors import BlackboardSyncError, CalendarAuthExpired
        saved = gcal.status(config)
        return replace(saved, last_error=str(exc) if isinstance(exc, BlackboardSyncError)
                       else tr("Google Calendar operation failed."),
                       needs_reconnect=saved.needs_reconnect or isinstance(exc, CalendarAuthExpired))
    return gcal.status(config)


def calendar_after_sync(config: Config, model: AppModel, outcome: RunOutcome) -> bool:
    """Called on the UI thread; reserves a separate worker, never waits for Google."""
    model.calendar = gcal.status(config)
    if outcome.status != "ok" or model.paused or model.calendar_busy or not model.calendar.connected or model.calendar.needs_reconnect:
        return False
    model.calendar_busy = "sync"
    return True


def run_login_guarded(settings: Settings) -> tuple[bool, str]:
    """``run_login`` that turns any unexpected exception into a failed login."""
    try:
        return run_login(settings)
    except Exception as exc:
        log.exception("Login job failed")
        return False, str(exc)


def run_past_terms(settings: Settings, runner: Runner = subprocess.run) -> tuple[dict[str, str], RunOutcome]:
    """Discover on a worker, using the same session, executable and lock as sync.

    Returns each entry of the list (a term's name, told apart from a same-named
    term) mapped to the term's Blackboard id, which the download is started with.
    """
    try:
        proc = runner(cli_command("--base-url", settings.base_url, "past-terms", "--json"),
                      capture_output=True, text=True, timeout=LOGIN_TIMEOUT, stdin=subprocess.DEVNULL)
        if proc.returncode:
            return {}, parse_sync_output("", proc.returncode, proc.stderr, utcnow())
        data = json.loads(proc.stdout)
        options = data.get("options")
        if options is None:
            names = data["terms"]
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                raise ValueError(tr("Could not read the list of past terms."))
            options = [{"label": name, "id": ""} for name in names]
        terms = {option["label"]: option["id"] for option in options}
        if len(terms) != len(options) or not all(isinstance(k, str) and k and isinstance(v, str)
                                                 for k, v in terms.items()):
            raise ValueError(tr("Could not read the list of past terms."))
        return terms, RunOutcome(status="ok")
    except Exception as exc:
        return {}, RunOutcome(status="error", message=tr("Could not load past terms: {error}").format(error=exc))


def refresh_hidden_folders(config: Config, model: AppModel) -> None:
    """Which folders hold the files of the courses unticked in Dersler (hidden from Son indirilenler)."""
    try:
        model.hidden_folders = courses.load_hidden_folders(config)
    except OSError as exc:
        log.warning("Could not read the course choices: %s", exc)


def synced_file_count(config: Config, dest: Path) -> int:
    """How many downloaded files the chosen folder ``dest`` holds: whether a folder change needs asking."""
    return relocate.count_synced_files(config.state_file, dest)


def run_move_guarded(config: Config, old: Path, new: Path) -> relocate.MoveResult:
    """Move the downloaded files from the chosen folder ``old`` to ``new``; never raises (a worker thread runs it)."""
    try:
        return relocate.move_destination(config.state_file, config.lock_file, old, new)
    except Exception as exc:
        log.exception("Moving the files failed")
        return relocate.MoveResult(status="error", message=str(exc))


def login_method(platform: str | None = None) -> str:
    """Where ``login`` will ask the student to sign in: a browser's name or ``INAPP``.

    Shown while waiting; "" if it cannot be told (the sign-in itself decides).
    """
    from blackboard_sync.login import login_method_label

    try:
        return login_method_label("auto", platform=platform)
    except Exception:  # never block a sign-in on this
        return ""


def menubar_state_file(config: Config) -> Path:
    return config.data_dir / "menubar.json"


def log_file(config: Config) -> Path:
    return config.data_dir / "menubar.log"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def saved_settings(config: Config) -> Settings | None:
    """What the settings window saved; None before the first save."""
    return load_settings(config.data_dir)


def effective_settings(config: Config) -> Settings:
    """The settings the app syncs with: the saved ones, else the defaults.

    Saved settings win over ``BBSYNC_*`` variables here, so a choice made in
    the window is not undone by an environment the app was started with.
    """
    return saved_settings(config) or Settings(base_url=config.base_url, dest=config.dest)


def load_last_run(config: Config) -> RunOutcome | None:
    data = _read_json(config.last_run_file)
    if not data or data.get("dry_run") or not data.get("status"):
        return None
    return RunOutcome.from_report(data)


def load_model(config: Config, now: datetime, autostart: bool) -> AppModel:
    """Restore the model from last-run.json (shared with the CLI) and menubar.json."""
    last = load_last_run(config)
    saved = _read_json(menubar_state_file(config))
    recent, login_prompted = load_saved_state(saved)
    settings = effective_settings(config)
    model = AppModel(
        dest=settings.dest,
        configured=saved_settings(config) is not None,
        now=now,
        last=last,
        recent=recent,
        login_prompted=login_prompted,
        autostart=autostart,
        check_updates=settings.check_updates,
        sync_interval_minutes=settings.sync_interval_minutes,
        updates=UpdateState.load((saved or {}).get("updates"), now),
        recent_seen=RecentSeen((saved or {}).get("recent_seen")),
    )
    if saved and not (last and last.status == "ok") and isinstance(saved.get("courses"), list):
        try:
            model.courses = [CourseChange(**item) for item in saved["courses"]]
        except (TypeError, ValueError):
            pass
    if saved and not (last and last.status == "ok"):
        model.auth_failed_at = model.auth_failed_at or parse_iso(saved.get("auth_failed_at"))
    if model.configured and relocate.root_migration_pending(config.state_file, settings.dest):
        # Files of a version before the University folder: move them in first, so the
        # folder and "Son indirilenler" find them before the next sync.
        model.pending, model.move_from = MOVE_JOB, settings.dest
    sent = (saved or {}).get("reminders")
    model.reminders_sent = sent if isinstance(sent, dict) else {}
    model.paused = bool((saved or {}).get("paused"))
    model.activity_log = load_activity((saved or {}).get("activity"))
    model.restore_pending((saved or {}).get("pending"))  # a move or download the last run never got to
    model.calendar = gcal.status(config)
    refresh_hidden_folders(config, model)
    refresh_session(config, model, settings)
    if saved is None and last is not None and last.status == "ok":
        # First start: show what the last terminal sync brought in.
        model.remember(last)
    return model


REMINDER_CHECK_EVERY = timedelta(minutes=5)
# More reminders than this at once (say after a day away) become one notification.
REMINDER_GROUP_FROM = 4


def check_reminders(config: Config, model: AppModel, now: datetime) -> list[Notification]:
    """Notifications for due dates 24 hours and 1 hour away; looks at most every few minutes.

    Reads the due dates the last sync stored. Courses unticked in Dersler are left out.
    The record of what was shown is kept in ``model.reminders_sent`` (saved with the model).
    """
    if not model.configured:
        return []
    if model.reminders_checked_at is not None and now - model.reminders_checked_at < REMINDER_CHECK_EVERY:
        return []
    model.reminders_checked_at = now
    try:
        state = State.load(config.state_file, backup=False)
        reminders, sent = deadlines.due_reminders(
            state, sync_root(model.dest), now, model.reminders_sent, courses.load_disabled(config))
    except OSError as exc:
        log.warning("could not look for due dates: %s", exc)
        return []
    model.reminders_sent = sent
    if len(reminders) >= REMINDER_GROUP_FROM:
        lines = [f"{r.course}: {r.title}" for r in reminders]
        return [Notification(tr("Upcoming deadlines"), "\n".join(lines), {})]
    notes = []
    for reminder in reminders:
        title, message = deadlines.reminder_text(reminder, now)
        notes.append(Notification(title, message, {"deadline": reminder.target}))
    return notes


def save_model(config: Config, model: AppModel) -> None:
    config.ensure_data_dir()
    write_private_json(menubar_state_file(config), model.saved_state())


def single_instance(config: Config) -> IO | None:
    """Hold a lock for the app's lifetime; None when another copy is running."""
    config.ensure_data_dir()
    fh = open(config.data_dir / "menubar.lock", "w")
    if not try_lock(fh):
        fh.close()
        return None
    return fh


# Started by a restart (a new language): wait for the quitting copy's lock.
RESTARTING = "--restarting"
RESTART_TIMEOUT = 30.0  # seconds; a copy still running after that keeps the app


def wait_for_instance(config: Config, timeout: float = RESTART_TIMEOUT,
                      sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.monotonic) -> IO | None:
    """``single_instance``, tried again while the copy that restarts us is still quitting."""
    deadline = clock() + timeout
    while True:
        lock = single_instance(config)
        if lock is not None or clock() >= deadline:
            return lock
        sleep(0.25)


def relaunch(config: Config, command: list[str] | None = None, popen: Callable[..., object] = subprocess.Popen,
             **options) -> None:
    """Start a new copy of the app that takes over once this one quits; raises OSError.

    ``command`` defaults to the menu bar app; ``options`` go to ``Popen`` (Windows
    passes its detached-process flags, macOS a new session).
    """
    config.ensure_data_dir()
    if not options:
        options = {"start_new_session": True}
    with open(log_file(config), "a") as out:
        popen([*(command or runtime.menubar_command()), RESTARTING], stdin=subprocess.DEVNULL, stdout=out,
              stderr=out, cwd=str(Path.home()), env=os.environ.copy(), **options)


def detach(config: Config, python: str | None = None) -> int:
    """Start the app in the background, detached from the terminal, and return."""
    config.ensure_data_dir()
    log = open(log_file(config), "a")
    try:
        subprocess.Popen(
            runtime.menubar_command(python),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            cwd=str(Path.home()),
            env=os.environ.copy(),
        )
    except OSError as exc:
        print(shorten(tr("Could not start the menu bar app: {error}").format(error=exc), 200), file=sys.stderr)
        return EXIT_ERROR
    finally:
        log.close()
    return 0


def refresh_session(config: Config, model: AppModel, settings: Settings) -> None:
    try:
        model.session = load_session(config.session_file, settings.base_url)
        model.session_expired = False
    except (LoginRequired, TypeError, AttributeError, KeyError):
        model.session = None
        model.session_expired = config.session_file.exists()


def logout(config: Config) -> list[str]:
    """Remove the session and all login browser data; downloaded content, settings
    and sync state are retained. Returns warnings for data that could not be removed."""
    return signout.sign_out(config)
