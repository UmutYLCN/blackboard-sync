"""Windows-only entry point; Tk (or ``loop.EventLoop``) owns state, tray and workers enqueue events.

The main window is the WebView2 page (``web_window``); without WebView2, or with
``BLACKBOARD_SYNC_UI=tk``, it is the Tk ``MainWindow``.
"""

import argparse
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import replace
from pathlib import Path

from blackboard_sync import (announcements, courses, deadlines, relocate, runtime, session_refresh, signout, updater,
                             uninstall)
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.i18n import ntr, tr
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.menubar.main_window_model import (
    GENERAL,
    duplicates_text,
    duplicates_title,
    main_status,
    notebooklm_progress,
    removable_ids,
    shows_window_at_launch,
)
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    NOTEBOOKLM_CONNECT,
    NOTEBOOKLM_DUPLICATES,
    NOTEBOOKLM_SYNC,
    SESSION_JOB,
    UPDATE_ACTIONS,
    RunOutcome,
    open_target,
)
from blackboard_sync.notebooklm import store as notebooklm_store
from blackboard_sync.settings import SettingsError, save_settings
from blackboard_sync.system import sync_root
from . import activation, autostart, notifications, package
from .presentation import icon_image, render_menu

log = logging.getLogger(__name__)

# The two executables of the installed app (packaging/blackboard_sync_windows.spec).
GUI_EXE = "Blackboard Sync.exe"
CLI_EXE = "blackboard-sync-cli.exe"
# Shown once, when the main window first closes: where the app went.
TRAY_HINT_TITLE = tr("Blackboard Sync is running in the background")
TRAY_HINT = (tr("Right-click the Blackboard Sync icon next to the clock for the menu. "
             "If you don't see it, click the ^ arrow that shows hidden icons."))
TRAY_HINT_SHOWN = "tray-hint-shown"
# Workers wake Tk with this virtual event, so the UI never polls its queue.
WAKE_EVENT = "<<bbsync>>"
# The request files (toast click, second start) come from other processes and
# cannot wake Tk, so they are checked on a slow timer; this is also the safety
# net should a wake-up ever be lost.
REQUEST_CHECK_MS = 2000
# Which main window to show: "web" (default, the WebView2 page) or "tk" (the older Tk window).
UI_ENV = "BLACKBOARD_SYNC_UI"
# The same failing check is logged with its traceback at most this often.
ERROR_LOG_INTERVAL = 60.0


class LogThrottle:
    """Lets the same key through at most once per ``interval`` seconds."""

    def __init__(self, interval=ERROR_LOG_INTERVAL, clock=time.monotonic):
        self.interval, self.clock = interval, clock
        self.last = {}

    def allow(self, key):
        now = self.clock()
        if key in self.last and now - self.last[key] < self.interval:
            return False
        self.last[key] = now
        return True


def app_command():
    """The command line that starts this tray app (a restart in a new language)."""
    executable = Path(sys.executable)
    if runtime.is_frozen():
        return [str(executable)]
    if executable.name.lower() == "python.exe":
        executable = executable.with_name("pythonw.exe")
    return [str(executable), "-m", "blackboard_sync.windows"]


def console_command(command):
    # pythonw can discard standard streams even with redirected handles. Run
    # the console interpreter hidden so the CLI always returns its JSON report.
    command = list(command)
    executable = Path(command[0])
    if executable.name.lower() == "pythonw.exe":
        command[0] = str(executable.with_name("python.exe"))
    elif runtime.is_frozen() and executable.name.lower() == GUI_EXE.lower():
        # Same reason in the installed app: its windowed exe has no console, so
        # the CLI runs as the console twin installed next to it.
        command[0] = str(executable.with_name(CLI_EXE))
    return command


def cli_options():
    # The CLI emits UTF-8 even when the Windows ANSI code page is different.
    return {"encoding": "utf-8", "errors": "replace", "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def cli_runner(command, **kwargs):
    """A CLI job in the app's one job slot: Pause can end it."""
    return jobs.run_cancellable(console_command(command), **kwargs, **cli_options())


def cli_run(command, **kwargs):
    """A CLI job beside the job slot; ``subprocess.run`` for ``jobs``."""
    return subprocess.run(console_command(command), **kwargs, **cli_options())


def cli_popen(command, **kwargs):
    """The same for a child that reports as it goes; ``subprocess.Popen`` for ``jobs``."""
    return subprocess.Popen(console_command(command), **kwargs, **cli_options())


class TrayApp:
    web = None  # the WebView2 window's ``WebHost`` when the main window is the page (``web_window``)

    def __init__(self, config, root, show_window=False):
        import pystray

        self.config, self.root = config, root
        self.background = not show_window  # started at login or by a silent update
        self.settings = jobs.effective_settings(config)
        self.model = jobs.load_model(config, jobs.utcnow(), autostart.is_installed())
        self.events = queue.Queue()
        self.poll_errors = LogThrottle()
        self.window = None  # the main window, built when first shown
        self.login_after_job = False  # a new school's sign-in waits for the file move
        self.closed = False
        self.uninstalling = False
        self.drawn = None
        self.drawn_icon = None
        self.icon = pystray.Icon("Blackboard Sync", icon_image(self.model.icon()), "Blackboard Sync")
        self.refresh()

    def run(self):
        self.icon.run_detached()
        log.info("Tray icon started (configured %s)", self.model.configured)
        self.root.bind(WAKE_EVENT, self.drain)
        self.root.after(REQUEST_CHECK_MS, self.poll)
        self.root.after(1000, self.tick)
        if shows_window_at_launch(self.background, self.model.configured):
            self.root.after(200, self.show_window)
        self.root.mainloop()

    def post(self, callback, *args):
        """Queue ``callback(*args)`` for the Tk thread and wake it (any thread)."""
        self.events.put((callback, args))
        try:
            self.root.event_generate(WAKE_EVENT, when="tail")
        except Exception:
            # Tk is gone (quitting), so the event would never run anyway.
            log.debug("Could not wake Tk", exc_info=True)

    def drain(self, _event=None):
        try:
            while not self.closed:
                callback, args = self.events.get_nowait()
                try:
                    callback(*args)
                except Exception:
                    log.exception("UI event failed")
        except queue.Empty:
            pass

    def poll(self):
        if self.uninstalling:
            self.root.after(REQUEST_CHECK_MS, self.poll)
            return
        self.drain()
        if not self.closed:
            try:
                update, window = activation.take_requests(self.config)
                if update:
                    self.notification_clicked({"action": "update"})
                if window:
                    log.info("Started again; showing the main window")
                    self.show_window()
            except OSError as exc:
                # A persistent failure (say a denied folder) must not flood the log.
                if self.poll_errors.allow((type(exc), exc.errno, exc.filename)):
                    log.exception("Could not read toast activation")
            self.root.after(REQUEST_CHECK_MS, self.poll)

    def tick(self):
        if self.uninstalling:
            self.root.after(30000, self.tick)
            return
        self.start_next()
        self.start_session_check()
        if updater.enabled() and self.model.update_due(jobs.utcnow()):
            self.start_update_check(manual=False)
        self.remind()
        self.refresh()
        self.root.after(30000, self.tick)

    def remind(self):
        """Toasts for due dates 24 hours and 1 hour away."""
        notes = jobs.check_reminders(self.config, self.model, jobs.utcnow())
        self.post_notifications(notes)
        if notes:
            self.save()

    def start_next(self):
        """A job a folder change asked for goes first, then the scheduled sync."""
        jobs.refresh_session(self.config, self.model, self.settings)  # a queued sync waits for it
        job = self.model.pending_job()
        if job is not None:
            self.start_job(job)
        elif self.model.due(jobs.utcnow()):
            self.start_job("sync")

    def start_job(self, job):
        old, new = self.model.move_from, self.model.dest
        if job == MOVE_JOB and old is None:
            return
        if job == "login" and self.model.busy == SESSION_JOB:  # over in seconds, and it may use the browser profile
            self.login_after_job = True
            return
        if self.model.updates.busy == "download" or not self.model.begin(job):
            return
        if job == "login":
            self.model.login_method = jobs.login_method()
        self.refresh()
        settings, config = self.settings, self.config
        may_refresh = self.model.session_care.may_refresh(jobs.utcnow())
        def worker():
            refresh = None
            try:
                if job == "login":
                    result = jobs.run_login(settings, runner=cli_runner)
                elif job == MOVE_JOB:
                    result = jobs.run_move_guarded(config, old, new)
                else:
                    result, refresh = jobs.run_sync_refreshing(job, settings, may_refresh,
                                                               wanted=lambda: not self.model.paused, runner=cli_runner)
            except Exception as exc:
                log.exception("CLI job failed")
                result = ((False, str(exc)) if job == "login"
                          else relocate.MoveResult(status="error", message=str(exc)) if job == MOVE_JOB
                          else RunOutcome(status="error", message=str(exc)))
            self.post(self.job_done, job, result, refresh)
        threading.Thread(target=worker, daemon=True).start()

    def start_session_check(self):
        """Between syncs: keep the session alive, and replace it if it is gone or about to go."""
        now = jobs.utcnow()
        if not self.model.session_check_due(now) or not self.model.begin(SESSION_JOB):
            return
        settings, may_refresh = self.settings, self.model.session_care.may_refresh(now)
        def worker():
            self.post(self.session_done, jobs.run_session_check(self.config, settings, may_refresh, runner=cli_runner))
        threading.Thread(target=worker, daemon=True).start()

    def session_done(self, check):
        if check.status != session_refresh.ALIVE:
            log.info("Keep-alive: %s", check.status)
        self.log_refresh(check.refresh)
        self.post_notifications(self.model.finish_session_check(check.status, check.refresh, jobs.utcnow()))
        self.save()
        if self.login_after_job:
            self.login_after_job = False
            self.start_job("login")
        else:
            self.start_next()
        self.refresh()

    def log_refresh(self, refresh):
        if refresh is None:
            return
        if refresh.ok:
            log.info("Session refreshed automatically (%.1f s)", refresh.seconds)
        else:
            log.warning("Automatic re-sign-in failed: %s", refresh.reason)

    def start_calendar(self, action="sync", **options):
        """Connect, sync or disconnect Google Calendar on a worker; pressing Connect again cancels it."""
        if self.model.calendar_busy:
            if action == "connect" and self.model.calendar_busy == "connect":
                self.calendar_cancel.set()
            return
        if action == "sync" and self.model.paused:
            return
        self.model.calendar_busy = action
        cancel = threading.Event()
        self.calendar_cancel = cancel
        self.refresh()
        def worker():
            self.post(self.calendar_done, jobs.run_calendar_guarded(self.config, action, cancel=cancel, **options))
        threading.Thread(target=worker, daemon=True).start()

    def disconnect_calendar(self):
        """Asked in the WebView2 page (the Tk window has no Calendar section)."""
        choice = self.web.ask_calendar_disconnect() if self.web is not None else None
        if choice is not None:
            self.start_calendar("disconnect", delete_calendar=choice)

    def theme_chosen(self, theme):
        """Settings → Theme, saved at once (not with the form); before the first Save it waits for it."""
        from dataclasses import replace

        self.settings = replace(self.settings, theme=theme)
        if jobs.saved_settings(self.config) is None:
            return
        try:
            save_settings(self.config.data_dir, self.settings)
        except OSError:
            log.exception("Could not save the theme")

    def calendar_done(self, status):
        self.model.calendar_busy = None
        self.model.calendar = status
        self.save()
        self.refresh()

    def start_notebooklm(self, action=NOTEBOOKLM_SYNC, auto=False):
        """Run beside the Blackboard jobs; whatever happens shows only on Home's card."""
        if not self.model.begin_notebooklm(action):
            return
        log.info("NotebookLM %s started", action)
        self.refresh()
        config, settings = self.config, self.settings
        def worker():
            status = jobs.run_notebooklm_guarded(config, action, settings, auto, popen=cli_popen,
                                                 on_event=lambda event: self.post(self.notebooklm_event, event))
            self.post(self.notebooklm_done, action, status)
        threading.Thread(target=worker, daemon=True).start()

    def notebooklm_event(self, event):
        self.model.notebooklm_progress = notebooklm_progress(event)
        self.refresh()

    def notebooklm_done(self, action, status):
        result = status.outcome or ("login required" if status.needs_login else "error" if status.error else "ok")
        log.info("NotebookLM %s finished: %s %s", action, result, status.message if status.error else "")
        if self.model.finish_notebooklm(status):
            self.start_notebooklm(auto=action != NOTEBOOKLM_CONNECT)
        self.refresh()

    def find_notebooklm_duplicates(self, source_ids=None):
        """List the duplicates, or remove the copies just confirmed; both take the NotebookLM slot."""
        if not self.model.begin_notebooklm(NOTEBOOKLM_DUPLICATES):
            return
        self.refresh()
        def worker():
            report = jobs.run_notebooklm_duplicates(source_ids, runner=cli_run)
            self.post(self.notebooklm_duplicates_done, report, source_ids is not None)
        threading.Thread(target=worker, daemon=True).start()

    def notebooklm_duplicates_done(self, report, removed):
        self.notebooklm_done(NOTEBOOKLM_DUPLICATES, notebooklm_store.status(self.config))
        if report.get("status") != "ok":
            log.warning("NotebookLM duplicates: %s %s", report.get("status"), report.get("message"))
            self.show_message("warning", tr("Could not look through NotebookLM."), report.get("message") or "")
        elif removed:
            self.show_message("info", tr("Duplicates removed."), tr("{n} removed, {failed} failed.").format(
                n=len(report.get("removed", ())), failed=len(report.get("failed", ()))))
        else:
            ids = removable_ids(report)
            if self.window is None or not self.window_open:
                self.show_window(GENERAL)  # the look takes a while: it may have been closed since
            if self.ask_duplicates(report, len(ids)) and self.ask_remove_duplicates(len(ids)):
                self.find_notebooklm_duplicates(ids)

    def ask_duplicates(self, report, removable):
        """The list; True when the student asks to remove the copies that can go (they confirm once more)."""
        remove = ntr("Remove {n} copy…", "Remove {n} copies…", removable).format(n=removable) if removable else ""
        title, text = duplicates_title(report), duplicates_text(report)
        if self.web is not None:
            return self.web.ask_duplicates(title, text, remove)
        from .main_window import ask_notebooklm_duplicates

        return ask_notebooklm_duplicates(self.dialog_parent(), title, text, remove)

    def ask_remove_duplicates(self, removable):
        """Deleting cannot be undone from here, so it takes this second, plain question."""
        return self.ask_destructive(
            ntr("Remove {n} copy from NotebookLM?", "Remove {n} copies from NotebookLM?",
                removable).format(n=removable),
            tr("Only newer copies this app added are removed, and only with the same content as "
               "the older copy. The older copy stays. This cannot be undone."), tr("Remove"))

    def disconnect_notebooklm(self):
        """Confirmed first: signing in again takes the student through Google's sign-in."""
        if self.model.notebooklm_busy is not None or not self.ask_destructive(
                tr("Disconnect NotebookLM?"),
                tr("The Google session is deleted from this computer. Files already in NotebookLM "
                   "stay there, and new ones are no longer added."), tr("Disconnect")):
            return
        try:
            problems = notebooklm_store.disconnect(self.config)
        except OSError as exc:  # Windows refuses to delete a file that something still holds open
            problems = [str(exc)]
        self.model.notebooklm = notebooklm_store.status(self.config)
        if problems:
            log.warning("Could not delete the NotebookLM session data: %s", problems)
            self.model.notebooklm = replace(self.model.notebooklm, error=True, message=signout.LOCKED_WARNING)

    def job_done(self, job, result, refresh=None):
        if job == "login":
            self.model.finish_login(*result, jobs.utcnow())
        elif job == MOVE_JOB:
            log.info("Move finished: %s, %d moved, %d kept", result.status, result.moved, len(result.kept))
            self.post_notifications(
                self.model.finish_move(result.status, result.moved, len(result.kept), result.message))
        else:
            self.log_refresh(refresh)
            if refresh is not None:
                self.model.record_refresh(refresh, jobs.utcnow())
            for note in self.model.finish_sync(result, jobs.utcnow()):
                threading.Thread(target=self.notify, args=(note,), daemon=True).start()
            if jobs.calendar_after_sync(self.config, self.model, result):
                cancel = threading.Event()
                self.calendar_cancel = cancel
                def worker():
                    status = jobs.run_calendar_guarded(self.config, cancel=cancel)
                    self.post(self.calendar_done, status)
                threading.Thread(target=worker, daemon=True).start()
            if self.model.wants_notebooklm(result, self.settings.notebooklm_auto):
                self.start_notebooklm(auto=True)
            jobs.refresh_hidden_folders(self.config, self.model)  # the sync may have found new courses
        self.save()
        if self.login_after_job:
            self.login_after_job = False
            self.start_job("login")
        elif job != MOVE_JOB:  # a move that found the folders locked waits for the timer
            self.start_next()
        self.refresh()

    def post_notifications(self, notes):
        for note in notes:
            threading.Thread(target=self.notify, args=(note,), daemon=True).start()

    def start_update_check(self, manual=True):
        if not updater.enabled():
            return
        if not self.model.updates.begin("check"):
            return
        self.refresh()
        threading.Thread(target=self.update_check_worker, args=(manual,), daemon=True).start()

    def update_check_worker(self, manual):
        try:
            result = updater.check()
        except Exception:
            log.exception("Update check failed")
            result = updater.CheckResult("unknown")
        self.post(self.update_checked, result, manual)

    def update_checked(self, result, manual):
        self.post_notifications(self.model.updates.finish_check(result, jobs.utcnow(), manual))
        self.save()
        self.refresh()

    def start_update(self):
        if not updater.enabled():
            return
        release = self.model.updates.available
        if release is None:
            self.start_update_check()
            return
        if self.model.updates.busy is not None:
            return
        if not runtime.is_frozen():
            webbrowser.open(release.page_url)
            return
        if self.model.busy is not None:
            self.model.note = tr("Wait for the running job to finish before updating.")
            self.refresh()
            return
        if not self.model.updates.begin("download"):
            return
        self.refresh()
        threading.Thread(target=self.update_install_worker, args=(release,), daemon=True).start()

    def update_install_worker(self, release):
        error = ""
        try:
            updater.install_windows_update(release)
        except updater.UpdateError as exc:
            error = str(exc)
        except Exception:
            log.exception("Update installation failed")
            error = tr("Could not install the update; try again later.")
        self.post(self.update_installed, error)

    def update_installed(self, error):
        self.post_notifications(self.model.updates.finish_download(error))
        self.save()
        if error:
            self.refresh()
        else:
            # The installer has started; release the app and its lifetime lock.
            self.dispatch("quit")

    def notification_clicked(self, data):
        if data.get("action") in UPDATE_ACTIONS:
            self.dispatch(data["action"])

    def toggle_pause(self):
        """Duraklat / Devam et: pausing also ends a sync that is running right now."""
        if self.model.paused:
            self.model.resume(jobs.utcnow())
            self.save()
            self.start_next()
            return
        self.model.pause()
        if self.model.calendar_busy == "sync":
            self.calendar_cancel.set()
        if self.model.notebooklm_busy == NOTEBOOKLM_SYNC:
            jobs.notebooklm_child.stop()
        if self.model.busy == "sync":
            jobs.stop_sync()  # the worker reports "paused" and frees the job slot
        self.save()

    def notify(self, note):
        try:
            notifications.show(note)
        except (OSError, subprocess.SubprocessError):
            log.exception("Windows notification failed")

    def window_status(self):
        """What the main window draws; Home's greeting line counts the saved due dates."""
        return main_status(self.model, jobs.utcnow(), deadlines.load_calendar(self.config, self.settings.dest))

    def refresh(self):
        import pystray

        jobs.refresh_session(self.config, self.model, self.settings)
        try:
            self.model.autostart = autostart.is_installed()
        except OSError:
            log.exception("Could not read login item")
        state = self.model.icon()
        # Session expiry can be detected before the first scheduled sync.
        if self.model.session_expired:
            from blackboard_sync.menubar.model import Icon
            state = Icon.EXPIRED
        if state != self.drawn_icon:
            self.icon.icon = icon_image(state)
            self.drawn_icon = state
        if self.window_open:
            self.window.update_status(self.window_status())
        menu = self.model.menu(jobs.utcnow())
        if package.is_packaged():
            menu.entries = [entry for entry in menu.entries if entry.action not in UPDATE_ACTIONS]
        if menu != self.drawn:
            self.icon.menu = render_menu(menu.entries,
                                        lambda action, value: self.post(self.dispatch, action, value),
                                        pystray.Menu, pystray.MenuItem)
            self.drawn = menu

    def dispatch(self, action, value=""):
        if self.uninstalling:
            return
        if action in ("sync", "login"):
            self.start_job(action)
        elif action == "check_updates":
            self.start_update_check()
        elif action == "update":
            self.start_update()
        elif action == "uninstall":
            self.start_uninstall()
            return
        elif action == "pause":
            self.toggle_pause()
        elif action in ("settings", "calendar_settings"):
            self.show_window(GENERAL)
        elif action == "calendar_connect":
            self.start_calendar("connect")
        elif action == "calendar_sync":
            self.start_calendar()
        elif action == "calendar_disconnect":
            self.disconnect_calendar()
        elif action == "notebooklm_connect":
            self.start_notebooklm(NOTEBOOKLM_CONNECT)
        elif action == "notebooklm_sync":
            self.start_notebooklm()
        elif action == "notebooklm_open":
            webbrowser.open(notebooklm_store.APP_URL)
        elif action == "notebooklm_duplicates":
            self.find_notebooklm_duplicates()
        elif action == "notebooklm_disconnect":
            self.disconnect_notebooklm()
        elif action == "deadline":
            if value.startswith(self.config.base_url.rstrip("/") + "/"):
                webbrowser.open(value)
            else:
                self.dispatch("open", value)
        elif action == "announcement":
            target = announcements.open_target(value, self.model.root)
            if isinstance(target, Path):
                try:
                    os.startfile(str(target))
                except OSError:
                    self.model.note = tr("Could not open the announcement.")
            elif target:
                webbrowser.open(target)
        elif action == "reveal":
            target = open_target(self.model.root, value)
            if target is not None and target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            elif target is not None:
                os.startfile(str(target))
        elif action in ("folder", "open"):
            target = self.model.root if action == "folder" else open_target(self.model.root, value)
            if target and target.exists():
                try:
                    os.startfile(str(target))
                    if action == "open" and target.is_file():
                        for item in self.model.recent:
                            if item.path == value:
                                self.model.recent_seen.opened(item)
                        self.save()
                except OSError:
                    self.model.note = tr("Could not open the file or folder.")
            else:
                self.model.note = tr("The file or folder does not exist yet; sync first.")
        elif action == "logout" and self.model.busy is None:
            # Asked from the main window, so the question belongs in front of it.
            if self.ask_yes_no(
                tr("Sign out?"),
                tr("All sign-in data is removed; you will need to enter your school details "
                   "again to sign in. Your downloaded files are kept."),
            ):
                try:
                    warnings = jobs.logout(self.config)
                    if warnings:
                        self.model.note = warnings[0]
                except OSError:
                    self.model.note = tr("Could not sign out.")
        elif action == "quit":
            if self.job_holds_app():
                self.show_message("info", "Blackboard Sync", settings_form.T_BUSY, parent=self.root)
                return
            jobs.notebooklm_child.stop()  # safe at any moment; the next run goes on from there
            self.closed = True
            self.icon.stop()
            self.root.destroy()
            return
        self.refresh()

    def job_holds_app(self):
        """Quitting has to wait. A look at the session does not count: it needs no window, and
        ending it could leave its browser behind, so it finishes on its own in a moment."""
        return self.model.busy not in (None, SESSION_JOB) or self.model.updates.busy == "download"

    def start_uninstall(self):
        if package.is_packaged():
            self.show_message("info", "Blackboard Sync", uninstall.STORE_REMOVAL)
            return
        if self.model.busy or self.model.updates.busy or self.model.calendar_busy or self.model.notebooklm_busy:
            self.show_message("info", "Blackboard Sync", uninstall.BUSY)
            return
        self.uninstalling = True
        if self.web is not None:
            choice = self.web.ask_uninstall(sync_root(self.settings.dest))
        else:
            from .main_window import ask_uninstall

            choice = ask_uninstall(self.dialog_parent(), sync_root(self.settings.dest))
        if choice is None:
            self.uninstalling = False
            return
        if self.window is not None:
            # Closed without window_closed: no "runs in the background" hint now.
            window, self.window = self.window, None
            window.destroy()
        try:
            self.config.dest = self.settings.dest
            warnings = uninstall.uninstall(
                self.config, choice, before_cleanup=self.prepare_uninstall,
                owns_app_lock=True, app_cleanup=lambda: [],
            )
        except (BlackboardSyncError, OSError) as exc:
            self.show_message("error", "Blackboard Sync", str(exc))
            self.uninstalling = False
            return
        if warnings:
            self.show_message("warning", "Blackboard Sync", "\n\n".join(warnings))
        warnings = uninstall.remove_app()
        if warnings:
            self.show_message("warning", "Blackboard Sync", "\n\n".join(warnings))
        self.closed = True
        self.icon.stop()
        self.root.destroy()

    def prepare_uninstall(self):
        from .startup import close_logging

        lock = getattr(self, "lifetime_lock", None)
        if lock is not None:
            lock.close()
        close_logging()

    def open_settings(self):
        """"Ayarlar…" in the tray menu: the main window on Genel."""
        self.show_window(GENERAL)

    def form_values(self):
        """What the Genel form shows when nothing is edited: the saved settings."""
        saved = jobs.saved_settings(self.config)
        return settings_form.initial_values(saved, self.settings, self.model.autostart)

    @property
    def window_open(self):
        return self.window is not None and self.window.state.open

    def show_window(self, section=None):
        """Open the main window (or bring it forward); its taskbar button comes with it."""
        if self.web is not None:
            from .web_window import WebMainWindow as MainWindow
        else:
            from .main_window import MainWindow

        if self.uninstalling:
            return
        if self.window is None:
            log.info("Opening the main window (first run %s)", not self.model.configured)
            web = {} if self.web is None else {
                "theme": lambda: self.settings.theme, "on_theme": self.theme_chosen, "packaged": package.is_packaged}
            self.window = MainWindow(self.root, self.form_values(), self.window_status(),
                                     self.settings_submitted, self.dispatch, self.window_closed,
                                     on_values=self.form_values,
                                     on_open=lambda path: self.dispatch("open", path),
                                     on_reveal=lambda path: self.dispatch("reveal", path),
                                     on_deadlines=lambda: deadlines.load_calendar(self.config, self.settings.dest),
                                     on_deadline=lambda target: self.dispatch("deadline", target),
                                     on_announcements=lambda: announcements.load_rows(self.config),
                                     on_open_announcement=lambda row: self.dispatch("announcement", row),
                                     on_courses=lambda: courses.load_rows(self.config),
                                     on_course_toggle=self.course_toggled,
                                     on_section=lambda _section: self.refresh(),
                                     recent_seen=self.model.recent_seen, on_seen=self.save, **web)
        self.window.show(section)
        self.refresh()

    def course_toggled(self, course_id, enabled):
        """A Dersler checkbox: save the choice; a course ticked again syncs right away."""
        try:
            courses.set_enabled(self.config, course_id, enabled)
        except OSError as exc:
            log.warning("Could not save the course choice: %s", exc)
            self.model.note = tr("Could not save the course choice: {error}").format(error=exc.strerror or exc)
        jobs.refresh_hidden_folders(self.config, self.model)
        if enabled and not self.uninstalling and self.model.account()[0] is not None:
            self.start_job("sync")  # does nothing while another job runs
        self.refresh()

    def window_closed(self):
        """Only the window went: the tray icon, timers and jobs go on."""
        log.info("Main window closed; the app keeps running in the tray")
        self.show_tray_hint()

    def show_tray_hint(self):
        """Once: the window is gone, the app lives on in the (maybe hidden) tray icon."""
        marker = self.config.data_dir / TRAY_HINT_SHOWN
        if marker.exists():
            return
        try:
            self.icon.notify(TRAY_HINT, TRAY_HINT_TITLE)
            marker.touch()
        except Exception:
            log.exception("Could not show the tray hint")

    def settings_submitted(self, values, login):
        # Do not apply a new destination/school to the result of an in-flight job;
        # a look at the session changes no files.
        if self.model.busy not in (None, SESSION_JOB) or self.model.updates.busy == "download":
            return settings_form.T_BUSY, "base_url"
        try:
            submission = settings_form.submit(values, self.settings)
        except SettingsError as exc:
            return str(exc), exc.field
        choice = None
        files = jobs.synced_file_count(self.config, self.settings.dest) if submission.dest_changed else 0
        if files:
            choice = self.ask_dest_choice(self.settings.dest, submission.settings.dest, files)
            if choice is None:
                return settings_form.T_DEST_NOT_CHANGED, "dest"
        try:
            autostart.set_enabled(submission.autostart)
            save_settings(self.config.data_dir, submission.settings)
        except OSError as exc:
            log.exception("Could not save settings")
            return tr("Could not save the settings: {error}").format(error=exc), "dest"
        self.settings = submission.settings
        self.model.apply_settings(
            self.settings.dest,
            submission.school_changed,
            self.settings.check_updates,
            self.settings.sync_interval_minutes,
            dest_choice=choice,
            auto_relogin=self.settings.auto_relogin,
        )
        self.save()
        self.start_next()  # a move goes before signing in to a new school
        if submission.needs_login(login):
            if self.model.busy is None:
                self.start_job("login")
            else:
                self.login_after_job = True
        self.refresh()
        if submission.language_changed:
            # After the window has taken the saved values back.
            self.root.after(0, self.offer_language_restart)
        return None

    def offer_language_restart(self):
        """The language is read when the app starts: offer to start again in the new one now."""
        if self.ask_yes_no(settings_form.T_LANGUAGE_RESTART_TITLE, settings_form.T_LANGUAGE_RESTART):
            self.restart()

    def restart(self):
        """Start a new copy that takes over once this one has quit, then quit."""
        if self.job_holds_app():
            self.model.note = tr("Could not restart Blackboard Sync; quit it and open it again.")
            self.refresh()
            return
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            jobs.relaunch(self.config, app_command(), creationflags=flags)
        except OSError:
            log.exception("Could not restart")
            self.model.note = tr("Could not restart Blackboard Sync; quit it and open it again.")
            self.refresh()
            return
        self.dispatch("quit")

    def ask_dest_choice(self, old, new, files):
        if self.web is not None:
            return self.web.ask_dest_choice(old, new, files)
        from .main_window import ask_dest_choice

        return ask_dest_choice(self.dialog_parent(), old, new, files)

    # -- dialogs: Tk's in front of the Tk window, native message boxes for the WebView2 page ----
    def dialog_parent(self):
        """What a question is asked in front of: the main window while it is open, else the hidden root."""
        return self.window.window if self.window_open else self.root

    def ask_yes_no(self, title, message):
        if self.web is not None:
            return self.web.ask_yes_no(title, message)
        from tkinter import messagebox

        return messagebox.askyesno(title, message, parent=self.dialog_parent())

    def ask_destructive(self, title, message, button):
        """A yes-or-no question whose yes cannot be taken back: it is not the default answer."""
        if self.web is not None:
            return self.web.ask_destructive(title, message, button)
        return self.ask_yes_no(title, message)

    def show_message(self, kind, title, message, parent=None):
        """``kind`` is "info", "warning" or "error"; ``parent`` overrides ``dialog_parent`` (Tk)."""
        if self.web is not None:
            self.web.show_message(kind, title, message)
            return
        from tkinter import messagebox

        show = getattr(messagebox, {"info": "showinfo", "warning": "showwarning", "error": "showerror"}[kind])
        show(title, message, parent=parent if parent is not None else self.dialog_parent())

    def save(self):
        try:
            jobs.save_model(self.config, self.model)
        except OSError:
            log.exception("Could not save tray state")


def run_web(config, show_window, lock):
    """Run the app with the WebView2 main window; False (nothing started) where WebView2 cannot run."""
    from .loop import EventLoop
    from .web_window import WebHost

    loop = EventLoop()
    try:
        host = WebHost.create(loop, jobs.effective_settings(config).theme)
    except Exception:
        log.exception("The WebView2 main window is unavailable; using the Tk window")
        return False
    loop.host = host
    loop.on_destroy.append(host.quit)  # Quit: the window closes and pywebview's loop ends
    app = TrayApp(config, loop, show_window)
    app.web = host
    app.lifetime_lock = lock
    log.info("Main window: WebView2")
    host.run(app.run)
    return True


def main(argv=None):
    if sys.platform != "win32":
        print("The Windows tray app requires Windows.", file=sys.stderr)
        return 1
    import tkinter as tk

    parser = argparse.ArgumentParser(description="Blackboard Sync Windows tray")
    parser.add_argument("--notification", choices=[activation.UPDATE_URI])
    parser.add_argument("--store-notification", action="store_true", help=argparse.SUPPRESS)
    # The login item and the updater's silent reinstall start the app in the
    # tray only; any other start (installer, Start Menu) shows its main window.
    parser.add_argument(autostart.BACKGROUND, action="store_true")
    # A copy started by ``restart`` (a new language): it waits for the old one to quit.
    parser.add_argument(jobs.RESTARTING, action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    # Logging is set up by .startup, before this module is imported.
    config = Config.from_env()
    config.ensure_data_dir()
    if args.notification:
        activation.request_update(config)
    # The packaged (MSIX) app's login item cannot pass --background.
    show_window = args.store_notification or not (args.background or args.notification or autostart.started_at_login())
    lock = jobs.wait_for_instance(config) if args.restarting else jobs.single_instance(config)
    if lock is None:
        log.info("Another copy is already running%s", "; asking it to show its window" if show_window else "")
        if show_window:
            activation.request_window(config)
        return 0
    try:
        activation.take_window_request(config)  # left over from an earlier run
        try:
            activation.register()
            autostart.upgrade_legacy()
        except OSError:
            log.exception("Could not register update-toast activation or login item")
        if os.environ.get(UI_ENV, "web").strip().lower() != "tk" and run_web(config, show_window, lock):
            return 0
        root = tk.Tk()
        root.withdraw()
        if sys.platform == "win32":
            from blackboard_sync.windows.theme import apply_theme

            apply_theme(root)
        root.report_callback_exception = lambda *exc: log.error("Tk callback failed", exc_info=exc)
        app = TrayApp(config, root, show_window)
        app.lifetime_lock = lock
        app.run()
    finally:
        lock.close()
    return 0
