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

from blackboard_sync import runtime, updater
from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.menubar.model import open_target, RunOutcome, UPDATE_ACTIONS
from blackboard_sync.settings import SettingsError, save_settings
from . import activation, autostart, notifications
from .presentation import icon_image, render_menu

log = logging.getLogger(__name__)

# The two executables of the installed app (packaging/blackboard_sync_windows.spec).
GUI_EXE = "Blackboard Sync.exe"
CLI_EXE = "blackboard-sync-cli.exe"
# Shown once, when the first settings window closes: where the app went.
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
    def __init__(self, config, root, show_settings=False):
        import pystray

        self.config, self.root = config, root
        self.show_settings = show_settings
        self.settings = jobs.effective_settings(config)
        self.model = jobs.load_model(config, jobs.utcnow(), autostart.is_installed())
        self.events = queue.Queue()
        self.poll_errors = LogThrottle()
        self.window = None
        self.closed = False
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
        if self.show_settings or not self.model.configured:
            self.root.after(200, self.open_settings)
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
        self.drain()
        if not self.closed:
            try:
                update, settings = activation.take_requests(self.config)
                if update:
                    self.notification_clicked({"action": "update"})
                if settings:
                    log.info("Started again; showing the settings window")
                    self.open_settings()
            except OSError as exc:
                # A persistent failure (say a denied folder) must not flood the log.
                if self.poll_errors.allow((type(exc), exc.errno, exc.filename)):
                    log.exception("Could not read toast activation")
            self.root.after(REQUEST_CHECK_MS, self.poll)

    def tick(self):
        if self.model.due(jobs.utcnow()):
            self.start_job("sync")
        if self.model.update_due(jobs.utcnow()):
            self.start_update_check(manual=False)
        self.refresh()
        self.root.after(30000, self.tick)

    def start_job(self, job):
        if self.model.updates.busy == "download" or not self.model.begin(job):
            return
        if job == "login":
            self.model.login_method = jobs.login_method()
        self.refresh()
        settings = self.settings
        def worker():
            try:
                result = (jobs.run_login(settings, runner=cli_runner) if job == "login"
                          else jobs.run_sync(job, settings, runner=cli_runner))
            except Exception as exc:
                log.exception("CLI job failed")
                result = (False, str(exc)) if job == "login" else RunOutcome(status="error", message=str(exc))
            self.post(self.job_done, job, result)
        threading.Thread(target=worker, daemon=True).start()

    def job_done(self, job, result):
        if job == "login":
            self.model.finish_login(*result, jobs.utcnow())
        else:
            for note in self.model.finish_sync(result, jobs.utcnow()):
                threading.Thread(target=self.notify, args=(note,), daemon=True).start()
        self.save()
        if self.model.due(jobs.utcnow()):
            self.start_job("sync")
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
        state = self.model.icon()
        # Session expiry can be detected before the first scheduled sync.
        if self.model.session_expired:
            from blackboard_sync.menubar.model import Icon
            state = Icon.EXPIRED
        if state != self.drawn_icon:
            self.icon.icon = icon_image(state)
            self.drawn_icon = state
        if self.window is not None:
            self.window.update_status(settings_form.window_status(self.model))
        menu = self.model.menu(jobs.utcnow())
        if menu != self.drawn:
            self.icon.menu = render_menu(menu.entries,
                                        lambda action, value: self.post(self.dispatch, action, value),
                                        pystray.Menu, pystray.MenuItem)
            self.drawn = menu

    def dispatch(self, action, value=""):
        from tkinter import messagebox

        if action in ("sync", "refetch", "login"):
            self.start_job(action)
        elif action == "check_updates":
            self.start_update_check()
        elif action == "update":
            self.start_update()
        elif action == "settings":
            self.open_settings()
        elif action in ("folder", "open"):
            target = self.model.dest if action == "folder" else open_target(self.model.dest, value)
            if target and target.exists():
                try:
                    os.startfile(str(target))
                except OSError:
                    self.model.note = "Dosya veya klasör açılamadı."
            else:
                self.model.note = "Dosya veya klasör henüz yok; önce senkronize edin."
        elif action == "logout" and self.model.busy is None:
            # Asked from the settings window, so the question belongs in front of it.
            parent = self.window.window if self.window is not None else self.root
            if messagebox.askyesno("Hesaptan çıkış yapılsın mı?", "İndirilen dosyalarınız korunacak.", parent=parent):
                try:
                    jobs.logout(self.config)
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

    def open_settings(self):
        from .settings_window import SettingsWindow

        if self.window is None:
            saved = jobs.saved_settings(self.config)
            values = settings_form.initial_values(saved, self.settings, self.model.autostart)
            log.info("Opening the settings window (first run %s)", saved is None)
            self.window = SettingsWindow(self.root, values, settings_form.window_status(self.model),
                                         saved is None, self.settings_submitted, self.dispatch,
                                         self.settings_closed)
        self.window.show()

    def settings_closed(self):
        self.window = None
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
        # Do not apply a new destination/school to the result of an in-flight job.
        if self.model.busy or self.model.updates.busy == "download":
            return "Önce çalışan işlemin tamamlanmasını bekleyin.", "base_url"
        try:
            submission = settings_form.submit(values, self.settings)
            autostart.set_enabled(submission.autostart)
            save_settings(self.config.data_dir, submission.settings)
        except SettingsError as exc:
            return str(exc), exc.field
        except OSError as exc:
            log.exception("Could not save settings")
            return f"Ayarlar kaydedilemedi: {exc}", "dest"
        self.settings = submission.settings
        self.model.apply_settings(
            self.settings.dest,
            submission.school_changed,
            self.settings.check_updates,
            self.settings.sync_interval_minutes,
        )
        self.save()
        if submission.needs_login(login):
            self.start_job("login")
        self.refresh()
        return None

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
    # tray only; any other start (installer, Start Menu) shows its window.
    parser.add_argument(autostart.BACKGROUND, action="store_true")
    args = parser.parse_args(argv)
    # Logging is set up by .startup, before this module is imported.
    config = Config.from_env()
    config.ensure_data_dir()
    if args.notification:
        activation.request_update(config)
    show_settings = not (args.background or args.notification)
    lock = jobs.single_instance(config)
    if lock is None:
        log.info("Another copy is already running%s", "; asking it to show its window" if show_settings else "")
        if show_settings:
            activation.request_settings(config)
        return 0
    try:
        activation.take_settings_request(config)  # left over from an earlier run
        try:
            activation.register()
            autostart.upgrade_legacy()
        except OSError:
            log.exception("Could not register update-toast activation or login item")
        root = tk.Tk()
        root.withdraw()
        root.report_callback_exception = lambda *exc: log.error("Tk callback failed", exc_info=exc)
        TrayApp(config, root, show_settings).run()
    finally:
        lock.close()
    return 0
