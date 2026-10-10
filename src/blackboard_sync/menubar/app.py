"""The menu bar GUI: a thin rumps layer that draws ``AppModel`` and forwards events.

Decisions (when to sync, what the menu and the main window say, which
notification to post) live in ``model.py`` and ``main_window_model.py``; this
module only owns threads, AppKit objects and ``open``.
"""

from __future__ import annotations

import argparse
import functools
import logging
import subprocess
import sys
import threading
from pathlib import Path

from blackboard_sync import deleted, runtime, update_macos, updater, uninstall
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.menubar import jobs, launchagent, settings_form
from blackboard_sync.menubar.main_window_model import GENERAL, main_status, shows_window_at_launch
from blackboard_sync.menubar.model import (
    DEST_KEEP,
    MOVE_JOB,
    AppModel,
    Icon,
    MenuModel,
    Notification,
    T_UPDATE_WAIT,
    RunOutcome,
    open_target,
)
from blackboard_sync.settings import SettingsError, save_settings
from blackboard_sync.system import sync_root
from blackboard_sync.updater import CheckResult, Release, UpdateError

log = logging.getLogger("blackboard_sync.menubar")

TICK_SECONDS = 30
# SF Symbols per state; idle uses the logo below, with this symbol as a fallback.
# Expired and error are tinted so they stand out.
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
T_UPDATE_READY = "Blackboard Sync {version} indirildi"
# The manual update, where the app cannot replace itself (``update_macos.ManualUpdate``).
T_UPDATE_STEPS = (
    "Açılan pencerede “Blackboard Sync” simgesini “Applications” klasörüne sürükleyin "
    "ve eski sürümün yerine koymak için “Değiştir”i seçin. Bunun için önce "
    "Blackboard Sync'ten çıkmanız gerekir; sonra uygulamayı Applications klasöründen "
    "yeniden açın. Ayarlarınız ve indirdiğiniz ders dosyaları korunur."
)


def forget_menu_items(menu) -> None:
    """Drop the callback registry entries of every item in ``menu`` (submenus too).

    rumps 0.4.0 keeps each item, its NSMenuItem and callback in a class-level dict
    that ``Menu.clear()`` never prunes, so every rebuild would leak the old menu.
    """
    from rumps.rumps import NSApp

    registry = NSApp._ns_to_py_and_callback
    stack = list(menu.values())
    while stack:
        item = stack.pop()
        registry.pop(item._menuitem, None)
        if getattr(item, "_menu", None) is not None:
            stack.extend(item.values())


def symbol_image(icon: Icon):
    from AppKit import NSColor, NSImage, NSImageSymbolConfiguration

    if icon == Icon.IDLE:
        # PyInstaller places bundled data under _MEIPASS; source runs use the repo.
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        assets = root / "assets" / "menubar"
        image = NSImage.alloc().initWithContentsOfFile_(str(assets / "idle.png"))
        if image is not None and image.isValid():
            retina = NSImage.alloc().initWithContentsOfFile_(str(assets / "idle@2x.png"))
            if retina is not None and retina.isValid():
                for representation in retina.representations():
                    representation.setSize_((18, 18))
                    image.addRepresentation_(representation)
            image.setSize_((18, 18))
            image.setAccessibilityDescription_(DESCRIPTIONS[icon])
            image.setTemplate_(True)  # follows the light/dark menu bar
            return image

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


# A second start of the app (from a terminal, or another copy of it) asks the
# running copy with the same data folder to show its main window.
SHOW_WINDOW = "io.github.umutylcn.blackboard-sync.show-window"


def request_window(config: Config) -> None:
    from Foundation import NSDistributedNotificationCenter

    NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_deliverImmediately_(
        SHOW_WINDOW, str(config.data_dir), None, True
    )


def set_dock_icon(visible: bool) -> None:
    """Regular (Dock icon, app menu) while the main window is open; a menu bar accessory otherwise."""
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSApplicationActivationPolicyRegular,
    )

    policy = NSApplicationActivationPolicyRegular if visible else NSApplicationActivationPolicyAccessory
    application = NSApplication.sharedApplication()
    if application.activationPolicy() != policy and not application.setActivationPolicy_(policy):
        log.warning("could not switch the Dock icon %s", "on" if visible else "off")


def app_icon_image():
    """The app's icon for the Dock and the window; a source run would show Python's."""
    from AppKit import NSImage

    if runtime.is_frozen():
        return None  # the bundle's own icon
    path = Path(__file__).resolve().parents[3] / "assets" / "icon" / "app.icns"
    image = NSImage.alloc().initWithContentsOfFile_(str(path))
    return image if image is not None and image.isValid() else None


def install_reopen_handler(callback) -> None:
    """Call ``callback`` when the running app is opened again (Finder, Launchpad, the Dock).

    rumps owns the application delegate; the reopen method is added to its class
    so the status item, notification and wake handling stay rumps' own.
    """
    import objc
    from rumps.rumps import NSApp as Delegate

    def reopen(self, _app, _visible):
        callback()
        return False  # handled: AppKit must not do its own reopen

    objc.classAddMethods(Delegate, [objc.selector(
        reopen, selector=b"applicationShouldHandleReopen:hasVisibleWindows:", signature=b"Z@:@Z",
    )])


def build_main_menu():
    """The app menu, Düzen and Pencere: the menu bar while the main window is open.

    The menu bar icon's own menu is separate and unchanged.
    """
    from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagOption, NSEventModifierFlagShift, NSMenu, NSMenuItem

    def menu(title, items):
        submenu = NSMenu.alloc().initWithTitle_(title)
        for entry in items:
            if entry is None:
                submenu.addItem_(NSMenuItem.separatorItem())
                continue
            text, action, key, *flags = entry
            item = submenu.addItemWithTitle_action_keyEquivalent_(text, action, key)
            if flags:
                item.setKeyEquivalentModifierMask_(flags[0])
        holder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        holder.setSubmenu_(submenu)
        return holder, submenu

    main = NSMenu.alloc().initWithTitle_("")
    app_item, _ = menu("Blackboard Sync", [
        ("Blackboard Sync'i gizle", "hide:", "h"),
        ("Diğerlerini gizle", "hideOtherApplications:", "h", NSEventModifierFlagCommand | NSEventModifierFlagOption),
        ("Tümünü göster", "unhideAllApplications:", ""),
        None,
        ("Blackboard Sync'ten çık", "terminate:", "q"),
    ])
    edit_item, _ = menu("Düzen", [
        ("Geri al", "undo:", "z"),
        ("Yinele", "redo:", "z", NSEventModifierFlagCommand | NSEventModifierFlagShift),
        None,
        ("Kes", "cut:", "x"),
        ("Kopyala", "copy:", "c"),
        ("Yapıştır", "paste:", "v"),
        ("Tümünü seç", "selectAll:", "a"),
    ])
    window_item, window_menu = menu("Pencere", [
        ("Küçült", "performMiniaturize:", "m"),
        ("Kapat", "performClose:", "w"),
    ])
    for item in (app_item, edit_item, window_item):
        main.addItem_(item)
    return main, window_menu


def open_path(path: Path) -> None:
    subprocess.Popen(["open", str(path)], stdin=subprocess.DEVNULL)


def open_url(url: str) -> None:
    subprocess.Popen(["open", url], stdin=subprocess.DEVNULL)


@functools.cache
def _receivers():
    """The Objective-C classes that forward to the app (defined once per process)."""
    from AppKit import NSObject

    class MenuDelegate(NSObject):
        def menuNeedsUpdate_(self, menu):
            self.owner.refresh()

    class WindowRequests(NSObject):
        def showWindow_(self, _notification):
            self.owner.show_window()

    return MenuDelegate, WindowRequests


def build_app(config: Config, show_window: bool = False):
    import rumps
    from AppKit import NSApplication, NSColor, NSAttributedString, NSForegroundColorAttributeName
    from Foundation import NSDistributedNotificationCenter

    MenuDelegate, WindowRequests = _receivers()

    from PyObjCTools import AppHelper

    class MenuBarApp(rumps.App):
        def __init__(self):
            super().__init__("Blackboard Sync", title=FALLBACK_TITLES[Icon.IDLE], quit_button=None)
            self.config = config
            self.settings = jobs.effective_settings(config)
            self.model = jobs.load_model(config, jobs.utcnow(), launchagent.is_installed())
            self._drawn: MenuModel | None = None
            self._drawn_icon: Icon | None = None
            self._menu_delegate = MenuDelegate.alloc().init()
            self._menu_delegate.owner = self
            self.menu._menu.setDelegate_(self._menu_delegate)
            self._window = None  # the main window, built when first shown
            self._uninstalling = False
            self._login_after_job = False  # asked for while another job was running
            self._timer = rumps.Timer(self.tick, TICK_SECONDS)
            self._timer.start()
            # Notifications need the running app: say how the update it quit for went.
            self._installed_timer = rumps.Timer(self._report_installed, 1)
            self._installed_timer.start()
            if show_window:
                # Opened by the student (or set up for the first time): show the
                # main window once the app is running.
                self._first_run_timer = rumps.Timer(self._first_run, 1)
                self._first_run_timer.start()
            rumps.events.on_notification.register(self.notification_clicked)
            rumps.events.on_wake.register(self.tick)
            install_reopen_handler(self.show_window)
            self._requests = WindowRequests.alloc().init()
            self._requests.owner = self
            NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
                self._requests, "showWindow:", SHOW_WINDOW, str(config.data_dir))
            application = NSApplication.sharedApplication()
            main_menu, window_menu = build_main_menu()
            application.setMainMenu_(main_menu)
            application.setWindowsMenu_(window_menu)
            icon = app_icon_image()
            if icon is not None:
                application.setApplicationIconImage_(icon)

        # -- events ------------------------------------------------------
        def tick(self, _sender=None) -> None:
            if self._uninstalling:
                return
            self.start_next()
            if self.model.update_due(jobs.utcnow()):
                self.start_update_check(manual=False)
            self.refresh()

        def start_next(self) -> None:
            """A job a folder change asked for goes first, then the scheduled sync."""
            jobs.refresh_session(self.config, self.model, self.settings)  # a refetch waits for it
            job = self.model.pending_job()
            if job == MOVE_JOB:
                self.start_move()
            elif job is not None:
                self.start_sync(job=job)
            elif self.model.due(jobs.utcnow()):
                self.start_sync()

        def start_sync(self, _sender=None, job: str = "sync", refetch_keys=None) -> None:
            if not self.model.begin(job):
                return
            log.info("%s started", job)
            self.refresh()
            threading.Thread(target=self._sync_worker, args=(job, self.settings, refetch_keys, self.model.past_term), daemon=True).start()

        def start_refetch(self, _sender=None) -> None:
            self.start_sync(job="refetch")

        def _sync_worker(self, job: str, settings, refetch_keys=None, term_name: str = "") -> None:
            outcome = jobs.run_sync_guarded(job, settings, refetch_keys=refetch_keys, term_name=term_name)
            AppHelper.callAfter(self._sync_done, outcome)

        def start_past_terms(self) -> None:
            """Look up the past terms for the list in Genel, in the background."""
            if not self.model.begin("past_terms"):
                return
            threading.Thread(target=self._past_terms_worker, args=(self.settings,), daemon=True).start()

        def _past_terms_worker(self, settings) -> None:
            AppHelper.callAfter(self._past_terms_done, *jobs.run_past_terms(settings))

        def _past_terms_done(self, names, outcome) -> None:
            self.model.finish_past_terms(names, outcome)
            self.start_next()  # a move the window saved meanwhile goes first
            if self._login_after_job and self.model.busy is None:
                self._login_after_job = False
                self.start_login()
            self.refresh()

        def download_past_term(self, name: str) -> bool:
            if not self.model.select_past_term(name):
                return False
            self.start_sync(job="past_term")
            return True

        def _sync_done(self, outcome: RunOutcome) -> None:
            log.info("sync finished: %s %s", outcome.status, outcome.message)
            for note in self.model.finish_sync(outcome, jobs.utcnow()):
                self.notify(note)
            self._save()
            if self._login_after_job:
                self._login_after_job = False
                self.start_login()
            self.refresh()

        def start_move(self) -> None:
            old, new = self.model.move_from, self.model.dest
            if old is None or not self.model.begin(MOVE_JOB):
                return
            log.info("moving the files from %s to %s", old, new)
            self.refresh()
            threading.Thread(target=self._move_worker, args=(old, new), daemon=True).start()

        def _move_worker(self, old: Path, new: Path) -> None:
            result = jobs.run_move_guarded(self.config, old, new)
            AppHelper.callAfter(self._move_done, result)

        def _move_done(self, result) -> None:
            log.info("move finished: %s, %d moved, %d kept", result.status, result.moved, len(result.kept))
            for note in self.model.finish_move(result.status, result.moved, len(result.kept), result.message):
                self.notify(note)
            self._save()
            # No tick here: a move that found the folders locked waits for the timer.
            if self._login_after_job:
                self._login_after_job = False
                self.start_login()
            self.refresh()

        def start_login(self, _sender=None) -> None:
            if not self.model.begin("login"):
                return
            self.model.login_method = jobs.login_method()
            log.info("login started (%s, %s)", self.settings.base_url, self.model.login_method)
            self.refresh()
            threading.Thread(target=self._login_worker, args=(self.settings,), daemon=True).start()

        def _login_worker(self, settings) -> None:
            ok, message = jobs.run_login_guarded(settings)
            AppHelper.callAfter(self._login_done, ok, message)

        def _login_done(self, ok: bool, message: str) -> None:
            log.info("login finished: ok=%s %s", ok, message)
            self.model.finish_login(ok, message, jobs.utcnow())
            if self._login_after_job:  # the school changed during this sign-in
                self._login_after_job = False
                self.start_login()
                return
            self.tick()  # a successful sign-in makes a sync due right away

        # -- updates -----------------------------------------------------
        def start_update_check(self, _sender=None, manual: bool = True) -> None:
            if not self.model.updates.begin("check"):
                return
            self.refresh()
            threading.Thread(target=self._update_check_worker, args=(manual,), daemon=True).start()

        def _update_check_worker(self, manual: bool) -> None:
            try:
                result = updater.check()
            except Exception:  # check() handles network errors; never leave the row stuck
                log.exception("update check failed")
                result = CheckResult("unknown")
            AppHelper.callAfter(self._update_checked, result, manual)

        def _update_checked(self, result: CheckResult, manual: bool) -> None:
            log.info("update check: %s %s", result.status, result.release.version if result.release else "")
            for note in self.model.updates.finish_check(result, jobs.utcnow(), manual):
                self.notify(note)
            self._save()
            self.refresh()

        def start_update(self, _sender=None) -> None:
            release = self.model.updates.available
            if release is None:
                self.start_update_check()
                return
            if not runtime.is_frozen():
                # Run from a checkout: there is no app bundle to replace.
                open_url(release.page_url)
                return
            if self.model.updates.busy is not None:
                return
            if self.model.busy is not None:
                # The app quits to install; a running sync or move would be cut off.
                self.notify(Notification("Güncelleme şimdi yüklenemiyor", T_UPDATE_WAIT, {}))
                return
            if not self.model.updates.begin("download"):
                return
            self.refresh()
            threading.Thread(target=self._update_worker, args=(release,), daemon=True).start()

        def _update_worker(self, release: Release) -> None:
            path, manual, error = None, "", ""
            try:
                try:
                    target = update_macos.find_target(uninstall.app_bundle())
                except update_macos.ManualUpdate as exc:
                    manual = str(exc)
                    log.info("updating by hand: %s", manual)
                    path = updater.download(release, updater.download_dir())
                else:
                    update_macos.install(release, target, self.config.lock_file, jobs.log_file(self.config))
            except UpdateError as exc:
                error = str(exc)
            except OSError as exc:
                error = f"Güncelleme kaydedilemedi: {exc.strerror or exc}"
            except Exception:  # keep the menu usable whatever went wrong
                log.exception("update failed")
                error = "Güncelleme yüklenemedi."
            AppHelper.callAfter(self._update_finished, release, path, manual, error)

        def _update_finished(self, release: Release, path: Path | None, manual: str, error: str) -> None:
            log.info("update: %s %s %s", path, manual, error)
            for note in self.model.updates.finish_download(error):
                self.notify(note)
            if error:
                self.refresh()
                return
            if path is None:
                # Staged and verified; the helper swaps the app in once this process exits.
                self.model.updates.installing = release.version
                self._save()
                self.quit()
                return
            self.refresh()
            updater.open_disk_image(path)
            if rumps.alert(T_UPDATE_READY.format(version=release.version), f"{manual}\n\n{T_UPDATE_STEPS}",
                           ok="Blackboard Sync'ten çık", cancel="Sonra") == 1:
                self.quit()

        def _report_installed(self, timer) -> None:
            timer.stop()
            notes = self.model.updates.finish_install()
            for note in notes:
                self.notify(note)
            if notes:
                self._save()

        def open_school_folder(self, _sender=None) -> None:
            if self.model.root.is_dir():
                open_path(self.model.root)
            else:
                self.model.note = f"{self.model.root.name or self.model.root} klasörü henüz yok; önce senkronize edin."
                self.refresh()

        def open_recent(self, rel_path: str) -> None:
            target = open_target(self.model.root, rel_path)
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
            self.show_window()

        def open_settings(self, _sender=None) -> None:
            """"Ayarlar…" in the menu: the main window on Genel."""
            self.show_window(GENERAL)

        def form_values(self) -> settings_form.FormValues:
            """What the Genel form shows when nothing is edited: the saved settings."""
            saved = jobs.saved_settings(self.config)
            return settings_form.initial_values(saved, self.settings, launchagent.is_installed())

        @property
        def window_open(self) -> bool:
            return self._window is not None and self._window.state.open

        def past_terms_wanted(self) -> bool:
            """Genel is in view and its past-term list still has to be looked up."""
            return (self.window_open and self._window.section == GENERAL and not self._uninstalling
                    and self.model.past_terms_due())

        def show_window(self, section: str | None = None) -> None:
            """Open the main window (or bring it forward); the Dock icon comes with it."""
            if self._uninstalling:
                return
            if self._window is None:
                from blackboard_sync.menubar.main_window import MainWindow

                self._window = MainWindow(
                    self.form_values(),
                    main_status(self.model, jobs.utcnow()),
                    on_submit=self.settings_submitted,
                    on_action=self.window_action,
                    on_close=self._window_closed,
                    on_values=self.form_values,
                    on_open=self.open_recent,
                    on_missing=lambda: deleted.load_missing(self.config, self.settings.dest),
                    on_deleted_action=self.deleted_action,
                    on_past_term=self.download_past_term,
                    on_section=lambda _section: self.refresh(),
                )
            if not self.window_open:
                self.model.reload_past_terms()
            log.info("showing the main window")
            set_dock_icon(True)
            self._window.show(section)
            self.refresh()  # on Genel, starts looking up the past terms

        def deleted_action(self, action, keys):
            if self._uninstalling or self.model.busy is not None or self.model.updates.busy == "download":
                return settings_form.T_BUSY
            try:
                if action == "dismiss":
                    deleted.dismiss_missing(self.config, self.settings.dest, keys)
                elif keys:
                    self.start_sync(job="refetch", refetch_keys=keys)
            except Exception as exc:
                log.warning("Deleted-file action failed: %s", exc)
                return "İşlem tamamlanamadı; çalışan senkron varsa bitmesini bekleyin."
            return None

        def window_action(self, action: str) -> None:
            """A button in the main window that acts right away instead of saving."""
            {
                "sync": self.start_sync, "folder": self.open_school_folder, "login": self.start_login,
                "logout": self.logout, "refetch": self.start_refetch,
                "check_updates": self.start_update_check, "update": self.start_update,
                "uninstall": self.start_uninstall,
            }[action]()

        def _window_closed(self) -> None:
            """Only the window went: the menu bar icon, timers and jobs go on; the Dock icon leaves."""
            log.info("main window closed; the app keeps running in the menu bar")
            set_dock_icon(False)

        def settings_submitted(self, values: settings_form.FormValues, login: bool) -> tuple[str, str] | None:
            """Save the Genel form; returns (error, field) to show, None once saved."""
            try:
                submission = settings_form.submit(values, self.settings)
            except SettingsError as exc:
                return str(exc), exc.field
            choice = DEST_KEEP
            files = jobs.synced_file_count(self.config, self.settings.dest) if submission.dest_changed else 0
            if files:
                # A running sync still writes into the old folder.
                if self.model.busy is not None:
                    return settings_form.T_BUSY, "dest"
                choice = self.ask_dest_choice(self.settings.dest, submission.settings.dest, files)
                if choice is None:
                    return settings_form.T_DEST_NOT_CHANGED, "dest"
            try:
                save_settings(self.config.data_dir, submission.settings)
            except OSError as exc:
                log.warning("could not save the settings: %s", exc)
                return f"Ayarlar kaydedilemedi: {exc.strerror or exc}", "dest"
            log.info(
                "settings saved: %s, dest %s", submission.settings.base_url, submission.settings.dest
            )
            self.settings = submission.settings
            self.model.apply_settings(
                submission.settings.dest,
                submission.school_changed,
                submission.settings.check_updates,
                submission.settings.sync_interval_minutes,
                dest_choice=choice,
            )
            if submission.autostart != launchagent.is_installed():
                self.toggle_autostart()
            self._save()
            self.start_next()  # a move goes before signing in to a new school
            if submission.needs_login(login):
                if self.model.busy is None:
                    self.start_login()
                elif self.model.busy != "login" or submission.school_changed:
                    self._login_after_job = True
            self.refresh()
            return None

        def ask_dest_choice(self, old: Path, new: Path, files: int) -> str | None:
            from blackboard_sync.menubar.main_window import ask_dest_choice

            return ask_dest_choice(old, new, files)

        def notification_clicked(self, notification) -> None:
            if self._uninstalling:
                return
            data = notification.data if isinstance(notification.data, dict) else {}
            if data.get("action") == "login":
                self.start_login()
            elif data.get("action") == "update":
                self.start_update()
            elif data.get("open"):
                path = Path(data["open"])
                open_path(path if path.exists() else self.model.root)

        def start_uninstall(self, _sender=None) -> None:
            from blackboard_sync.menubar.main_window import ask_uninstall

            if self.model.busy or self.model.updates.busy:
                rumps.alert("Blackboard Sync", uninstall.BUSY)
                return
            self._uninstalling = True  # modal dialogs also run timers/wake events
            self._timer.stop()
            choice = ask_uninstall(sync_root(self.settings.dest))
            if choice is None:
                self._uninstalling = False
                self._timer.start()
                return
            if self.window_open:
                self._window.close()
            try:
                self.config.dest = self.settings.dest
                warnings = uninstall.uninstall(
                    self.config, choice, before_cleanup=self._prepare_uninstall,
                    owns_app_lock=True, app_cleanup=lambda: [],
                )
            except (BlackboardSyncError, OSError) as exc:
                rumps.alert("Blackboard Sync", str(exc))
                self._uninstalling = False
                self._timer.start()
                return
            if warnings:
                rumps.alert("Blackboard Sync", "\n\n".join(warnings))
            warnings = uninstall.remove_app()
            if warnings:
                rumps.alert("Blackboard Sync", "\n\n".join(warnings))
            self.quit()

        def _prepare_uninstall(self) -> None:
            lock = getattr(self, "_lifetime_lock", None)
            if lock is not None:
                lock.close()
            uninstall.close_file_logs()

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
            jobs.refresh_session(self.config, self.model, self.settings)
            self.model.autostart = launchagent.is_installed()
            if self.past_terms_wanted():
                self.start_past_terms()
            self._draw_icon(self.model.icon())
            if self.window_open:
                self._window.update_status(main_status(self.model, jobs.utcnow()))
            menu = self.model.menu(jobs.utcnow())
            if menu == self._drawn:
                return
            self._drawn = menu
            forget_menu_items(self.menu)
            self.menu.clear()
            def render(entry):
                if not entry.title:
                    return rumps.separator
                actions = {
                    "sync": self.start_sync, "login": self.start_login,
                    "folder": self.open_school_folder, "settings": self.open_settings,
                    "quit": self.quit, "open": lambda _s: self.open_recent(entry.value),
                    "update": self.start_update,
                }
                item = rumps.MenuItem(entry.title, callback=actions.get(entry.action) if entry.enabled else None)
                item.state = int(entry.checked)
                if entry.warning:
                    item._menuitem.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(
                        entry.title, {NSForegroundColorAttributeName: NSColor.systemRedColor()}
                    ))
                for child in entry.children:
                    item.add(render(child))
                return item
            self.menu.update([render(entry) for entry in menu.entries])

        def logout(self, _sender=None) -> None:
            if self.model.busy is not None:
                return
            if rumps.alert("Hesaptan çıkış yapılsın mı?",
                           "Tüm giriş verileri silinir; yeniden giriş yaparken okul bilgilerinizi "
                           "tekrar girmeniz gerekir. İndirilen dosyalarınız korunacak.",
                           ok="Çıkış yap", cancel="Vazgeç") != 1:
                return
            try:
                warnings = jobs.logout(self.config)
                if warnings:
                    self.model.note = warnings[0]
            except OSError:
                self.model.note = "Hesaptan çıkış yapılamadı."
            self.refresh()

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
    # The login item starts the app quietly: menu bar icon only, no window.
    group.add_argument("--background", action="store_true", help="start without opening the main window")
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
        if not args.background:
            log.info("already running; asking it to show its window")
            request_window(config)
        return 0
    # Refresh older login items (now started with --background) without enabling
    # autostart or restarting launchd.
    if launchagent.is_installed():
        try:
            launchagent.install(jobs.log_file(config))
        except OSError as exc:
            log.warning("could not refresh the login item: %s", exc)
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    # A menu bar app: no Dock icon, no app menu until the main window opens.
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    show_window = shows_window_at_launch(args.background, jobs.saved_settings(config) is not None)
    app = build_app(config, show_window=show_window)
    app._lifetime_lock = lock
    log.info("menu bar app started (dest %s, window %s)", app.settings.dest, show_window)
    app.run()
    lock.close()
    return 0
