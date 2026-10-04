"""Windows-only entry point; Tk owns state, tray and workers enqueue events."""

import logging
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.menubar.model import open_target, RunOutcome
from blackboard_sync.settings import SettingsError, save_settings
from . import autostart, notifications
from .presentation import icon_image, render_menu

log = logging.getLogger(__name__)


def cli_runner(command, **kwargs):
    # pythonw can discard standard streams even with redirected handles. Run
    # the console interpreter hidden so the CLI always returns its JSON report.
    command = list(command)
    executable = Path(command[0])
    if executable.name.lower() == "pythonw.exe":
        command[0] = str(executable.with_name("python.exe"))
    # The CLI emits UTF-8 even when the Windows ANSI code page is different.
    return subprocess.run(command, **kwargs, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class TrayApp:
    def __init__(self, config, root):
        import pystray

        self.config, self.root = config, root
        self.settings = jobs.effective_settings(config)
        self.model = jobs.load_model(config, jobs.utcnow(), autostart.is_installed())
        self.events = queue.Queue()
        self.window = None
        self.closed = False
        self.drawn = None
        self.drawn_icon = None
        self.icon = pystray.Icon("Blackboard Sync", icon_image(self.model.icon()), "Blackboard Sync")
        self.refresh()

    def run(self):
        self.icon.run_detached()
        self.root.after(100, self.poll)
        self.root.after(1000, self.tick)
        if not self.model.configured:
            self.root.after(200, self.open_settings)
        self.root.mainloop()

    def poll(self):
        try:
            while not self.closed:
                callback, args = self.events.get_nowait()
                try:
                    callback(*args)
                except Exception:
                    log.exception("UI event failed")
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(100, self.poll)

    def tick(self):
        if self.model.due(jobs.utcnow()):
            self.start_job("sync")
        self.refresh()
        self.root.after(30000, self.tick)

    def start_job(self, job):
        if not self.model.begin(job):
            return
        self.refresh()
        settings = self.settings
        def worker():
            try:
                result = (jobs.run_login(settings, runner=cli_runner) if job == "login"
                          else jobs.run_sync(job, settings, runner=cli_runner))
            except Exception as exc:
                log.exception("CLI job failed")
                result = (False, str(exc)) if job == "login" else RunOutcome(status="error", message=str(exc))
            self.events.put((self.job_done, (job, result)))
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
        menu = self.model.menu(jobs.utcnow())
        if menu != self.drawn:
            self.icon.menu = render_menu(menu.entries,
                                        lambda action, value: self.events.put((self.dispatch, (action, value))),
                                        pystray.Menu, pystray.MenuItem)
            self.drawn = menu

    def dispatch(self, action, value=""):
        from tkinter import messagebox

        if action in ("sync", "refetch", "login"):
            self.start_job(action)
        elif action == "settings":
            self.open_settings()
        elif action == "autostart":
            try:
                autostart.set_enabled(not autostart.is_installed())
            except OSError:
                self.model.note = "Açılışta başlatma ayarı değiştirilemedi."
        elif action == "releases":
            webbrowser.open(value)
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
            if messagebox.askyesno("Hesaptan çıkış yapılsın mı?", "İndirilen dosyalarınız korunacak.", parent=self.root):
                try:
                    jobs.logout(self.config)
                except OSError:
                    self.model.note = "Hesaptan çıkış yapılamadı."
        elif action == "quit":
            if self.model.busy:
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
            self.window = SettingsWindow(self.root, values, saved is None, self.settings_submitted,
                                         lambda: setattr(self, "window", None))
        self.window.show()

    def settings_submitted(self, values, login):
        # Do not apply a new destination/school to the result of an in-flight job.
        if self.model.busy:
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
        self.model.apply_settings(self.settings.dest, submission.school_changed)
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


def main():
    if sys.platform != "win32":
        print("The Windows tray app requires Windows.", file=sys.stderr)
        return 1
    import tkinter as tk

    config = Config.from_env()
    config.ensure_data_dir()
    logging.basicConfig(filename=str(config.data_dir / "windows-tray.log"), encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock = jobs.single_instance(config)
    if lock is None:
        return 0
    try:
        root = tk.Tk()
        root.withdraw()
        TrayApp(config, root).run()
    finally:
        lock.close()
    return 0
