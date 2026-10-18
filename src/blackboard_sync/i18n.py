"""The app's languages: English, the text written in the code, and Turkish.

Every text a student reads goes through ``tr`` (or ``ntr`` when it counts
something); Turkish comes from the catalog in ``locale_tr``. The language is the
``language`` saved in ``settings.json``. It is read once, the first time a text
is needed, so the text constants of every module are already in that language;
a new choice applies when the app starts again.

``BBSYNC_LANGUAGE`` overrides the saved choice (the tests run in English).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

ENGLISH = "en"
TURKISH = "tr"
# (code, the language's name in itself); the order of the Settings menu.
LANGUAGES = ((ENGLISH, "English"), (TURKISH, "Türkçe"))
DEFAULT_LANGUAGE = ENGLISH
LANGUAGE_ENV = "BBSYNC_LANGUAGE"
SETTINGS_FILE = "settings.json"  # settings.SETTINGS_FILE; settings itself needs tr

_language: str | None = None
_catalog: dict[str, str] | None = None


def normalize_language(value: object) -> str:
    """A known language code, else English (a missing or hand-edited value)."""
    return value if isinstance(value, str) and value in dict(LANGUAGES) else DEFAULT_LANGUAGE


def language_name(code: str) -> str:
    return dict(LANGUAGES)[normalize_language(code)]


def saved_language(env: Mapping[str, str] | None = None) -> str:
    """The language chosen in Settings, read from ``settings.json`` in the data folder."""
    env = os.environ if env is None else env
    if env.get(LANGUAGE_ENV):
        return normalize_language(env[LANGUAGE_ENV])
    from blackboard_sync.system import default_data_dir

    folder = Path(env.get("BBSYNC_DATA_DIR") or default_data_dir(env=env)).expanduser()
    try:
        data = json.loads((folder / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_LANGUAGE
    return normalize_language(data.get("language") if isinstance(data, dict) else None)


def language() -> str:
    """The language texts are shown in; read from the settings on first use."""
    global _language
    if _language is None:
        _language = saved_language()
    return _language


def set_language(code: str) -> None:
    """Use ``code`` from now on; texts already made (module constants) keep their language."""
    global _language
    _language = normalize_language(code)


def catalog() -> dict[str, str]:
    """English text -> Turkish text."""
    global _catalog
    if _catalog is None:
        from blackboard_sync.locale_tr import CATALOG

        _catalog = CATALOG
    return _catalog


def tr(text: str) -> str:
    """``text`` in the app's language; English is the text itself."""
    if language() == ENGLISH:
        return text
    return catalog().get(text, text)


def ntr(one: str, many: str, count: int) -> str:
    """``one`` or ``many`` by ``count``, in the app's language ("1 file", "2 files").

    Turkish keeps the noun singular after a number, so both map to the same text.
    """
    return tr(one if count == 1 else many)
