"""The menu bar GUI: a thin rumps layer that draws ``AppModel`` and forwards events.

Decisions (when to sync, what the menu says, which notification to post) live
in ``model.py``; this module only owns threads, AppKit objects and ``open``.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import threading
from pathlib import Path

from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs, launchagent, settings_form
from blackboard_sync.menubar.model import (
    T_AUTOSTART,
    T_OPEN_FOLDER,
    T_QUIT,
    T_RECENT,
    T_RECENT_EMPTY,
    T_SETTINGS,
    AppModel,
    Icon,
    MenuModel,
    Notification,
    RunOutcome,
    open_target,
)
from blackboard_sync.settings import SettingsError, save_settings

log = logging.getLogger("blackboard_sync.menubar")

TICK_SECONDS = 30
# SF Symbols per state; expired and error are tinted so they stand out.
SYMBOLS = {
    Icon.IDLE: ("graduationcap", None),
    Icon.SYNCING: ("arrow.triangle.2.circlepath", None),
    Icon.EXPIRED: ("person.crop.circle.badge.exclamationmark", "systemRedColor"),
    Icon.ERROR: ("exclamationmark.triangle", "systemOrangeColor"),
}
FALLBACK_TITLES = {Icon.IDLE: "BB", Icon.SYNCING: "BB ↻", Icon.EXPIRED: "BB ⛔", Icon.ERROR: "BB ⚠"}
DESCRIPTIONS = {
    Icon.IDLE: "Blackboard Sync",
    Icon.SYNCING: "Blackboard Sync: senkronize ediliyor",
    Icon.EXPIRED: "Blackboard Sync: oturum sona erdi",
    Icon.ERROR: "Blackboard Sync: hata",
}


def symbol_image(icon: Icon):
    from AppKit import NSColor, NSImage, NSImageSymbolConfiguration

    name, color = SYMBOLS[icon]
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, DESCRIPTIONS[icon])
    if image is None:
        return None
    if color:
        config = NSImageSymbolConfiguration.configurationWithPaletteColors_([getattr(NSColor, color)()])
        image = image.imageWithSymbolConfiguration_(config)
        image.setTemplate_(False)
    else:
        image.setTemplate_(True)  # follows the light/dark menu bar
    return image


def open_path(path: Path) -> None:
    subprocess.Popen(["open", str(path)], stdin=subprocess.DEVNULL)


def build_app(config: Config):
    import rumps
    from PyObjCTools import AppHelper

    class MenuBarApp(rumps.App):
        def __init__(self):
            super().__init__("Blackboard Sync", title=FALLBACK_TITLES[Icon.IDLE], quit_button=None)
            self.config = config
            self.settings = jobs.effective_settings(config)
            self.model = jobs.load_model(config, jobs.utcnow(), launchagent.is_installed())
            self._drawn: MenuModel | None = None
            self._drawn_icon: Icon | None = None
            self._settings_window = None
            self._login_after_job = False  # asked for while another job was running
            self._timer = rumps.Timer(self.tick, TICK_SECONDS)
            self._timer.start()
            if not self.model.configured:
                # First launch: show the settings window once the app is running.
                self._first_run_timer = rumps.Timer(self._first_run, 1)
                self._first_run_timer.start()
            rumps.events.on_notification.register(self.notification_clicked)
            rumps.events.on_wake.register(self.tick)

        # -- events ------------------------------------------------------
        def tick(self, _sender=None) -> None:
            if self.model.due(jobs.utcnow()):
                self.start_sync()
            self.refresh()

        def start_sync(self, _sender=None, job: str = "sync") -> None:
            if not self.model.begin(job):
                return
            log.info("%s started", job)
            self.refresh()
            threading.Thread(target=self._sync_worker, args=(job, self.settings), daemon=True).start()

        def start_refetch(self, _sender=None) -> None:
            self.start_sync(job="refetch")

        def _sync_worker(self, job: str, settings) -> None:
            outcome = jobs.run_sync(job, settings)
            AppHelper.callAfter(self._sync_done, outcome)

        def _sync_done(self, outcome: RunOutcome) -> None:
            log.info("sync finished: %s %s", outcome.status, outcome.message)
            for note in self.model.finish_sync(outcome, jobs.utcnow()):
                self.notify(note)
            self._save()
            if self._login_after_job:
                self._login_after_job = False
                self.start_login()
            self.refresh()

        def start_login(self, _sender=None) -> None:
            if not self.model.begin("login"):
                return
            log.info("login started (%s)", self.settings.base_url)
            self.refresh()
            threading.Thread(target=self._login_worker, args=(self.settings,), daemon=True).start()

        def _login_worker(self, settings) -> None:
            ok, message = jobs.run_login(settings)
            AppHelper.callAfter(self._login_done, ok, message)

        def _login_done(self, ok: bool, message: str) -> None:
            log.info("login finished: ok=%s %s", ok, message)
            self.model.finish_login(ok, message, jobs.utcnow())
            if self._login_after_job:  # the school changed during this sign-in
                self._login_after_job = False
                self.start_login()
                return
            self.tick()  # a successful sign-in makes a sync due right away

        def open_school_folder(self, _sender=None) -> None:
            if self.model.dest.is_dir():
                open_path(self.model.dest)
            else:
                self.model.note = "Okul klasörü henüz yok; önce senkronize edin."
                self.refresh()

        def open_recent(self, rel_path: str) -> None:
            target = open_target(self.model.dest, rel_path)
            if target is None:
                self.model.note = "Dosya bulunamadı."
                self.refresh()
            else:
                open_path(target)

        def toggle_autostart(self, _sender=None) -> None:
            try:
                if launchagent.is_installed():
                    launchagent.remove()
                else:
                    launchagent.install(jobs.log_file(self.config))
            except OSError as exc:
                log.warning("could not change the login item: %s", exc)
                self.model.note = "Açılışta başlatma ayarı değiştirilemedi."
            self.refresh()

        def _first_run(self, timer) -> None:
            timer.stop()
            self.open_settings()

        def open_settings(self, _sender=None) -> None:
            if self._settings_window is None:
                from blackboard_sync.menubar.settings_window import SettingsWindow

                saved = jobs.saved_settings(self.config)
                values = settings_form.initial_values(saved, self.settings, launchagent.is_installed())
                self._settings_window = SettingsWindow(
                    values,
                    first_run=saved is None,
                    on_submit=self.settings_submitted,
                    on_close=self._settings_closed,
                )
            self._settings_window.show()

        def _settings_closed(self) -> None:
            self._settings_window = None

        def settings_submitted(self, values: settings_form.FormValues, login: bool) -> tuple[str, str] | None:
            """Save the window; returns (error, field) to show instead of closing."""
            try:
                submission = settings_form.submit(values, self.settings)
                save_settings(self.config.data_dir, submission.settings)
            except SettingsError as exc:
                return str(exc), exc.field
            except OSError as exc:
                log.warning("could not save the settings: %s", exc)
                return f"Ayarlar kaydedilemedi: {exc.strerror or exc}", "dest"
            log.info(
                "settings saved: %s, dest %s", submission.settings.base_url, submission.settings.dest
            )
            self.settings = submission.settings
            self.model.apply_settings(submission.settings.dest, submission.school_changed)
            if submission.autostart != launchagent.is_installed():
                self.toggle_autostart()
            self._save()
            if submission.needs_login(login):
                if self.model.busy is None:
                    self.start_login()
                elif self.model.busy != "login" or submission.school_changed:
                    self._login_after_job = True
            self.refresh()
            return None

        def notification_clicked(self, notification) -> None:
            data = notification.data if isinstance(notification.data, dict) else {}
            if data.get("action") == "login":
                self.start_login()
            elif data.get("open"):
                path = Path(data["open"])
                open_path(path if path.exists() else self.model.dest)

        def quit(self, _sender=None) -> None:
            rumps.quit_application()

        # -- drawing -----------------------------------------------------
        def notify(self, note: Notification) -> None:
            try:
                rumps.notification(note.title, None, note.message, data=note.data)
            except RuntimeError:
                # No notification center for this Python (see README); a plain
                # notification still tells the student, without click action.
                script = "display notification %s with title %s" % (
                    _applescript_str(note.message),
                    _applescript_str(note.title),
                )
                subprocess.Popen(["osascript", "-e", script], stdin=subprocess.DEVNULL)

        def refresh(self) -> None:
            self.model.autostart = launchagent.is_installed()
            self._draw_icon(self.model.icon())
            menu = self.model.menu(jobs.utcnow())
            if menu == self._drawn:
                return
            self._drawn = menu
            self.menu.clear()
            items: list = [rumps.MenuItem(line) for line in menu.status_lines]  # no callback: greyed out
            items.append(rumps.separator)
            items.append(rumps.MenuItem(menu.sync_title, callback=self.start_sync if menu.sync_enabled else None))
            items.append(
                rumps.MenuItem(menu.refetch_title, callback=self.start_refetch if menu.refetch_enabled else None)
            )
            items.append(rumps.MenuItem(menu.login_title, callback=self.start_login if menu.login_enabled else None))
            items.append(rumps.MenuItem(T_OPEN_FOLDER, callback=self.open_school_folder))
            recent = rumps.MenuItem(T_RECENT)
            if menu.recent:
                for label, rel_path in menu.recent:
                    recent.add(rumps.MenuItem(label, callback=lambda _s, p=rel_path: self.open_recent(p)))
            else:
                recent.add(rumps.MenuItem(T_RECENT_EMPTY))
            items.append(recent)
            items.append(rumps.separator)
            items.append(rumps.MenuItem(T_SETTINGS, callback=self.open_settings))
            autostart = rumps.MenuItem(T_AUTOSTART, callback=self.toggle_autostart)
            autostart.state = 1 if menu.autostart else 0
            items.append(autostart)
            items.append(rumps.MenuItem(T_QUIT, callback=self.quit))
            self.menu.update(items)

        def _draw_icon(self, icon: Icon) -> None:
            status_item = getattr(getattr(self, "_nsapp", None), "nsstatusitem", None)
            if status_item is None or icon == self._drawn_icon:
                return
            self._drawn_icon = icon
            image = symbol_image(icon)
            if image is None:
                status_item.setImage_(None)
                status_item.setTitle_(FALLBACK_TITLES[icon])
            else:
                status_item.setTitle_("")
                status_item.setImage_(image)

        def _save(self) -> None:
            try:
                jobs.save_model(self.config, self.model)
            except OSError as exc:
                log.warning("could not save menu bar state: %s", exc)

    return MenuBarApp()


def _applescript_str(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="blackboard-sync-menubar",
        description="Menu bar app that syncs Blackboard every hour and notifies about new files.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--detach", action="store_true", help="start in the background and return")
    group.add_argument("--enable-autostart", action="store_true", help="start the app at every login")
    group.add_argument("--disable-autostart", action="store_true", help="stop starting the app at login")
    args = parser.parse_args(argv)
    config = Config.from_env()

    if args.enable_autostart:
        print(f"Installed {launchagent.install(jobs.log_file(config))}; the app now starts at login.")
        return 0
    if args.disable_autostart:
        removed = launchagent.remove()
        print("Removed the login item." if removed else "The login item was not installed.")
        return 0
    if args.detach:
        return jobs.detach(config)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock = jobs.single_instance(config)
    if lock is None:
        print("The Blackboard Sync menu bar app is already running.", file=sys.stderr)
        return 0
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    # A menu bar app: no Dock icon, no app menu.
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    app = build_app(config)
    log.info("menu bar app started (dest %s)", app.settings.dest)
    app.run()
    lock.close()
    return 0
