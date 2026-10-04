"""What the settings window shows and what saving it means, without any GUI code.

``settings_window.py`` only draws these values and calls ``submit`` when a
button is pressed. The first launch (no ``settings.json`` yet) and the
"Ayarlar…" menu item open the same window.

User-facing strings are Turkish on purpose: the window is read by the student.
"""

from __future__ import annotations

from dataclasses import dataclass

from blackboard_sync.settings import (
    Settings,
    display_path,
    normalize_base_url,
    normalize_dest,
)

T_TITLE_FIRST_RUN = "Blackboard Sync kurulumu"
T_TITLE = "Blackboard Sync ayarları"
T_INTRO_FIRST_RUN = (
    "Ders dosyalarınız her saat bu Mac'e indirilir. Okulunuzun Blackboard adresini ve "
    "dosyaların kaydedileceği klasörü kontrol edin, sonra “Giriş yap” ile Blackboard'a girin."
)
T_URL_LABEL = "Okulunuzun Blackboard adresi"
T_URL_PLACEHOLDER = "https://blackboard.okul.edu.tr"
T_URL_HINT = "Adresi değiştirirseniz yeni okul için tekrar giriş yapmanız gerekir."
T_DEST_LABEL = "Dosyaların kaydedileceği klasör"
T_DEST_HINT = (
    "Klasörü değiştirmek yalnızca bundan sonraki senkronları etkiler; "
    "mevcut dosyalar taşınmaz ve silinmez."
)
T_CHECK_UPDATES = "Güncellemeleri otomatik denetle"
T_CHOOSE_FOLDER = "Seç…"
T_CHOOSE_FOLDER_PROMPT = "Bu klasörü kullan"
T_CHOOSE_FOLDER_MESSAGE = "Ders dosyalarının kaydedileceği klasörü seçin."
T_LOGIN = "Giriş yap"
T_SAVE = "Kaydet"
T_CANCEL = "Vazgeç"


@dataclass
class FormValues:
    """The window's inputs, as text the student can edit."""

    base_url: str
    dest: str
    autostart: bool
    check_updates: bool = True


@dataclass(frozen=True)
class Submission:
    """Validated settings plus what the app has to do after saving them."""

    settings: Settings
    autostart: bool
    school_changed: bool  # the old session belongs to another host: sign in again
    dest_changed: bool  # future syncs go to the new folder; nothing is moved

    def needs_login(self, login_pressed: bool) -> bool:
        return login_pressed or self.school_changed


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
    )
    return Submission(
        settings=settings,
        autostart=values.autostart,
        school_changed=settings.base_url != current.base_url.rstrip("/"),
        dest_changed=settings.dest != current.dest,
    )

