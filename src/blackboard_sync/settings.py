"""Settings chosen in the menu bar app's settings window, saved as ``settings.json``.

The file lives in the data directory beside ``state.json``. Both the menu bar
app and the command line read it, so a student never needs command-line flags:
the window decides which Blackboard to talk to and where files go.

Validation messages are Turkish on purpose: the settings window shows them to
the student.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from blackboard_sync.session import write_private_json
from blackboard_sync.system import make_private_dir

SETTINGS_FILE = "settings.json"


class SettingsError(ValueError):
    """An invalid value in the settings window; ``field`` names the input."""

    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class Settings:
    base_url: str
    dest: Path
    # "Güncellemeleri otomatik denetle": look for a new app version once a day.
    check_updates: bool = True

    def to_dict(self) -> dict:
        return {"base_url": self.base_url, "dest": str(self.dest), "check_updates": self.check_updates}

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        return cls(
            base_url=normalize_base_url(data["base_url"]),
            dest=normalize_dest(data["dest"]),
            check_updates=data.get("check_updates", True) is not False,
        )


def settings_path(data_dir: Path) -> Path:
    return data_dir / SETTINGS_FILE


def load_settings(data_dir: Path) -> Settings | None:
    """The saved settings; None when they were never saved or cannot be read."""
    try:
        data = json.loads(settings_path(data_dir).read_text(encoding="utf-8"))
        return Settings.from_dict(data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def save_settings(data_dir: Path, settings: Settings) -> Path:
    make_private_dir(data_dir)
    path = settings_path(data_dir)
    write_private_json(path, settings.to_dict())
    return path


def normalize_base_url(text: str) -> str:
    """Reduce what the student typed or pasted to ``https://host[:port]``.

    Blackboard Learn always lives at the root of its host, so a pasted course
    link such as ``https://blackboard.x.edu.tr/ultra/course`` keeps only the
    host. A missing scheme means https; anything else but https is refused.
    """
    text = (text or "").strip()
    if not text:
        raise SettingsError("Okulunuzun Blackboard adresini yazın.", "base_url")
    if "://" not in text:
        text = "https://" + text
    example = "Geçerli bir adres yazın, örneğin https://blackboard.okul.edu.tr"
    try:
        parts = urlsplit(text)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise SettingsError(example, "base_url") from None
    if parts.scheme.lower() != "https":
        raise SettingsError("Adres https:// ile başlamalı.", "base_url")
    if (
        not host
        or "." not in host.strip(".")
        or parts.username is not None
        or any(c.isspace() for c in text)
    ):
        raise SettingsError(example, "base_url")
    return f"https://{host}" + (f":{port}" if port else "")


def normalize_dest(text: str | os.PathLike) -> Path:
    """An absolute folder path; ``~`` is expanded. The folder may not exist yet."""
    text = str(text or "").strip()
    if not text:
        raise SettingsError("Dosyaların kaydedileceği klasörü seçin.", "dest")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise SettingsError("Klasörü tam yoluyla yazın, örneğin ~/Documents/Okul", "dest")
    path = Path(os.path.normpath(path))
    if path.exists() and not path.is_dir():
        raise SettingsError("Bu yol bir klasör değil.", "dest")
    return path


def display_path(path: Path, home: Path | None = None) -> str:
    """``/Users/me/Documents/Okul`` -> ``~/Documents/Okul`` for the window."""
    home = Path.home() if home is None else home
    try:
        rest = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if str(rest) == "." else f"~/{rest}"

