"""Running the CLI for the menu bar app, and the app's small amount of saved state.

Syncs and sign-ins run as ``python -m blackboard_sync sync --json`` / ``login``
child processes, so the app reuses the exact CLI code path, its lock file and
its exit codes, and a crash in a run cannot take the menu bar app down. The
school and folder from the settings window are passed as flags on every run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, IO

from blackboard_sync import runtime
from blackboard_sync.config import Config
from blackboard_sync.errors import EXIT_ERROR, LoginRequired
from blackboard_sync.menubar.model import (
    AppModel,
    CourseChange,
    RunOutcome,
    UpdateState,
    load_saved_state,
    login_arguments,
    parse_sync_output,
    parse_iso,
    shorten,
    sync_arguments,
)
from blackboard_sync.session import write_private_json, load_session
from blackboard_sync.settings import Settings, load_settings
from blackboard_sync.system import try_lock

# A first sync of a whole term can take a while; this only guards against a hang.
SYNC_TIMEOUT = 2 * 60 * 60
LOGIN_TIMEOUT = 15 * 60  # `login` itself gives up after 10 minutes

Runner = Callable[..., subprocess.CompletedProcess]


def cli_command(*args: str, python: str | None = None) -> list[str]:
    return runtime.cli_command(*args, python=python)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_sync(
    job: str,
    settings: Settings,
    runner: Runner = subprocess.run,
    now: Callable[[], datetime] = utcnow,
) -> RunOutcome:
    try:
        proc = runner(
            cli_command(*sync_arguments(job, settings)),
            capture_output=True,
            text=True,
            timeout=SYNC_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return RunOutcome(status="error", message="Senkron çok uzun sürdü ve durduruldu.", finished_at=now())
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
        return False, "zaman aşımı"
    except OSError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    lines = [line for line in (proc.stderr or proc.stdout or "").strip().splitlines() if line.strip()]
    return False, lines[-1] if lines else f"exit status {proc.returncode}"


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
        updates=UpdateState.load((saved or {}).get("updates"), now),
    )
    if saved and not (last and last.status == "ok") and isinstance(saved.get("courses"), list):
        try:
            model.courses = [CourseChange(**item) for item in saved["courses"]]
        except (TypeError, ValueError):
            pass
    if saved and not (last and last.status == "ok"):
        model.auth_failed_at = model.auth_failed_at or parse_iso(saved.get("auth_failed_at"))
    refresh_session(config, model, settings)
    if saved is None and last is not None and last.status == "ok":
        # First start: show what the last terminal sync brought in.
        model.remember(last)
    return model


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
        print(shorten(f"Could not start the menu bar app: {exc}", 200), file=sys.stderr)
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


def logout(config: Config) -> None:
    """Remove only credentials; downloaded content and sync state are retained."""
    config.session_file.unlink(missing_ok=True)
