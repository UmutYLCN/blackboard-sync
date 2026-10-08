"""The first thing the Windows tray app does: a log file and visible failures.

The installed app is windowed, so it has no console to print to. Before the
tray app itself is imported, this opens ``windows-tray.log`` in the data folder
(``%APPDATA%\\blackboard-sync``), sends crashes of the interpreter there too
(faulthandler), and turns an unhandled error into a native message box that
names the log. Only the standard library and ``blackboard_sync.system`` are
imported here, so a missing module of the frozen build is caught as well.
"""

import faulthandler
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

from blackboard_sync.system import default_data_dir, make_private_dir

log = logging.getLogger(__name__)

LOG_NAME = "windows-tray.log"
# faulthandler writes through its own handle, which would block renaming the
# log on Windows, so interpreter crashes and stack dumps get a file of their own.
FAULT_LOG_NAME = "windows-tray-faults.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3  # windows-tray.log plus three older ones: 4 MB at most
# Hidden diagnostic: BBSYNC_STACK_DUMP=<seconds> writes the stack of every
# thread to the log every <seconds> (to see where a running app waits).
STACK_DUMP_ENV = "BBSYNC_STACK_DUMP"
ERROR_TITLE = "Blackboard Sync"
ERROR_TEXT = "Blackboard Sync beklenmeyen bir hata nedeniyle durdu."
ERROR_LOG_TEXT = "Ayrıntılar bu dosyada:\n{path}"

MB_ICONERROR = 0x10
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000

_fault_file = None  # kept open for faulthandler for the life of the process


def data_dir(env=None) -> Path:
    """The tray app's data folder, chosen the same way as ``Config.from_env``."""
    env = os.environ if env is None else env
    return Path(env.get("BBSYNC_DATA_DIR") or default_data_dir(env=env)).expanduser()


def log_path(env=None) -> Path:
    return data_dir(env) / LOG_NAME


def setup_logging(env=None) -> Path:
    """Log to ``windows-tray.log`` from now on; returns its path."""
    global _fault_file
    env = os.environ if env is None else env
    path = log_path(env)
    # The private folder is made here, before anything else creates it, so it
    # still gets its owner-only permissions.
    make_private_dir(path.parent)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
                                                   encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
    _fault_file = open(path.with_name(FAULT_LOG_NAME), "a", encoding="utf-8")
    faulthandler.enable(_fault_file, all_threads=True)
    threading.excepthook = _log_thread_error
    interval = _stack_dump_interval(env.get(STACK_DUMP_ENV))
    if interval:
        faulthandler.dump_traceback_later(interval, repeat=True, file=_fault_file)
    from blackboard_sync import __version__
    log.info("Starting Blackboard Sync %s (pid %d, frozen %s, args %s)", __version__, os.getpid(),
             bool(getattr(sys, "frozen", False)), sys.argv[1:])
    return path


def close_logging() -> None:
    """Release both log handles before uninstall deletes the data folder contents."""
    global _fault_file
    from blackboard_sync.uninstall import close_file_logs

    faulthandler.cancel_dump_traceback_later()
    faulthandler.disable()
    if _fault_file is not None:
        _fault_file.close()
        _fault_file = None
    close_file_logs()


def _stack_dump_interval(value):
    try:
        seconds = float(value or 0)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def _log_thread_error(args):
    name = args.thread.name if args.thread else "?"
    log.error("Thread %s failed", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def error_text(path, exc) -> str:
    # Without a log file the error itself is the only clue.
    detail = ERROR_LOG_TEXT.format(path=path) if path else f"{type(exc).__name__}: {exc}"
    return f"{ERROR_TEXT}\n\n{detail}"


def show_error(text) -> None:
    """A native message box; works without Tk, which may be what failed."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, ERROR_TITLE,
                                         MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST)
    except Exception:  # no GUI at all; the log is all there is
        pass


def run(argv=None) -> int:
    """Start the tray app with logging in place; report an unhandled error."""
    path = None
    try:
        path = setup_logging()
        from .app import main

        return main(argv)
    except Exception as exc:
        if path is not None:
            log.exception("Blackboard Sync stopped on an unhandled error")
        show_error(error_text(path, exc))
        return 1
