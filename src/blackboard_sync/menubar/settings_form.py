"""What the settings window shows and what saving it means, without any GUI code.

The Genel tab has four sections: Hesap (school address, who is signed in, sign
in or out), Klasör (destination), Genel (start at
login, sync interval) and Güncellemeler (automatic checks, check now, version). Silinenler lists
missing outputs for selective recovery or permanent dismissal. The GUI
layers (``settings_window.py`` on macOS, ``windows/settings_window.py``) only
draw ``FormValues`` and ``WindowStatus`` and report which button was pressed.
The first launch (no ``settings.json`` yet) and the "Ayarlar…" menu item open
the same window.

User-facing strings are Turkish on purpose: the window is read by the student.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blackboard_sync import __version__
from blackboard_sync.deleted import T_DOWNLOAD
from blackboard_sync.menubar.model import (
    DEST_KEEP,
    DEST_MOVE,
    DEST_REFETCH,
    T_CHECK_NOW,
    T_LOGGING_IN,
    T_LOGIN,
    T_LOGOUT,
    T_REFETCHING,
    T_SYNC_NOW,
    AppModel,
    login_waiting_line,
)
from blackboard_sync.settings import (
    SYNC_INTERVAL_CHOICES,
    Settings,
    display_path,
    normalize_base_url,
    normalize_dest,
    normalize_sync_interval,
)
from blackboard_sync.system import sync_root

T_TITLE_FIRST_RUN = "Blackboard Sync kurulumu"
T_TITLE = "Blackboard Sync ayarları"
T_INTERVAL_LABEL = "Otomatik senkron"
# (minutes, menu text); 0 means only by hand. Order is the order in the window.
INTERVAL_OPTIONS = (
    (30, "Her 30 dakikada"),
    (60, "Her saat"),
    (180, "Her 3 saatte"),
    (0, "Yalnızca elle"),
)
assert tuple(minutes for minutes, _ in INTERVAL_OPTIONS) == SYNC_INTERVAL_CHOICES
_INTRO_WHEN = {
    30: "her 30 dakikada bir",
    60: "her saat",
    180: "her 3 saatte bir",
}


def interval_title(minutes: int) -> str:
    return dict(INTERVAL_OPTIONS)[normalize_sync_interval(minutes)]


def intro_first_run(device: str, sync_interval_minutes: int = 60) -> str:
    """The first-run intro; ``device`` is "bu Mac'e" or "bu bilgisayara"."""
    when = _INTRO_WHEN.get(normalize_sync_interval(sync_interval_minutes))
    start = (
        f"Ders dosyalarınız {when} {device} indirilir."
        if when
        else f"Ders dosyalarınız “{T_SYNC_NOW}” dediğinizde {device} indirilir."
    )
    return (
        f"{start} Okulunuzun Blackboard adresini ve dosyaların kaydedileceği klasörü "
        "kontrol edin, sonra “Giriş yap” ile Blackboard'a girin."
    )


T_INTRO_FIRST_RUN = intro_first_run("bu Mac'e")
T_SECTION_ACCOUNT = "Hesap"
T_SECTION_FOLDER = "Klasör"
T_SECTION_GENERAL = "Genel"
T_SECTION_UPDATES = "Güncellemeler"
T_URL_LABEL = "Okulunuzun Blackboard adresi"
T_URL_PLACEHOLDER = "https://blackboard.okul.edu.tr"
T_URL_HINT = "Adresi değiştirirseniz yeni okul için tekrar giriş yapmanız gerekir."
T_DEST_LABEL = "Dosyaların kaydedileceği klasör"
# Under the folder field: what ``system.sync_root`` does with the chosen folder.
T_DEST_ROOT_NOTE = "Dosyalar seçtiğiniz klasörün içindeki University klasörüne kaydedilir."
T_DEST_HINT = (
    f"{T_DEST_ROOT_NOTE} "
    "Klasörü değiştirirseniz indirilmiş dosyaları yeni klasöre taşımayı ya da "
    "yeniden indirmeyi seçebilirsiniz."
)
T_AUTOSTART = "Bilgisayar açılınca başlat"
T_CHECK_UPDATES = "Güncellemeleri otomatik denetle"
T_CHOOSE_FOLDER = "Seç…"
T_CHOOSE_FOLDER_PROMPT = "Bu klasörü kullan"
T_CHOOSE_FOLDER_MESSAGE = "Ders dosyalarının kaydedileceği klasörü seçin."
T_SAVE = "Kaydet"
T_CANCEL = "Vazgeç"
T_BUSY = "Önce çalışan işlemin tamamlanmasını bekleyin."
T_DEST_NOT_CHANGED = "Klasör değiştirilmedi."

# Asked when the folder changes and the old one holds downloaded files.
T_DEST_CHANGE_TITLE = "İndirilen dosyalar ne olsun?"
T_MOVE = "Taşı"
T_REDOWNLOAD = "Yeniden indir"
T_NEW_ONLY = "Sadece yeni dosyalar"
# (choice, button); the first one is the default.
DEST_CHOICES = ((DEST_MOVE, T_MOVE), (DEST_REFETCH, T_REDOWNLOAD), (DEST_KEEP, T_NEW_ONLY))


def dest_change_message(old: Path, new: Path, files: int) -> str:
    """The question under ``T_DEST_CHANGE_TITLE``; ``files`` were synced into ``old``.

    ``old`` and ``new`` are the chosen folders; the text names their University folders.
    """
    old, new = sync_root(old), sync_root(new)
    return (
        f"“{display_path(old)}” klasöründe Blackboard'dan indirilmiş {files} dosya var.\n\n"
        f"{T_MOVE}: dosyalar “{display_path(new)}” klasörüne taşınır, yeniden indirilmez. "
        "Kendi eklediğiniz dosyalar eski klasörde kalır.\n"
        f"{T_REDOWNLOAD}: dosyalar yeni klasöre yeniden indirilir; eski klasöre dokunulmaz.\n"
        f"{T_NEW_ONLY}: dosyalar eski klasörde kalır; yeni klasöre yalnızca bundan sonra "
        "eklenenler indirilir."
    )


@dataclass
class FormValues:
    """The window's inputs, as text the student can edit."""

    base_url: str
    dest: str
    autostart: bool
    check_updates: bool = True
    sync_interval_minutes: int = 60  # 0: only by hand


@dataclass(frozen=True)
class Submission:
    """Validated settings plus what the app has to do after saving them."""

    settings: Settings
    autostart: bool
    school_changed: bool  # the old session belongs to another host: sign in again
    # Future syncs go to another University folder; see ``DEST_CHOICES``. Choosing
    # ``~/X/University`` instead of ``~/X`` (or back) changes nothing.
    dest_changed: bool
    interval_changed: bool = False  # the next automatic run is recomputed

    def needs_login(self, login_pressed: bool) -> bool:
        return login_pressed or self.school_changed


@dataclass(frozen=True)
class WindowStatus:
    """The live part of the window: who is signed in and which buttons work now.

    Buttons that need the app's single job slot (sign in, sign out, bring back
    deleted files) are disabled while a sync or a sign-in runs.
    """

    account: str
    account_warning: bool
    account_title: str
    account_action: str  # "login" (saves the form first) | "logout"
    account_enabled: bool
    refetch_title: str
    refetch_enabled: bool
    version: str
    update_title: str
    update_action: str  # "check_updates" | "update"
    update_enabled: bool
    deleted_message: str = ""


def window_status(model: AppModel) -> WindowStatus:
    idle = model.busy is None
    name, expired = model.account()
    if model.busy == "login":
        account, title, action = login_waiting_line(model.login_method), T_LOGGING_IN, "login"
    elif name is not None:
        account, title, action = f"Giriş yapıldı: {name}", T_LOGOUT, "logout"
    elif expired:
        account, title, action = "Oturum sona erdi; tekrar giriş yapın.", T_LOGIN, "login"
    else:
        account, title, action = "Henüz giriş yapılmadı.", T_LOGIN, "login"
    updates = model.updates
    if updates.busy == "check":
        update_title, update_action = "Denetleniyor…", "check_updates"
    elif updates.busy == "download":
        update_title, update_action = "İndiriliyor…", "update"
    elif updates.available is not None:
        update_title, update_action = f"{updates.available.version} sürümüne güncelle", "update"
    else:
        update_title, update_action = T_CHECK_NOW, "check_updates"
    return WindowStatus(
        account=account,
        account_warning=expired and model.busy != "login",
        account_title=title,
        account_action=action,
        account_enabled=idle,
        refetch_title=T_REFETCHING if model.busy == "refetch" else T_DOWNLOAD,
        # Before the first save there is no folder to bring files back to.
        refetch_enabled=idle and model.configured and model.updates.busy != "download",
        version=f"Sürüm {__version__}",
        update_title=update_title,
        update_action=update_action,
        update_enabled=updates.busy is None,
        deleted_message=model.activity() or model.note or (
            (model.last.message or "Son işlem tamamlandı.") if model.last and model.last.status == "ok"
            else "Oturum sona erdi; tekrar giriş yapın." if model.last and model.last.status == "login_required"
            else "Başka bir senkron çalışıyor; bitmesini bekleyin." if model.last and model.last.status == "locked"
            else "İşlem tamamlanamadı. Ayrıntılar uygulama menüsünde." if model.last else ""
        ),
    )


def initial_values(saved: Settings | None, current: Settings, autostart: bool) -> FormValues:
    """Prefill the window with the saved settings, else what the app uses now.

    On the first launch "Bilgisayar açılınca başlat" is ticked: the app is
    meant to run in the background without the student thinking about it.
    """
    shown = saved or current
    return FormValues(
        base_url=shown.base_url,
        dest=display_path(shown.dest),
        autostart=autostart or saved is None,
        check_updates=shown.check_updates,
        sync_interval_minutes=shown.sync_interval_minutes,
    )


def submit(values: FormValues, current: Settings) -> Submission:
    """Validate the inputs; raises ``SettingsError`` with a Turkish message.

    ``current`` is what the app syncs with right now (the saved settings, or
    the defaults before the first save).
    """
    settings = Settings(
        base_url=normalize_base_url(values.base_url),
        dest=normalize_dest(values.dest),
        check_updates=values.check_updates,
        sync_interval_minutes=normalize_sync_interval(values.sync_interval_minutes),
    )
    return Submission(
        settings=settings,
        autostart=values.autostart,
        school_changed=settings.base_url != current.base_url.rstrip("/"),
        dest_changed=sync_root(settings.dest) != sync_root(current.dest),
        interval_changed=settings.sync_interval_minutes != current.sync_interval_minutes,
    )

