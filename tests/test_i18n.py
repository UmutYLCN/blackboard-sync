"""The language setting: every text has its translation in every language, and the app starts in the saved one."""

import ast
import importlib
import json
import os
import string
import subprocess
import sys
from pathlib import Path

import pytest

from blackboard_sync import i18n
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.settings import Settings, load_settings, save_settings

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "blackboard_sync"
TRANSLATED = [code for code, _ in i18n.LANGUAGES if code != i18n.ENGLISH]


def catalog_of(code: str) -> dict[str, str]:
    return importlib.import_module(f"blackboard_sync.locale_{code}").CATALOG


def source_texts() -> dict[str, str]:
    """Every literal passed to tr()/ntr() in the app, with where it is."""
    texts = {}
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "i18n.py":  # tr() itself
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "ntr"):
                for arg in node.args[: 1 if node.func.id == "tr" else 2]:
                    assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (
                        f"{path.name}:{node.lineno}: tr() needs a literal so the catalog can have it")
                    texts.setdefault(arg.value, f"{path.name}:{node.lineno}")
    return texts


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def test_the_settings_menu_lists_every_language_in_itself():
    assert i18n.LANGUAGES == (("en", "English"), ("tr", "Türkçe"), ("es", "Español"), ("fr", "Français"),
                              ("de", "Deutsch"), ("ar", "العربية"))
    assert i18n.RTL_LANGUAGES == {"ar"}


@pytest.mark.parametrize("code", TRANSLATED)
def test_every_text_has_a_translation_with_the_same_fields(code):
    catalog = catalog_of(code)
    texts = source_texts()
    missing = [f"{where}: {text!r}" for text, where in texts.items() if text not in catalog]
    assert not missing, f"No {code} for:\n" + "\n".join(missing)
    wrong = [text for text in texts if fields(catalog[text]) != fields(text)]
    assert not wrong, f"{code} with other {{fields}}: {wrong}"
    assert all(isinstance(catalog[text], str) and catalog[text].strip() for text in texts)


@pytest.mark.parametrize("code", TRANSLATED)
def test_catalog_has_no_unused_entries(code):
    assert set(catalog_of(code)) - set(source_texts()) == set()


@pytest.mark.parametrize("spec", ["blackboard_sync.spec", "blackboard_sync_mas.spec", "blackboard_sync_windows.spec"])
def test_frozen_apps_bundle_every_catalog(spec):
    """The catalogs are imported by name, which PyInstaller cannot see; the specs list them."""
    text = (ROOT / "packaging" / spec).read_text(encoding="utf-8")
    assert all(f'"blackboard_sync.locale_{code}"' in text for code in TRANSLATED)


def test_only_the_chosen_language_is_loaded():
    code = (
        "import sys\n"
        "from blackboard_sync import i18n\n"
        "i18n.set_language('de')\n"
        "i18n.tr('Sync now')\n"
        "print(sorted(m for m in sys.modules if m.startswith('blackboard_sync.locale_')))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC.parent), i18n.LANGUAGE_ENV: "en"}
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "['blackboard_sync.locale_de']"


@pytest.fixture
def turkish():
    i18n.set_language(i18n.TURKISH)
    yield
    i18n.set_language(i18n.ENGLISH)


@pytest.mark.parametrize("code", TRANSLATED)
def test_tr_uses_the_chosen_languages_catalog(code):
    i18n.set_language(code)
    try:
        assert i18n.tr("Sync now") == catalog_of(code)["Sync now"] != "Sync now"
        assert i18n.ntr("{n} file", "{n} files", 1) == catalog_of(code)["{n} file"]
        assert i18n.ntr("{n} file", "{n} files", 2) == catalog_of(code)["{n} files"]
        assert i18n.is_rtl() == (code == "ar")
    finally:
        i18n.set_language(i18n.ENGLISH)
    assert not i18n.is_rtl()


def test_tr_and_ntr(turkish):
    assert i18n.tr("Sync now") == "Şimdi senkronize et"
    assert i18n.ntr("{n} file", "{n} files", 1).format(n=1) == "1 dosya"
    assert i18n.ntr("{n} file", "{n} files", 3).format(n=3) == "3 dosya"
    assert i18n.tr("not in the catalog") == "not in the catalog"
    i18n.set_language(i18n.ENGLISH)
    assert i18n.tr("Sync now") == "Sync now"
    assert i18n.ntr("{n} file", "{n} files", 3) == "{n} files"


def test_turkish_dates(turkish):
    from datetime import date

    from blackboard_sync import deadlines

    # MONTHS was made in English when the module was imported; the order of day and month is Turkish now.
    assert deadlines.month_day(date(2026, 10, 15), "09:00") == "15 October 09:00"


def test_saved_language_reads_settings_json(tmp_path):
    env = {"BBSYNC_DATA_DIR": str(tmp_path)}
    assert i18n.saved_language(env) == "en"  # nothing saved yet
    (tmp_path / "settings.json").write_text(json.dumps({"language": "tr"}), encoding="utf-8")
    assert i18n.saved_language(env) == "tr"
    (tmp_path / "settings.json").write_text(json.dumps({"language": "ar"}), encoding="utf-8")
    assert i18n.saved_language(env) == "ar"
    (tmp_path / "settings.json").write_text(json.dumps({"language": "pt"}), encoding="utf-8")
    assert i18n.saved_language(env) == "en"  # unknown: English
    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")
    assert i18n.saved_language(env) == "en"
    assert i18n.saved_language({**env, i18n.LANGUAGE_ENV: "tr"}) == "tr"


def test_settings_keep_the_language(tmp_path):
    settings = Settings("https://bb.example.edu", tmp_path / "Docs", language="tr")
    save_settings(tmp_path, settings)
    assert load_settings(tmp_path).language == "tr"
    # Older settings files have no language: English.
    (tmp_path / "settings.json").write_text(json.dumps({"base_url": "https://bb.example.edu",
                                                        "dest": str(tmp_path)}), encoding="utf-8")
    assert load_settings(tmp_path).language == "en"


def test_form_offers_every_language_and_reports_a_change(tmp_path):
    current = Settings("https://bb.example.edu", tmp_path)
    values = settings_form.initial_values(current, current, autostart=False)
    assert values.language == "en"
    assert [name for _, name in settings_form.LANGUAGE_OPTIONS] == [
        "English", "Türkçe", "Español", "Français", "Deutsch", "العربية"]
    assert settings_form.language_code("Türkçe") == "tr"
    assert settings_form.language_title("tr") == "Türkçe"
    for code, name in i18n.LANGUAGES:
        assert settings_form.language_code(name) == code and settings_form.language_title(code) == name
    assert not settings_form.submit(values, current).language_changed
    values.language = "tr"
    submission = settings_form.submit(values, current)
    assert submission.language_changed and submission.settings.language == "tr"
    # Only the language changed: no sign-in, no move.
    assert not submission.school_changed and not submission.dest_changed


def test_app_texts_follow_the_saved_language(tmp_path):
    """A fresh process with Turkish saved builds every module constant in Turkish."""
    (tmp_path / "settings.json").write_text(json.dumps({
        "base_url": "https://bb.example.edu", "dest": str(tmp_path / "Docs"), "language": "tr"}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != i18n.LANGUAGE_ENV}
    # UTF-8 output: a Windows console code page cannot print every Turkish letter.
    env.update(BBSYNC_DATA_DIR=str(tmp_path), PYTHONPATH=str(SRC.parent), PYTHONIOENCODING="utf-8")
    code = (
        "from datetime import date\n"
        "from blackboard_sync.menubar import main_window_model as m, model, settings_form as f\n"
        "from blackboard_sync import deadlines\n"
        "print(m.T_NAV_OVERVIEW, m.T_STATE_TITLES[m.STATE_PAUSED], model.T_SYNC_NOW, f.T_SECTION_UPDATES,"
        " deadlines.month_day(date(2026, 10, 15), '09:00'), model.files(2), sep='|')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.strip().split("|") == ["Ana sayfa", "Duraklatıldı", "Şimdi senkronize et", "Güncellemeler",
                                      "15 Ekim 09:00", "2 dosya"]


def test_wait_for_instance_retries_until_the_old_copy_quits(tmp_path, monkeypatch):
    from blackboard_sync.config import Config

    config = Config(base_url="https://bb.example.edu", dest=tmp_path, data_dir=tmp_path)
    answers = [None, None, "lock"]
    monkeypatch.setattr(jobs, "single_instance", lambda _config: answers.pop(0))
    now = [0.0]
    slept = []
    lock = jobs.wait_for_instance(config, timeout=5, sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
                                  clock=lambda: now[0])
    assert lock == "lock" and len(slept) == 2
    # Still running after the timeout: give up, as a second copy would.
    monkeypatch.setattr(jobs, "single_instance", lambda _config: None)
    now[0] = 0.0
    assert jobs.wait_for_instance(config, timeout=1, sleep=lambda s: now.__setitem__(0, now[0] + s),
                                  clock=lambda: now[0]) is None


def test_relaunch_starts_a_restarting_copy(tmp_path):
    from blackboard_sync.config import Config

    config = Config(base_url="https://bb.example.edu", dest=tmp_path, data_dir=tmp_path)
    calls = []
    jobs.relaunch(config, ["app"], popen=lambda cmd, **kw: calls.append((cmd, kw)))
    (command, options), = calls
    assert command == ["app", jobs.RESTARTING]
    assert options["start_new_session"] is True and options["stdin"] == subprocess.DEVNULL
    calls.clear()
    jobs.relaunch(config, ["app.exe"], popen=lambda cmd, **kw: calls.append((cmd, kw)), creationflags=8)
    assert calls[0][1]["creationflags"] == 8 and "start_new_session" not in calls[0][1]
