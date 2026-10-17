"""The language setting: every text has its Turkish, and the app starts in the saved language."""

import ast
import json
import os
import string
import subprocess
import sys
from pathlib import Path

import pytest

from blackboard_sync import i18n
from blackboard_sync.locale_tr import CATALOG
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.settings import Settings, load_settings, save_settings

SRC = Path(__file__).resolve().parents[1] / "src" / "blackboard_sync"


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


def test_every_text_has_turkish_with_the_same_fields():
    texts = source_texts()
    missing = [f"{where}: {text!r}" for text, where in texts.items() if text not in CATALOG]
    assert not missing, "No Turkish for:\n" + "\n".join(missing)
    wrong = [text for text in texts if fields(CATALOG[text]) != fields(text)]
    assert not wrong, f"Turkish with other {{fields}}: {wrong}"
    assert all(CATALOG[text].strip() for text in texts)


def test_catalog_has_no_unused_entries():
    assert set(CATALOG) - set(source_texts()) == set()


@pytest.fixture
def turkish():
    i18n.set_language(i18n.TURKISH)
    yield
    i18n.set_language(i18n.ENGLISH)


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
    (tmp_path / "settings.json").write_text(json.dumps({"language": "de"}), encoding="utf-8")
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


def test_form_offers_both_languages_and_reports_a_change(tmp_path):
    current = Settings("https://bb.example.edu", tmp_path)
    values = settings_form.initial_values(current, current, autostart=False)
    assert values.language == "en"
    assert [name for _, name in settings_form.LANGUAGE_OPTIONS] == ["English", "Türkçe"]
    assert settings_form.language_code("Türkçe") == "tr"
    assert settings_form.language_title("tr") == "Türkçe"
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
    env.update(BBSYNC_DATA_DIR=str(tmp_path), PYTHONPATH=str(SRC.parent))
    code = (
        "from datetime import date\n"
        "from blackboard_sync.menubar import main_window_model as m, model, settings_form as f\n"
        "from blackboard_sync import deadlines\n"
        "print(m.T_NAV_OVERVIEW, m.T_STATE_TITLES[m.STATE_PAUSED], model.T_SYNC_NOW, f.T_SECTION_UPDATES,"
        " deadlines.month_day(date(2026, 10, 15), '09:00'), model.files(2), sep='|')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout
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
