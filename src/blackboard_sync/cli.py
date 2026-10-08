"""Command-line entry point: ``blackboard-sync login | sync | check | uninstall``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
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
from blackboard_sync.sync import Syncer, choose_past_terms, run_lock, run_sync
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

    sync = sub.add_parser("sync", help="download everything new into the course folders")
    _add_selection_args(sync)
    sync.add_argument("--dest", type=Path, help="base folder (env BBSYNC_DEST, default Documents/University)")
    sync.add_argument("--json", action="store_true", help="print the run summary as JSON")
    sync.add_argument("--dry-run", action="store_true", help="show what would be fetched, write nothing")
    sync.add_argument(
        "--refetch-missing",
        action="store_true",
        help="download again files that were deleted locally (default: respect deletions)",
    )

    sync.add_argument("--refetch-selection", type=Path,
                      help="JSON array of output keys; limits --refetch-missing to these files")

    check = sub.add_parser("check", help="verify the session and list the courses that would sync")
    _add_selection_args(check)
    check.add_argument("--dest", type=Path, help=argparse.SUPPRESS)
    past = sub.add_parser("past-terms", help="indirilebilen eski dönemleri listele")
    past.add_argument("--json", action="store_true", help="JSON olarak yazdır")
    uninstall = sub.add_parser("uninstall", help="uygulamayı ve tüm uygulama verilerini kaldır")
    uninstall.add_argument("--delete-course-files", action="store_true",
                           help="kayıtlı ders dosyalarını da Çöp Sepeti’ne taşı (varsayılan: koru)")
    return parser


def _add_selection_args(p: argparse.ArgumentParser) -> None:
    selection = p.add_mutually_exclusive_group()
    selection.add_argument("--term", help='eski dönemi bir kez indir, ör. "2025-2026 - Spring"; otomatik güncellenmez')
    selection.add_argument("--all-terms", action="store_true", help="sync every term, including past ones")
    p.add_argument(
        "--course",
        action="append",
        metavar="CODE",
        help="only this course (code like CSE303 or course id); repeatable",
    )


def make_config(args: argparse.Namespace) -> Config:
    config = Config.from_env(data_dir=args.data_dir)
    if args.base_url:
        config.base_url = args.base_url.rstrip("/")
    if getattr(args, "dest", None):
        config.dest = args.dest.expanduser()
    return config


def open_client(config: Config) -> tuple[BlackboardClient, dict]:
    session_data = load_session(config.session_file, config.base_url)
    return BlackboardClient(config.base_url, http_session(session_data)), session_data


def cmd_login(args, config: Config) -> int:
    from blackboard_sync.login import login

    login(config, browser=args.browser, timeout=args.timeout)
    print("Next: run `blackboard-sync sync` to download your courses.")
    return EXIT_OK


def cmd_check(args, config: Config) -> int:
    client, session_data = open_client(config)
    me = client.me()
    print(f"Session OK: signed in as {me.get('userName') or me.get('id')}.")
    syncer = Syncer(client, config, State(config.state_file), dry_run=True)
    warnings: list[str] = []
    terms, courses = syncer.discover(
        me["id"], args.term, args.all_terms, args.course, warnings=warnings
    )
    print(f"Term(s): {', '.join(t.name for t in terms) or 'none found'}")
    for course in courses:
        print(f"  {config.root / course.rel_dir}")
    for warning in warnings:
        print(f"  ! {warning}")
    refresh_saved_cookies(config.session_file, session_data, client.http)
    return EXIT_OK


def cmd_sync(args, config: Config) -> int:
    report = SyncReport(dry_run=args.dry_run, dest=str(config.root), past_term=args.term or "")
    migrated = None
    try:
        config.ensure_data_dir()
        with run_lock(config.lock_file):
            if not args.dry_run:
                # Before anything is downloaded, so files an older version put
                # straight into the chosen folder are not fetched again.
                migrated = relocate.migrate_destination(config.state_file, config.dest)
            selected = None
            if args.refetch_selection is not None:
                if not args.refetch_missing:
                    raise BlackboardSyncError("--refetch-selection requires --refetch-missing")
                selected = json.loads(args.refetch_selection.read_text(encoding="utf-8"))
                if not isinstance(selected, list) or not all(isinstance(k, str) for k in selected):
                    raise BlackboardSyncError("Refetch selection must be a JSON array of output keys")
                selected = set(selected)
            client, session_data = open_client(config)
            try:
                report = run_sync(
                    config,
                    client,
                    term_name=args.term,
                    all_terms=args.all_terms,
                    course_filters=args.course,
                    dry_run=args.dry_run,
                    refetch_missing=args.refetch_missing,
                    refetch_keys=selected,
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
        report.status, report.message = "error", f"Network error talking to Blackboard: {exc}"
    except Exception as exc:  # last resort: the report and last-run.json must always be written
        logging.getLogger(__name__).exception("Unexpected error during sync")
        report.status, report.message = "error", f"Unexpected error: {type(exc).__name__}: {exc}"
    if not report.finished_at:
        report.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if migrated is not None:
        report.moved_into_root = migrated.moved
        report.left_outside_root = [rel for rel, _reason in migrated.kept]

    if not args.dry_run and report.status != "locked" and args.term is None:
        write_private_json(config.last_run_file, report.to_dict())
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    elif report.status == "ok":
        print(report.render_text())
    else:
        print(report.message, file=sys.stderr)
    return STATUS_EXIT[report.status]


def cmd_past_terms(args, config: Config) -> int:
    client, session_data = open_client(config)
    try:
        with run_lock(config.lock_file):
            me = client.me()
            warnings: list[str] = []
            terms, _courses = Syncer(client, config, State(config.state_file), dry_run=True).discover(
                me["id"], all_terms=True, warnings=warnings,
            )
            names = [term.name for term in choose_past_terms(terms, datetime.now(timezone.utc))]
    finally:
        refresh_saved_cookies(config.session_file, session_data, client.http)
    if args.json:
        print(json.dumps({"terms": names, "warnings": warnings}, ensure_ascii=False))
    else:
        print("\n".join(names) or "İndirilebilecek eski dönem yok.")
    return EXIT_OK


def cmd_uninstall(args, config: Config) -> int:
    from blackboard_sync.uninstall import uninstall

    warnings = uninstall(config, delete_course_files=args.delete_course_files)
    for warning in warnings:
        print(warning, file=sys.stderr)
    print("Blackboard Sync uygulama verileri kaldırıldı.")
    return EXIT_ERROR if warnings else EXIT_OK


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
    handlers = {"login": cmd_login, "sync": cmd_sync, "check": cmd_check,
                "past-terms": cmd_past_terms, "uninstall": cmd_uninstall}
    try:
        return handlers[args.command](args, config)
    except LoginRequired as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_LOGIN_REQUIRED
    except BlackboardSyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    except requests.RequestException as exc:
        print(f"Network error talking to Blackboard: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130
