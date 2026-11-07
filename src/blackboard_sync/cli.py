"""Command-line entry point: ``blackboard-sync login | refresh-session | sync | check | notebooklm | uninstall``."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests

from blackboard_sync import __version__, relocate
from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.errors import (
    EXIT_ERROR,
    EXIT_LOCKED,
    EXIT_LOGIN_REQUIRED,
    EXIT_OK,
    AlreadyRunning,
    BlackboardSyncError,
    LoginRequired,
)
from blackboard_sync import schools
from blackboard_sync.i18n import tr
from blackboard_sync.inapp import INAPP
from blackboard_sync.login import BROWSER_LABELS
from blackboard_sync.report import SyncReport
from blackboard_sync.session import (
    http_session,
    load_session,
    refresh_saved_cookies,
    write_private_json,
)
from blackboard_sync.state import State
from blackboard_sync.sync import Syncer, run_lock, run_sync
from blackboard_sync.system import is_windows

STATUS_EXIT = {
    "ok": EXIT_OK,
    "login_required": EXIT_LOGIN_REQUIRED,
    "locked": EXIT_LOCKED,
    "error": EXIT_ERROR,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blackboard-sync",
        description="Mirror your Blackboard Learn Ultra courses into local folders.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--base-url", help="Blackboard address (env BBSYNC_BASE_URL)")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="private folder for the session and sync state (env BBSYNC_DATA_DIR)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log every request")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="sign in through a browser or the app's window and save the session")
    login.add_argument(
        "--browser",
        choices=["auto", *BROWSER_LABELS, INAPP],
        default="auto",
        help="auto: a supported browser if installed, else the app's own window (inapp)",
    )
    login.add_argument("--timeout", type=float, default=600, help="seconds to wait (default 600)")

    refresh = sub.add_parser("refresh-session", help="sign in again with no window, if the school's single sign-on allows it")
    refresh.add_argument("--json", action="store_true", help="print how it ended as JSON")

    sync = sub.add_parser("sync", help="download everything new into the course folders")
    _add_selection_args(sync)
    sync.add_argument("--dest", type=Path, help="base folder (env BBSYNC_DEST, default Documents/University)")
    sync.add_argument("--json", action="store_true", help="print the run summary as JSON")
    sync.add_argument("--dry-run", action="store_true", help="show what would be fetched, write nothing")
    # Every sync restores missing files now; the flag stays accepted for old scripts.
    sync.add_argument("--refetch-missing", action="store_true", help=argparse.SUPPRESS)

    check = sub.add_parser("check", help="verify the session and list the courses that would sync")
    _add_selection_args(check)
    check.add_argument("--dest", type=Path, help=argparse.SUPPRESS)
    uninstall = sub.add_parser("uninstall", help="remove the app and all of its data")
    uninstall.add_argument("--delete-course-files", action="store_true",
                           help="also move the downloaded course files to the Trash (default: keep them)")
    calendar = sub.add_parser("calendar", help="manage the optional Google Calendar connection")
    commands = calendar.add_subparsers(dest="calendar_action", required=True)
    commands.add_parser("connect", help="authorize in the system browser")
    commands.add_parser("status", help="show connection status as JSON")
    calendar_sync = commands.add_parser("sync", help="send cached Blackboard deadlines to Google")
    calendar_sync.add_argument("--reminders", action="store_true", help="use Google calendar default reminders")
    disconnect = commands.add_parser("disconnect", help="revoke access and remove local Calendar data")
    disconnect.add_argument("--delete-calendar", action="store_true")
    notebooklm = sub.add_parser("notebooklm", help="add the synced course files to NotebookLM")
    commands = notebooklm.add_subparsers(dest="notebooklm_action", required=True)
    commands.add_parser("login", help="sign in to Google in a browser and save the session")
    notebooklm_sync = commands.add_parser("sync", help="add new course files; prints one JSON event per line")
    notebooklm_sync.add_argument("--dest", type=Path, help="the folder the course files were saved in")
    notebooklm_sync.add_argument("--auto", action="store_true", help="after a sync: only look at the courses with something new")
    commands.add_parser("status", help="show the connection and the last run as JSON")
    duplicates = commands.add_parser("duplicates", help="list sources that are in a notebook twice; deletes nothing")
    duplicates.add_argument("--json", action="store_true", help="print the list as JSON")
    remove = commands.add_parser("remove-duplicates",
                                 help="remove the newer copies this app added, after asking; the older copy stays")
    remove.add_argument("--yes", action="store_true", help="do not ask: for scripts, after reading the list")
    remove.add_argument("--source", action="append", metavar="ID", help="only this copy; repeatable")
    remove.add_argument("--json", action="store_true", help="print the outcome as JSON")
    commands.add_parser("disconnect", help="delete the stored Google session")
    return parser


def _add_selection_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--all-terms", action="store_true", help="sync every term, including past ones")
    p.add_argument(
        "--course",
        action="append",
        metavar="CODE",
        help="only this course (code like CSE303 or course id); repeatable",
    )


def make_config(args: argparse.Namespace) -> Config:
    config = Config.from_env(data_dir=args.data_dir)
    if args.base_url:
        config.base_url = schools.resolve(args.base_url) or args.base_url.rstrip("/")
    if getattr(args, "dest", None):
        config.dest = args.dest.expanduser()
    return config


def open_client(config: Config) -> tuple[BlackboardClient, dict]:
    session_data = load_session(config.session_file, config.base_url)
    return BlackboardClient(config.base_url, http_session(session_data)), session_data


def cmd_login(args, config: Config) -> int:
    from blackboard_sync.login import login

    login(config, browser=args.browser, timeout=args.timeout)
    print(tr("Next: run `blackboard-sync sync` to download your courses."))
    return EXIT_OK


def cmd_refresh_session(args, config: Config) -> int:
    from blackboard_sync import session_refresh

    # Pausing ends this process; the browser must not stay behind on the profile. That takes
    # this handler on macOS; on Windows nothing runs then (see ``system.end_with_this_process``).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    result = session_refresh.silent_sign_in(config)
    if args.json:
        print(json.dumps({"status": result.reason, "seconds": round(result.seconds, 1)}))
    elif result.ok:
        print(tr("Session refreshed automatically"))
    else:
        print(tr("Could not refresh the session without you: {reason}").format(reason=result.reason), file=sys.stderr)
    if result.ok:
        return EXIT_OK
    return EXIT_LOCKED if result.reason == session_refresh.LOCKED else EXIT_LOGIN_REQUIRED


def cmd_check(args, config: Config) -> int:
    client, session_data = open_client(config)
    me = client.me()
    print(tr("Session OK: signed in as {name}.").format(name=me.get("userName") or me.get("id")))
    # The recorded files decide the folders, as in a real sync; nothing is written.
    syncer = Syncer(client, config, State.load(config.state_file, backup=False), dry_run=True)
    warnings: list[str] = []
    terms, courses = syncer.discover(me["id"], args.all_terms, args.course, warnings=warnings)
    print(tr("Term(s): {terms}").format(terms=", ".join(t.name for t in terms) or tr("none found")))
    for course in courses:
        print(f"  {config.root / course.rel_dir}")
    for warning in warnings:
        print(f"  ! {warning}")
    refresh_saved_cookies(config.session_file, session_data, client.http)
    return EXIT_OK


@contextmanager
def _exit_on_sigterm():
    """End with ``SystemExit`` on SIGTERM, so ``finally`` blocks still run.

    Pausing a sync ends its process with SIGTERM on macOS. Without a handler
    Python stops at once and the files placed since the last save of
    state.json would be unknown to it; ``run_sync`` saves in its ``finally``.
    Ctrl+C (SIGINT) already raises ``KeyboardInterrupt``. On Windows the process
    is ended without running anything; the sync saves after every file there.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def cmd_sync(args, config: Config) -> int:
    report = SyncReport(dry_run=args.dry_run, dest=str(config.root))
    migrated = None
    try:
        config.ensure_data_dir()
        with _exit_on_sigterm(), run_lock(config.lock_file):
            if not args.dry_run:
                # Before anything is downloaded, so files an older version put
                # straight into the chosen folder are not fetched again.
                migrated = relocate.migrate_destination(config.state_file, config.dest)
            client, session_data = open_client(config)
            try:
                report = run_sync(
                    config,
                    client,
                    all_terms=args.all_terms,
                    course_filters=args.course,
                    dry_run=args.dry_run,
                    lock_held=True,
                    user_id=(session_data.get("user") or {}).get("id"),
                )
            finally:
                refresh_saved_cookies(config.session_file, session_data, client.http)
    except LoginRequired as exc:
        report.status, report.message = "login_required", str(exc)
    except AlreadyRunning as exc:
        report.status, report.message = "locked", str(exc)
    except BlackboardSyncError as exc:
        report.status, report.message = "error", str(exc)
    except requests.RequestException as exc:
        report.status, report.message = "error", tr("Network error talking to Blackboard: {error}").format(error=exc)
    except Exception as exc:  # last resort: the report and last-run.json must always be written
        logging.getLogger(__name__).exception("Unexpected error during sync")
        report.status, report.message = "error", tr("Unexpected error: {error}").format(
            error=f"{type(exc).__name__}: {exc}")
    if not report.finished_at:
        report.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if migrated is not None:
        report.moved_into_root = migrated.moved
        report.left_outside_root = [rel for rel, _reason in migrated.kept]

    if not args.dry_run and report.status != "locked":
        write_private_json(config.last_run_file, report.to_dict())
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    elif report.status == "ok":
        print(report.render_text())
    else:
        print(report.message, file=sys.stderr)
    return STATUS_EXIT[report.status]


def cmd_uninstall(args, config: Config) -> int:
    from blackboard_sync.uninstall import uninstall

    warnings = uninstall(config, delete_course_files=args.delete_course_files)
    for warning in warnings:
        print(warning, file=sys.stderr)
    print(tr("Blackboard Sync's app data was removed."))
    return EXIT_ERROR if warnings else EXIT_OK


def cmd_calendar(args, config: Config) -> int:
    from dataclasses import asdict
    from blackboard_sync import gcal

    if args.calendar_action == "status":
        print(json.dumps(asdict(gcal.status(config))))
    else:
        options = {}
        if args.calendar_action == "disconnect":
            options["delete_calendar"] = args.delete_calendar
        elif args.calendar_action == "sync":
            options["reminders"] = args.reminders
        gcal.perform(config, args.calendar_action, **options)
        print(json.dumps(asdict(gcal.status(config))))
    return EXIT_OK


def cmd_notebooklm(args, config: Config) -> int:
    from dataclasses import asdict
    from blackboard_sync.notebooklm import runner, signin, store

    def emit(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    if args.notebooklm_action == "login":
        outcome, message = signin.CONNECTED, ""
        try:
            signin.login(config, on_verify=lambda: emit({"event": "sign_in", "step": "verify"}))
        except BlackboardSyncError as exc:
            outcome, message = getattr(exc, "outcome", "error"), str(exc)
        emit({"event": "result", **asdict(store.status(config)), "outcome": outcome, "message": message})
        return EXIT_OK if outcome == signin.CONNECTED else EXIT_ERROR
    elif args.notebooklm_action == "sync":
        result = runner.run(config, auto=args.auto, events=emit)
        emit({"event": "result", **result.last_run()})
        return runner.EXIT_CODES[result.status]
    elif args.notebooklm_action in ("duplicates", "remove-duplicates"):
        return _notebooklm_duplicates(args, config)
    elif args.notebooklm_action == "disconnect":
        for path in store.disconnect(config):
            print(tr("Could not delete app data: {path}").format(path=path), file=sys.stderr)
    emit({"event": "result", **asdict(store.status(config))})
    return EXIT_OK


def _print_duplicates(report) -> None:
    from blackboard_sync.notebooklm import duplicates

    notes = {duplicates.IDENTICAL: tr("same content, this app added it: can be removed"),
             duplicates.CHANGED: tr("the file changed since the older copy: both stay"),
             duplicates.NOT_ADDED_BY_APP: tr("not added by this app: stays"),
             duplicates.UNVERIFIED: tr("cannot be compared: stays")}
    for course in report.courses:
        if course.duplicates:
            print(f"{course.course}:")
        for duplicate in course.duplicates:
            print(f"  {duplicate.name}")
            print(f"    {tr('older')}: {duplicate.older.created_at[:16]} ({duplicate.older.origin})")
            for copy in duplicate.newer:
                print(f"    {tr('newer')}: {copy.created_at[:16]} ({copy.origin}) - {notes[copy.verdict]}")
    print(tr("{groups} duplicated, {removable} can be removed.").format(
        groups=sum(len(course.duplicates) for course in report.courses),
        removable=sum(len(course.removable) for course in report.courses)))


def _confirmed(count: int) -> bool:
    """A script has no one to ask, so without ``--yes`` the answer there is no."""
    if not sys.stdin.isatty():
        return False
    answer = input(tr("Remove {n} newer copies from NotebookLM? [y/N] ").format(n=count))
    return answer.strip().lower() in ("y", "yes", "e", "evet")


def _notebooklm_duplicates(args, config: Config) -> int:
    from blackboard_sync.notebooklm import duplicates, runner

    report = duplicates.find(config)
    removing = args.notebooklm_action == "remove-duplicates"
    if report.status == "ok" and removing:
        offered = [copy.id for course in report.courses for copy, _older in course.removable]
        chosen = [id_ for id_ in offered if not args.source or id_ in args.source]
        if not args.json:
            _print_duplicates(report)
        if chosen and not (args.yes or _confirmed(len(chosen))):
            print(tr("Nothing was removed."), file=sys.stderr)
            return EXIT_ERROR
        if chosen:
            report = duplicates.remove(config, chosen)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False))
    elif report.status != "ok":
        print(report.message, file=sys.stderr)
    elif removing:
        print(tr("{n} removed, {failed} failed.").format(n=len(report.removed), failed=len(report.failed)))
    else:
        _print_duplicates(report)
    return runner.EXIT_CODES[report.status]


def _utf8_output() -> None:
    """Windows: write UTF-8 even when the output is a pipe (Turkish names, JSON)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    if is_windows():
        _utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        # urllib3 logs full URLs at DEBUG only; keep it quiet by default.
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    config = make_config(args)
    handlers = {"login": cmd_login, "refresh-session": cmd_refresh_session, "sync": cmd_sync, "check": cmd_check,
                "uninstall": cmd_uninstall, "calendar": cmd_calendar,
                "notebooklm": cmd_notebooklm}
    try:
        return handlers[args.command](args, config)
    except LoginRequired as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_LOGIN_REQUIRED
    except BlackboardSyncError as exc:
        print(tr("Error: {error}").format(error=exc), file=sys.stderr)
        return exc.exit_code
    except requests.RequestException as exc:
        print(tr("Network error talking to Blackboard: {error}").format(error=exc), file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130
