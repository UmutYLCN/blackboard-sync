"""Uninstall local app data and, optionally, recorded course files.

Course files go through the OS Trash API. No recursive destination deletion:
only safe state paths and their empty parent folders are candidates.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath

from blackboard_sync import runtime, signout
from blackboard_sync.config import Config
from blackboard_sync.errors import AlreadyRunning, BlackboardSyncError
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock
from blackboard_sync.system import try_lock

TITLE = "Blackboard Sync kaldırılsın mı?"
MENU_TITLE = "Uygulamayı kaldır…"
CHECKBOX = "İndirilmiş ders dosyalarını da sil"
MESSAGE = (
    "Uygulama, tüm uygulama kayıtları, günlükler, ayarlar ve giriş verileri kaldırılır. "
    "Bilgisayar açılınca başlatma kaydı da silinir. İndirilmiş ders dosyaları "
    "bu seçeneği işaretlemediğiniz sürece korunur."
)
BUSY = "Kaldırmadan önce senkronizasyonun veya klasör taşıma işleminin tamamlanmasını bekleyin."


def trash(path: Path) -> None:
    if sys.platform == "win32":
        from blackboard_sync.windows.trash import recycle

        recycle(path)
        return
    from send2trash import send2trash

    send2trash(str(path))


def remove_startup() -> None:
    if sys.platform == "win32":
        from blackboard_sync.windows.autostart import set_enabled

        set_enabled(False)
    elif sys.platform == "darwin":
        from blackboard_sync.menubar.launchagent import remove

        remove()


def app_bundle(executable: Path | None = None) -> Path | None:
    """Find the running bundle, never guess an app in /Applications."""
    if executable is None and not runtime.is_frozen():
        return None
    executable = Path(executable or sys.executable).absolute()
    for parent in executable.parents:
        if parent.suffix == ".app" and (parent / "Contents" / "MacOS") in executable.parents:
            return parent
    return None


def remove_app() -> list[str]:
    if not runtime.is_frozen():
        # A source checkout has no installed app bundle/uninstaller.
        return []
    if sys.platform == "darwin":
        bundle = app_bundle()
        if bundle is not None:
            try:
                trash(bundle)
                return []
            except OSError:
                return [f"Uygulama Çöp Sepeti'ne taşınamadı. Finder'da bu uygulamayı elle silin: {bundle}"]
    elif sys.platform == "win32":
        installer = Path(sys.executable).parent / "unins000.exe"
        if installer.is_file():
            try:
                # Inno stops the app, so start it only after all data cleanup.
                subprocess.Popen([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                                 stdin=subprocess.DEVNULL)
                return []
            except OSError:
                pass
        return ["Uygulama kaldırıcısı başlatılamadı. Windows Ayarlar → Uygulamalar bölümünden "
                f"Blackboard Sync'i kaldırın; gerekirse bu klasörü elle silin: {installer.parent}"]
    return ["Uygulama dosyalarını elle kaldırın."]


def _recorded_path(dest: Path, value) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        return None
    rel = PurePosixPath(value)
    if rel.is_absolute() or PureWindowsPath(value).drive or any(p in (".", "..") for p in value.split("/")):
        return None
    path = dest.joinpath(*rel.parts)
    # Refuse symlinks/junctions at any level below the configured destination.
    # resolve() also catches Windows reparse points and paths escaping the root.
    root = dest.resolve()
    for candidate in (path, *path.parents):
        if candidate == dest:
            break
        if candidate.is_symlink() or candidate.resolve() != root / candidate.relative_to(dest):
            return None
    return path


def trash_course_files(config: Config, send_to_trash=trash) -> list[str]:
    state = State.load(config.state_file, backup=False)
    warnings = []
    if state.recovery:
        return ["İndirme kayıtları okunamadı; ders dosyaları güvenlik için korundu."]
    folders: set[Path] = set()
    paths = {entry.get("path") for entry in state.outputs.values() if isinstance(entry, dict)
             and isinstance(entry.get("path"), str)}
    for rel in sorted(paths):
        path = _recorded_path(config.dest, rel)
        if path is None:
            continue
        # The state records files, never permission to remove a directory tree.
        if path.exists() and not path.is_file():
            continue
        parent = path.parent
        while parent != config.dest:
            folders.add(parent)
            parent = parent.parent
        if path.is_file():
            try:
                send_to_trash(path)
            except OSError as exc:
                warnings.append(f"Dosya Çöp Sepeti'ne taşınamadı: {path} ({exc})")
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                send_to_trash(folder)
        except OSError as exc:
            warnings.append(f"Boş klasör Çöp Sepeti'ne taşınamadı: {folder} ({exc})")
    return warnings


@contextmanager
def _app_lock(config: Config, owned: bool):
    """CLI requires the GUI to be closed so it cannot recreate cleaned records."""
    if owned:
        yield
        return
    handle = open(config.data_dir / "menubar.lock", "a+")
    try:
        if not try_lock(handle):
            raise AlreadyRunning("Önce Blackboard Sync'ten çıkın veya menüdeki Uygulamayı kaldır… seçeneğini kullanın.")
        yield
    finally:
        handle.close()


def uninstall(config: Config, delete_course_files: bool = False, *,
              send_to_trash=trash, clear_web=None, startup_cleanup=remove_startup,
              app_cleanup=remove_app, before_cleanup=None, owns_app_lock=False) -> list[str]:
    """Finish cleanup even if one step fails; return actionable warnings.

    Hooks make platform operations testable without touching real user folders.
    GUI callers stop timers and close their lifetime/log handles in before_cleanup,
    which runs only after the shared sync/move lock was acquired.
    """
    data = config.data_dir.resolve()
    dest = config.dest.resolve()
    if data == data.parent or data == Path.home().resolve() or data == dest or data in dest.parents:
        raise BlackboardSyncError("Uygulama veri klasörü indirme klasörünü veya ev klasörünü içeriyor; kaldırma iptal edildi.")
    for name in ("sync.lock", "menubar.lock"):
        if (config.data_dir / name).is_symlink():
            raise BlackboardSyncError("Kilit dosyası bir bağlantı; güvenli kaldırma yapılamadı.")
    warnings: list[str] = []
    try:
        with run_lock(config.lock_file):
            with _app_lock(config, owns_app_lock):
                if before_cleanup:
                    before_cleanup()
                if delete_course_files:
                    try:
                        warnings.extend(trash_course_files(config, send_to_trash))
                    except OSError as exc:
                        warnings.append(f"Ders dosyaları Çöp Sepeti’ne taşınamadı: {exc}")
                try:
                    warnings.extend(signout.sign_out(config, clear_web=clear_web))
                except OSError as exc:
                    warnings.append(f"Giriş verileri temizlenemedi: {exc}")
                try:
                    startup_cleanup()
                except OSError as exc:
                    warnings.append(f"Açılışta başlatma kaydı silinemedi: {exc}")
                # Open lock files cannot be unlinked on Windows. Remove them only
                # after both handles close; everything else is removed under lock.
                try:
                    for path in config.data_dir.iterdir():
                        if path.name not in ("sync.lock", "menubar.lock"):
                            if not signout._remove_tree(path):
                                warnings.append(f"Uygulama verisi silinemedi: {path}")
                except OSError as exc:
                    warnings.append(f"Uygulama veri klasörü temizlenemedi: {config.data_dir} ({exc})")
    except AlreadyRunning as exc:
        if "Another blackboard-sync" in str(exc):
            raise AlreadyRunning(BUSY) from exc
        raise
    for name in ("sync.lock", "menubar.lock"):
        try:
            (config.data_dir / name).unlink(missing_ok=True)
        except OSError as exc:
            warnings.append(f"Kilit dosyası silinemedi: {name} ({exc})")
    try:
        warnings.extend(app_cleanup())
    except OSError as exc:
        warnings.append(f"Uygulama kaldırılamadı; uygulamayı elle silin: {exc}")
    return list(dict.fromkeys(warnings))


def close_file_logs() -> None:
    """Release Windows file handles and prevent handlers reopening deleted logs."""
    loggers = [logging.getLogger(), *(logger for logger in logging.Logger.manager.loggerDict.values()
                                     if isinstance(logger, logging.Logger))]
    for logger in loggers:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
                handler.close()
