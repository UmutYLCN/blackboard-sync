"""Windows-only entry point; Tk owns state, tray and workers enqueue events."""

import argparse
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from blackboard_sync import deleted, relocate, runtime, updater, uninstall
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.menubar.main_window_model import GENERAL, main_status, shows_window_at_launch
from blackboard_sync.menubar.model import DEST_KEEP, MOVE_JOB, open_target, RunOutcome, UPDATE_ACTIONS
from blackboard_sync.settings import SettingsError, save_settings
from blackboard_sync.system import sync_root
from . import activation, autostart, notifications
from .presentation import icon_image, render_menu

log = logging.getLogger(__name__)

# The two executables of the installed app (packaging/blackboard_sync_windows.spec).
GUI_EXE = "Blackboard Sync.exe"
CLI_EXE = "blackboard-sync-cli.exe"
# Shown once, when the main window first closes: where the app went.
TRAY_HINT_TITLE = "Blackboard Sync arka planda çalışıyor"
TRAY_HINT = ("Menü için saatin yanındaki Blackboard Sync simgesine sağ tıklayın. "
             "Simge görünmüyorsa gizli simgeleri gösteren ^ okuna tıklayın.")
TRAY_HINT_SHOWN = "tray-hint-shown"
# Workers wake Tk with this virtual event, so the UI never polls its queue.
WAKE_EVENT = "<<bbsync>>"
# The request files (toast click, second start) come from other processes and
# cannot wake Tk, so they are checked on a slow timer; this is also the safety
# net should a wake-up ever be lost.
REQUEST_CHECK_MS = 2000
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


def cli_runner(command, **kwargs):
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
    # The CLI emits UTF-8 even when the Windows ANSI code page is different.
    return subprocess.run(command, **kwargs, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class TrayApp:
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
        if self.model.update_due(jobs.utcnow()):
            self.start_update_check(manual=False)
        self.refresh()
        self.root.after(30000, self.tick)

    def start_next(self):
        """A job a folder change asked for goes first, then the scheduled sync."""
        jobs.refresh_session(self.config, self.model, self.settings)  # a refetch waits for it
        job = self.model.pending_job()
        if job is not None:
            self.start_job(job)
        elif self.model.due(jobs.utcnow()):
            self.start_job("sync")

    def start_job(self, job, refetch_keys=None):
        old, new = self.model.move_from, self.model.dest
        if job == MOVE_JOB and old is None:
            return
        if self.model.updates.busy == "download" or not self.model.begin(job):
            return
        if job == "login":
            self.model.login_method = jobs.login_method()
        self.refresh()
        settings, config, term_name = self.settings, self.config, self.model.past_term
        def worker():
            try:
                if job == "login":
                    result = jobs.run_login(settings, runner=cli_runner)
                elif job == MOVE_JOB:
                    result = jobs.run_move_guarded(config, old, new)
                else:
                    result = jobs.run_sync(job, settings, runner=cli_runner, refetch_keys=refetch_keys, term_name=term_name)
            except Exception as exc:
                log.exception("CLI job failed")
                result = ((False, str(exc)) if job == "login"
                          else relocate.MoveResult(status="error", message=str(exc)) if job == MOVE_JOB
                          else RunOutcome(status="error", message=str(exc)))
            self.post(self.job_done, job, result)
        threading.Thread(target=worker, daemon=True).start()

    def job_done(self, job, result):
        if job == "login":
            self.model.finish_login(*result, jobs.utcnow())
        elif job == MOVE_JOB:
            log.info("Move finished: %s, %d moved, %d kept", result.status, result.moved, len(result.kept))
            self.post_notifications(
                self.model.finish_move(result.status, result.moved, len(result.kept), result.message))
        else:
            for note in self.model.finish_sync(result, jobs.utcnow()):
                threading.Thread(target=self.notify, args=(note,), daemon=True).start()
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
            self.model.note = "Güncellemeden önce çalışan işlemin tamamlanmasını bekleyin."
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
            error = "Güncelleme yüklenemedi; daha sonra tekrar deneyin."
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

    def notify(self, note):
        try:
            notifications.show(note)
        except (OSError, subprocess.SubprocessError):
            log.exception("Windows notification failed")

    def refresh(self):
        import pystray

        jobs.refresh_session(self.config, self.model, self.settings)
        try:
            self.model.autostart = autostart.is_installed()
        except OSError:
            log.exception("Could not read login item")
        if self.past_terms_wanted():
            self.start_past_terms()
        state = self.model.icon()
        # Session expiry can be detected before the first scheduled sync.
        if self.model.session_expired:
            from blackboard_sync.menubar.model import Icon
            state = Icon.EXPIRED
        if state != self.drawn_icon:
            self.icon.icon = icon_image(state)
            self.drawn_icon = state
        if self.window_open:
            self.window.update_status(main_status(self.model, jobs.utcnow()))
        menu = self.model.menu(jobs.utcnow())
        if menu != self.drawn:
            self.icon.menu = render_menu(menu.entries,
                                        lambda action, value: self.post(self.dispatch, action, value),
                                        pystray.Menu, pystray.MenuItem)
            self.drawn = menu

    def dispatch(self, action, value=""):
        from tkinter import messagebox

        if self.uninstalling:
            return
        if action in ("sync", "refetch", "login"):
            self.start_job(action)
        elif action == "check_updates":
            self.start_update_check()
        elif action == "update":
            self.start_update()
        elif action == "uninstall":
            self.start_uninstall()
            return
        elif action == "settings":
            self.show_window(GENERAL)
        elif action in ("folder", "open"):
            target = self.model.root if action == "folder" else open_target(self.model.root, value)
            if target and target.exists():
                try:
                    os.startfile(str(target))
                except OSError:
                    self.model.note = "Dosya veya klasör açılamadı."
            else:
                self.model.note = "Dosya veya klasör henüz yok; önce senkronize edin."
        elif action == "logout" and self.model.busy is None:
            # Asked from the main window, so the question belongs in front of it.
            parent = self.window.window if self.window_open else self.root
            if messagebox.askyesno(
                "Hesaptan çıkış yapılsın mı?",
                "Tüm giriş verileri silinir; yeniden giriş yaparken okul bilgilerinizi "
                "tekrar girmeniz gerekir. İndirilen dosyalarınız korunacak.",
                parent=parent,
            ):
                try:
                    warnings = jobs.logout(self.config)
                    if warnings:
                        self.model.note = warnings[0]
                except OSError:
                    self.model.note = "Hesaptan çıkış yapılamadı."
        elif action == "quit":
            if self.model.busy or self.model.updates.busy == "download":
                messagebox.showinfo("Blackboard Sync", "Önce çalışan işlemin tamamlanmasını bekleyin.", parent=self.root)
                return
            self.closed = True
            self.icon.stop()
            self.root.destroy()
            return
        self.refresh()

    def start_past_terms(self):
        """Look up the past terms for the list in Genel, in the background."""
        if not self.model.begin("past_terms"):
            return
        settings = self.settings
        def worker():
            self.post(self.past_terms_done, *jobs.run_past_terms(settings, runner=cli_runner))
        threading.Thread(target=worker, daemon=True).start()

    def past_terms_done(self, names, outcome):
        self.model.finish_past_terms(names, outcome)
        self.start_next()  # a move the window saved meanwhile goes first
        if self.login_after_job and self.model.busy is None:
            self.login_after_job = False
            self.start_job("login")
        self.refresh()

    def download_past_term(self, name):
        if not self.model.select_past_term(name):
            return False
        self.start_job("past_term")
        return self.model.busy == "past_term"

    def start_uninstall(self):
        from tkinter import messagebox
        from .main_window import ask_uninstall

        parent = self.window.window if self.window_open else self.root
        if self.model.busy or self.model.updates.busy:
            messagebox.showinfo("Blackboard Sync", uninstall.BUSY, parent=parent)
            return
        self.uninstalling = True
        choice = ask_uninstall(parent, sync_root(self.settings.dest))
        if choice is None:
            self.uninstalling = False
            return
        if self.window is not None:
            # Closed without window_closed: no "runs in the background" hint now.
            window, self.window = self.window, None
            window.destroy()
            parent = self.root
        try:
            self.config.dest = self.settings.dest
            warnings = uninstall.uninstall(
                self.config, choice, before_cleanup=self.prepare_uninstall,
                owns_app_lock=True, app_cleanup=lambda: [],
            )
        except (BlackboardSyncError, OSError) as exc:
            messagebox.showerror("Blackboard Sync", str(exc), parent=parent)
            self.uninstalling = False
            return
        if warnings:
            messagebox.showwarning("Blackboard Sync", "\n\n".join(warnings), parent=parent)
        warnings = uninstall.remove_app()
        if warnings:
            messagebox.showwarning("Blackboard Sync", "\n\n".join(warnings), parent=parent)
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

    def past_terms_wanted(self):
        """Genel is in view and its past-term list still has to be looked up."""
        return (self.window_open and self.window.state.section == GENERAL and not self.uninstalling
                and self.model.past_terms_due())

    def show_window(self, section=None):
        """Open the main window (or bring it forward); its taskbar button comes with it."""
        from .main_window import MainWindow

        if self.uninstalling:
            return
        if self.window is None:
            log.info("Opening the main window (first run %s)", not self.model.configured)
            self.window = MainWindow(self.root, self.form_values(), main_status(self.model, jobs.utcnow()),
                                     self.settings_submitted, self.dispatch, self.window_closed,
                                     on_values=self.form_values,
                                     on_open=lambda path: self.dispatch("open", path),
                                     on_missing=lambda: deleted.load_missing(self.config, self.settings.dest),
                                     on_deleted_action=self.deleted_action,
                                     on_past_term=self.download_past_term,
                                     on_section=lambda _section: self.refresh())
        if not self.window_open:
            self.model.reload_past_terms()
        self.window.show(section)
        self.refresh()  # on Genel, starts looking up the past terms

    def deleted_action(self, action, keys):
        if self.uninstalling or self.model.busy is not None or self.model.updates.busy == "download":
            return settings_form.T_BUSY
        try:
            if action == "dismiss":
                deleted.dismiss_missing(self.config, self.settings.dest, keys)
            elif keys:
                self.start_job("refetch", refetch_keys=keys)
        except Exception as exc:
            log.warning("Deleted-file action failed: %s", exc)
            return "İşlem tamamlanamadı; çalışan senkron varsa bitmesini bekleyin."
        return None

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
        # the past-term lookup the open window starts changes no files.
        if self.model.busy not in (None, "past_terms") or self.model.updates.busy == "download":
            return settings_form.T_BUSY, "base_url"
        try:
            submission = settings_form.submit(values, self.settings)
        except SettingsError as exc:
            return str(exc), exc.field
        choice = DEST_KEEP
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
            return f"Ayarlar kaydedilemedi: {exc}", "dest"
        self.settings = submission.settings
        self.model.apply_settings(
            self.settings.dest,
            submission.school_changed,
            self.settings.check_updates,
            self.settings.sync_interval_minutes,
            dest_choice=choice,
        )
        self.save()
        self.start_next()  # a move goes before signing in to a new school
        if submission.needs_login(login):
            if self.model.busy is None:
                self.start_job("login")
            else:
                self.login_after_job = True
        self.refresh()
        return None

    def ask_dest_choice(self, old, new, files):
        from .main_window import ask_dest_choice

        parent = self.window.window if self.window_open else self.root
        return ask_dest_choice(parent, old, new, files)

    def save(self):
        try:
            jobs.save_model(self.config, self.model)
        except OSError:
            log.exception("Could not save tray state")


def main(argv=None):
    if sys.platform != "win32":
        print("The Windows tray app requires Windows.", file=sys.stderr)
        return 1
    import tkinter as tk

    parser = argparse.ArgumentParser(description="Blackboard Sync Windows tray")
    parser.add_argument("--notification", choices=[activation.UPDATE_URI])
    # The login item and the updater's silent reinstall start the app in the
    # tray only; any other start (installer, Start Menu) shows its main window.
    parser.add_argument(autostart.BACKGROUND, action="store_true")
    args = parser.parse_args(argv)
    # Logging is set up by .startup, before this module is imported.
    config = Config.from_env()
    config.ensure_data_dir()
    if args.notification:
        activation.request_update(config)
    show_window = not (args.background or args.notification)
    lock = jobs.single_instance(config)
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
        root = tk.Tk()
        root.withdraw()
        root.report_callback_exception = lambda *exc: log.error("Tk callback failed", exc_info=exc)
        app = TrayApp(config, root, show_window)
        app.lifetime_lock = lock
        app.run()
    finally:
        lock.close()
    return 0
