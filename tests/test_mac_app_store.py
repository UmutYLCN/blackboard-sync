"""Mac App Store (``mas``) distribution: sandbox container paths, security-scoped folder bookmarks,
WKWebView-only sign-in and silent refresh, SMAppService login items, App Store update seam,
AI copy-command, offline Demo Mode, and packaging/entitlements contract.
"""

from __future__ import annotations

import base64
import json
import plistlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from blackboard_sync import (
    ai_launcher,
    announcements,
    cli,
    courses,
    deadlines,
    demo,
    i18n,
    licensing,
    login as login_mod,
    macos_bookmarks,
    session_refresh,
    settings as settings_mod,
    system,
    uninstall,
    updater,
)
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.menubar import jobs, launchagent, main_window_model as main, settings_form
from blackboard_sync.menubar.model import AppModel
from blackboard_sync.notebooklm import signin as notebooklm_signin
from blackboard_sync.session import load_session

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_bookmarks():
    macos_bookmarks.release_all()
    yield
    macos_bookmarks.release_all()


# -- 1. Sandbox container paths & real user home -----------------------------------------


def test_mas_default_data_dir_uses_sandbox_container_without_double_nesting(monkeypatch):
    regular_home = Path("/Users/student")
    # Direct macOS build stays in ~/Library/Application Support/blackboard-sync.
    assert system.default_data_dir(platform="darwin", env={}, home=regular_home) == (
        regular_home / "Library" / "Application Support" / "blackboard-sync"
    )

    # Unsandboxed MAS dev run points into the MAS container Data folder.
    assert system.default_data_dir(
        platform="darwin",
        env={"BBSYNC_DISTRIBUTION": "mas"},
        home=regular_home,
    ) == (
        regular_home
        / "Library"
        / "Containers"
        / system.MAS_BUNDLE_ID
        / "Data"
        / "Library"
        / "Application Support"
        / "blackboard-sync"
    )

    # Custom bundle ID overrides the container folder name.
    assert system.default_data_dir(
        platform="darwin",
        env={"BBSYNC_DISTRIBUTION": "mas", "BBSYNC_MAS_BUNDLE_ID": "edu.example.bbsync"},
        home=regular_home,
    ) == (
        regular_home
        / "Library"
        / "Containers"
        / "edu.example.bbsync"
        / "Data"
        / "Library"
        / "Application Support"
        / "blackboard-sync"
    )

    # Inside macOS App Sandbox, secinitd already sets HOME to .../Library/Containers/<id>/Data.
    container_home = regular_home / "Library" / "Containers" / system.MAS_BUNDLE_ID / "Data"
    assert system.default_data_dir(
        platform="darwin",
        env={"APP_SANDBOX_CONTAINER_ID": system.MAS_BUNDLE_ID},
        home=container_home,
    ) == container_home / "Library" / "Application Support" / "blackboard-sync"

    # Config.from_env picks up the MAS container path dynamically (on a Mac: the host platform decides).
    monkeypatch.setattr(sys, "platform", "darwin")
    cfg = Config.from_env({"BBSYNC_DISTRIBUTION": "mas"})
    assert "Containers" in cfg.data_dir.parts and cfg.data_dir.name == "blackboard-sync"


@pytest.mark.skipif(sys.platform == "win32", reason="pwd and the macOS App Sandbox exist only on POSIX")
def test_real_user_home_escapes_sandbox_container(monkeypatch):
    regular = Path("/Users/student")
    assert system.real_user_home(regular) == regular

    container = Path("/Users/student/Library/Containers/io.github.umutylcn.blackboard-sync.mas/Data")
    monkeypatch.setattr("pwd.getpwuid", lambda _uid: SimpleNamespace(pw_dir="/Users/student"))
    assert system.real_user_home(container) == regular


# -- 2. Security-scoped folder bookmarks & CLI sync gate ---------------------------------


def test_bookmarks_save_activate_refresh_stale_and_release(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    first_dir = tmp_path / "DocsA"
    second_dir = tmp_path / "DocsB"
    first_dir.mkdir()
    second_dir.mkdir()

    assert not macos_bookmarks.has_bookmark(data_dir)
    assert macos_bookmarks.activate_saved_bookmark(data_dir, sandboxed=False) is None

    saved = macos_bookmarks.save_bookmark(data_dir, first_dir, sandboxed=False)
    assert saved.resolve() == first_dir.resolve()
    assert macos_bookmarks.has_bookmark(data_dir)
    assert macos_bookmarks.is_active(saved)

    # Re-activating on next launch resolves the saved folder.
    macos_bookmarks.release_all()
    assert not macos_bookmarks.is_active(saved)
    resolved = macos_bookmarks.activate_saved_bookmark(data_dir, sandboxed=False)
    assert resolved is not None and resolved.resolve() == first_dir.resolve()
    assert macos_bookmarks.is_active(resolved)

    # Switching folders releases the previous security scope when asked.
    saved2 = macos_bookmarks.save_bookmark(data_dir, second_dir, sandboxed=False)
    macos_bookmarks.release_except(saved2)
    assert not macos_bookmarks.is_active(saved)
    assert macos_bookmarks.is_active(saved2)

    # Stale bookmark bytes trigger an automatic bookmark refresh on launch.
    macos_bookmarks.release_all()
    calls: list[Path] = []
    stopped: list[str] = []

    class FakeURL:
        def startAccessingSecurityScopedResource(self):
            return True

        def stopAccessingSecurityScopedResource(self):
            stopped.append("stopped")

    fake_url = FakeURL()
    monkeypatch.setattr(macos_bookmarks.sys, "platform", "darwin")
    monkeypatch.setattr(
        macos_bookmarks,
        "_resolve_bookmark_bytes",
        lambda _raw, sandboxed=None: (second_dir, fake_url, True, True),
    )
    orig_save = macos_bookmarks.save_bookmark

    def record_save(d_dir, path, nsurl=None, *, sandboxed=None):
        calls.append(path)
        return path

    monkeypatch.setattr(macos_bookmarks, "save_bookmark", record_save)
    macos_bookmarks.bookmark_path(data_dir).write_text(
        json.dumps({"path": str(second_dir), "bookmark": base64.b64encode(b"stale-bytes").decode("ascii")}),
        encoding="utf-8",
    )
    refreshed = macos_bookmarks.activate_saved_bookmark(data_dir, sandboxed=True)
    assert refreshed == second_dir
    assert calls == [second_dir]
    macos_bookmarks.release_all()
    assert stopped == ["stopped"]
    monkeypatch.setattr(macos_bookmarks, "save_bookmark", orig_save)


def test_mas_cli_sync_refuses_to_run_before_folder_bookmark_is_chosen(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    dest_dir = tmp_path / "ChosenDocs"
    dest_dir.mkdir()
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    monkeypatch.setenv("BBSYNC_DATA_DIR", str(data_dir))

    # Even if settings.json and a demo session exist, MAS refuses sync without a saved bookmark.
    settings_mod.save_settings(data_dir, settings_mod.Settings(demo.DEMO_BASE_URL, dest_dir))
    cfg = Config(base_url=demo.DEMO_BASE_URL, dest=dest_dir, data_dir=data_dir)
    demo.save_demo_session(cfg)

    with pytest.raises(BlackboardSyncError):
        with macos_bookmarks.scoped_folder_access(data_dir, require=True):
            pass

    rc = cli.main(["--base-url", demo.DEMO_BASE_URL, "sync", "--dest", str(dest_dir), "--json"])
    assert rc != 0
    assert not (dest_dir / "University").exists()

    # Once the student chooses the folder (saving its bookmark), sync succeeds cleanly.
    macos_bookmarks.save_bookmark(data_dir, dest_dir, sandboxed=False)
    macos_bookmarks.release_all()
    rc_ok = cli.main(["--base-url", demo.DEMO_BASE_URL, "sync", "--dest", str(dest_dir), "--json"])
    assert rc_ok == 0
    assert (dest_dir / "University").is_dir()


# -- 3. First-launch onboarding & Settings sections in MAS -------------------------------


def test_mas_onboarding_starts_empty_and_hides_non_sandbox_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    data_dir = tmp_path / "data"
    dest_dir = tmp_path / "Docs"
    cfg = Config(data_dir=data_dir, dest=dest_dir)

    # First launch: not configured, school and folder both empty, autostart opt-in (False).
    assert not jobs.is_configured(cfg)
    assert main.shows_window_at_launch(background=True, configured=jobs.is_configured(cfg))
    current = jobs.effective_settings(cfg)
    form = settings_form.initial_values(None, current, autostart=False, mas=True)
    assert form.base_url == ""
    assert form.dest == ""
    assert form.autostart is False

    # Even with settings.json saved, MAS stays unconfigured until dest-bookmark.json exists.
    settings_mod.save_settings(data_dir, settings_mod.Settings(demo.DEMO_BASE_URL, dest_dir))
    assert not jobs.is_configured(cfg)
    form_no_bm = settings_form.initial_values(
        settings_mod.load_settings(data_dir), current, autostart=False, mas=True, has_folder_bookmark=False
    )
    assert form_no_bm.base_url == demo.DEMO_SCHOOL_LABEL
    assert form_no_bm.dest == ""

    # Saving the bookmark completes configuration; "Demo University" round-trips back to DEMO_BASE_URL.
    dest_dir.mkdir()
    macos_bookmarks.save_bookmark(data_dir, dest_dir, sandboxed=False)
    assert jobs.is_configured(cfg)
    form_ready = settings_form.initial_values(
        settings_mod.load_settings(data_dir), current, autostart=False, mas=True, has_folder_bookmark=True
    )
    assert settings_form.submit(form_ready, current).settings.base_url == demo.DEMO_BASE_URL

    # Get started screen exposes "Try the demo" and hides Gemini Notebook in MAS.
    unconfigured_model = AppModel(dest=dest_dir, now=NOW, configured=False)
    status = main.main_status(unconfigured_model, NOW)
    assert status.first_run
    assert status.shows_demo is True
    assert status.shows_notebooklm is False
    assert not unconfigured_model.menu(NOW).sync_enabled

    # Settings sections omit Gemini Notebook, AI terminal picker, Danger zone, and check_updates switch.
    sections = settings_form.settings_sections(notebooklm=True, auto_relogin=True, mas=True)
    keys = [s.key for s in sections]
    assert settings_form.SECTION_NOTEBOOKLM not in keys
    assert settings_form.SECTION_AI not in keys
    assert settings_form.SECTION_DANGER not in keys
    updates_sec = next(s for s in sections if s.key == settings_form.SECTION_UPDATES)
    assert [r.key for r in updates_sec.rows] == ["update"]
    assert updates_sec.rows[0].button == ""
    assert updater.MAS_STORE_UPDATES in updates_sec.footer
    assert uninstall.MAS_STORE_REMOVAL in updates_sec.footer


# -- 4. WKWebView-only login, silent refresh & Gemini Notebook guard ---------------------


def test_mas_login_and_silent_refresh_never_touch_external_browsers(tmp_path, monkeypatch):
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")

    # External browser discovery is completely bypassed in MAS builds.
    assert login_mod.discover_browser() is None
    assert login_mod.choose_browser("auto") is None
    assert login_mod.choose_browser("chrome") is None
    assert login_mod.login_method_label("auto") == login_mod.INAPP
    # The real web-view check loads the host's GUI backend for the rest of the test process
    # (on Windows, pywebview and .NET: later tests could then open a window and never return).
    monkeypatch.setattr(login_mod, "inapp_check_runtime", lambda: "WKWebView")
    monkeypatch.setattr(login_mod, "_connector", lambda *_a: pytest.fail("MAS must not load playwright"))
    assert login_mod.check_runtime() == "WKWebView"

    # Silent refresh uses in-app WKWebView and never creates a Chromium profile directory.
    cfg = Config(base_url="https://bb.example.edu", dest=tmp_path / "Docs", data_dir=tmp_path / "data")
    cfg.ensure_data_dir()
    from blackboard_sync.session import save_session

    save_session(
        cfg.session_file,
        "https://bb.example.edu",
        [{"name": "BbRouter", "value": "old-cookie", "domain": "bb.example.edu", "path": "/", "secure": True}],
        {"userName": "student1", "displayName": "Student One"},
    )
    refreshed_cookies = [
        {"name": "BbRouter", "value": "fresh-cookie", "domain": "bb.example.edu", "path": "/", "secure": True}
    ]
    inapp_calls: list[tuple[str, float]] = []

    def fake_inapp_silent(url: str, timeout: float, _check_user, **_kw):
        inapp_calls.append((url, timeout))
        return session_refresh.REFRESHED, {"userName": "student1", "displayName": "Student One"}, refreshed_cookies

    monkeypatch.setattr(
        session_refresh,
        "discover_browser",
        lambda *a, **kw: pytest.fail("discover_browser must not be called in MAS"),
    )
    res = session_refresh.silent_sign_in(cfg, inapp_silent=fake_inapp_silent)
    assert res.ok and res.reason == session_refresh.REFRESHED
    assert inapp_calls == [("https://bb.example.edu", session_refresh.SILENT_TIMEOUT)]
    assert not cfg.profile_dir.exists()
    saved = load_session(cfg.session_file, "https://bb.example.edu")
    assert saved["user"]["userName"] == "student1"
    assert any(c.get("value") == "fresh-cookie" for c in saved["cookies"])

    # Interactive SSO challenge cleanly reports NEEDS_INTERACTION.
    res_sso = session_refresh.silent_sign_in(
        cfg,
        inapp_silent=lambda _url, _timeout, _check, **_kw: (session_refresh.NEEDS_INTERACTION, None, []),
    )
    assert not res_sso.ok and res_sso.reason == session_refresh.NEEDS_INTERACTION

    # Gemini Notebook sign-in refuses immediately with a clear MAS message instead of launching Chrome/CDP.
    with pytest.raises(notebooklm_signin.NotebookLMSignInFailed) as exc_info:
        notebooklm_signin.login(cfg)
    assert exc_info.value.outcome == notebooklm_signin.NO_BROWSER
    assert "Mac App Store" in str(exc_info.value)


# -- 5. SMAppService Start at Login ------------------------------------------------------


def test_mas_launchagent_uses_smappservice_instead_of_plist(tmp_path, monkeypatch):
    agents_dir = tmp_path / "LaunchAgents"
    log_file = tmp_path / "menubar.log"
    mas_env = {"BBSYNC_DISTRIBUTION": "mas"}

    class FakeSMService:
        def __init__(self):
            self.current = launchagent.SM_NOT_REGISTERED
            self.registered = 0
            self.unregistered = 0

        def status(self):
            return self.current

        def registerAndReturnError_(self, _err):
            self.registered += 1
            self.current = launchagent.SM_ENABLED
            return True, None

        def unregisterAndReturnError_(self, _err):
            self.unregistered += 1
            self.current = launchagent.SM_NOT_REGISTERED
            return True, None

    svc = FakeSMService()
    assert not launchagent.is_installed(agents_dir, env=mas_env, service_factory=lambda: svc)
    marker = launchagent.install(log_file, agents_dir, env=mas_env, service_factory=lambda: svc)
    assert marker == Path("SMAppService.mainApp")
    assert svc.registered == 1
    assert not agents_dir.exists()  # no ~/Library/LaunchAgents plist written!
    assert launchagent.is_installed(agents_dir, env=mas_env, service_factory=lambda: svc)

    # Refreshing legacy plists is a no-op in MAS.
    launchagent.refresh_if_installed(log_file, agents_dir, env=mas_env)
    assert not agents_dir.exists()

    assert launchagent.remove(agents_dir, env=mas_env, service_factory=lambda: svc) is True
    assert svc.unregistered == 1
    assert not launchagent.is_installed(agents_dir, env=mas_env, service_factory=lambda: svc)
    assert launchagent.remove(agents_dir, env=mas_env, service_factory=lambda: svc) is False


# -- 6. Updater disabled, force-update App Store seam & uninstall guard ------------------


def test_mas_disables_self_updater_exposes_app_store_url_and_guards_uninstall(tmp_path, monkeypatch):
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    assert not updater.enabled()
    result = updater.check(get=lambda *a, **kw: pytest.fail("GitHub API must not be queried in MAS"))
    assert result == updater.CheckResult("store")

    fake_release = updater.Release(
        version="99.0.0",
        page_url=updater.RELEASES_URL,
        asset_name="Blackboard-Sync-99.0.0.dmg",
        asset_url=f"{updater.DOWNLOAD_PREFIX}v99.0.0/Blackboard-Sync-99.0.0.dmg",
    )
    with pytest.raises(updater.UpdateError) as exc_info:
        updater.download(fake_release, tmp_path)
    assert str(exc_info.value) == updater.MAS_STORE_UPDATES

    # Force-update seam opens Mac App Store Updates page, or the exact app page once MAS_APP_ID is known.
    assert updater.store_update_url(platform="darwin", env={"BBSYNC_DISTRIBUTION": "mas"}) == (
        "macappstore://showUpdatesPage"
    )
    assert updater.store_update_url(
        platform="darwin",
        env={"BBSYNC_DISTRIBUTION": "mas", "BBSYNC_MAS_APP_ID": "6740001234"},
    ) == "macappstore://apps.apple.com/app/id6740001234"
    assert updater.store_update_url(platform="darwin", env={"BBSYNC_DISTRIBUTION": "direct"}) == updater.RELEASES_URL

    # Uninstall leaves files untouched and explains Launchpad / Applications removal.
    cfg = Config(data_dir=tmp_path / "data", dest=tmp_path / "Docs")
    assert uninstall.remove_app() == [uninstall.MAS_STORE_REMOVAL]
    assert uninstall.uninstall(cfg) == [uninstall.MAS_STORE_REMOVAL]


# -- 7. AI study card copy-command in MAS ------------------------------------------------


def test_mas_ai_launcher_copies_command_without_spawning_shells_or_osascript(tmp_path, monkeypatch):
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    detected = ai_launcher.detect(
        platform="darwin",
        run=lambda *a, **kw: pytest.fail("login shell must not run in MAS"),
    )
    assert set(detected) == set(ai_launcher.AI_CLIS) and all(detected.values())
    assert ai_launcher.detect_terminals(platform="darwin") == {}

    dest = tmp_path / "Docs"
    term_dir = dest / "University" / "2026-2027 Fall"
    term_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "courses": {"c1": {"code": "CS204", "folder": "2026-2027 Fall/CS204"}},
                "items": {},
                "outputs": {},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(dest=dest, data_dir=data_dir)
    copied: list[str] = []
    res = ai_launcher.launch(
        "claude",
        resume=True,
        config=cfg,
        run=lambda *a, **kw: pytest.fail("osascript/open must not run in MAS"),
        copy_fn=lambda text: (copied.append(text), True)[1],
    )
    assert res.ok
    assert res.folder == term_dir
    assert len(copied) == 1 and "2026-2027 Fall" in copied[0] and copied[0].endswith("&& claude")

    model = AppModel(dest=dest, now=NOW, configured=True, ai_cli="claude")
    model.ai_term = "2026-2027 Fall"
    card_before = main.ai_card(model)
    assert card_before.kind == main.AI_READY
    assert card_before.tools[0].label == "Copy command for Claude Code"
    assert "copy the terminal command" in card_before.detail

    model.finish_ai_launch(res)
    card_after = main.ai_card(model)
    assert card_after.kind == main.AI_COPIED
    assert card_after.detail == "Command copied. Paste it in your terminal and press Enter."
    assert card_after.tools_enabled

    menu = model.menu(NOW)
    ai_entry = next(e for e in menu.entries if e.action == "ai_open")
    assert ai_entry.title == "Copy Claude Code command for 2026-2027 Fall"


@pytest.mark.parametrize("language, expected", [
    ("tr", "Komut kopyalandı. Terminale yapıştırın ve Enter’a basın."),
    ("fr", "Commande copiée. Collez-la dans votre terminal et appuyez sur Entrée."),
    ("de", "Befehl kopiert. Füge ihn im Terminal ein und drücke die Eingabetaste."),
    ("es", "Comando copiado. Pégalo en la terminal y pulsa Intro."),
    ("ar", "تم نسخ الأمر. الصقه في تطبيق الطرفية واضغط على Enter."),
])
def test_mas_ai_copy_confirmation_is_localized(monkeypatch, tmp_path, language, expected):
    monkeypatch.setattr(licensing, "is_mas", lambda: True)
    monkeypatch.setattr(i18n, "_language", language)
    model = AppModel(dest=tmp_path, now=NOW, configured=True)
    model.finish_ai_launch(ai_launcher.LaunchResult(
        tool=ai_launcher.TOOLS["codex"], folder=tmp_path, copied_command="codex",
    ))
    assert main.ai_card(model).detail == expected


# -- 8. Built-in offline Demo Mode -------------------------------------------------------


def test_demo_mode_syncs_courses_pdfs_announcements_and_calendar_completely_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    data_dir = tmp_path / "data"
    dest_dir = tmp_path / "DemoDocs"
    dest_dir.mkdir()
    monkeypatch.setenv("BBSYNC_DATA_DIR", str(data_dir))
    macos_bookmarks.save_bookmark(data_dir, dest_dir, sandboxed=False)
    macos_bookmarks.release_all()

    # Block all real HTTP calls to prove Demo Mode is 100% offline.
    monkeypatch.setattr(
        requests.Session,
        "request",
        lambda *a, **kw: pytest.fail("Demo Mode must not make real network requests"),
    )

    assert cli.main(["--base-url", demo.DEMO_BASE_URL, "login"]) == 0
    assert cli.main(["--base-url", demo.DEMO_BASE_URL, "sync", "--dest", str(dest_dir), "--json"]) == 0

    cfg = Config(base_url=demo.DEMO_BASE_URL, dest=dest_dir, data_dir=data_dir)
    course_rows = courses.load_rows(cfg)
    assert {r.code for r in course_rows} == {"CS204", "MATH210", "PHYS102", "HIST115"}

    pdfs = list((dest_dir / "University").rglob("*.pdf"))
    assert len(pdfs) >= 9  # 5 course handouts + 4 announcement PDFs + assignment note PDFs
    assert all(p.read_bytes().startswith(b"%PDF-") for p in pdfs)

    ann_rows = announcements.load_rows(cfg)
    assert len(ann_rows) == 4
    assert any("Midterm Review Session" in r.title for r in ann_rows)

    cal = deadlines.load_calendar(cfg, dest_dir)
    assert sum(1 for d in cal.days if not d.past) >= 3  # upcoming deadlines across multiple days
    assert sum(1 for d in cal.days if d.past) >= 1  # past-due deadline also shown

    # Keep-alive and silent refresh both succeed locally for Demo Mode.
    assert session_refresh.keep_alive(cfg).status == session_refresh.ALIVE
    assert session_refresh.silent_sign_in(cfg).reason == session_refresh.REFRESHED

    # Second sync is idempotent (0 newly downloaded files).
    report_before = json.loads(cfg.last_run_file.read_text(encoding="utf-8"))
    assert report_before["totals"]["new_files"] == 5
    assert report_before["totals"]["new_notes"] == 5
    assert report_before["totals"]["new_announcements"] == 4
    assert cli.main(["--base-url", demo.DEMO_BASE_URL, "sync", "--dest", str(dest_dir), "--json"]) == 0
    report_after = json.loads(cfg.last_run_file.read_text(encoding="utf-8"))
    assert report_after["totals"]["new_files"] == 0
    assert report_after["totals"]["new_notes"] == 0
    assert report_after["totals"]["new_announcements"] == 0


# -- 9. MAS entitlements & PyInstaller spec contract -------------------------------------


def test_mas_entitlements_and_spec_contract():
    mas_ent = plistlib.loads((ROOT / "packaging" / "entitlements" / "mas.plist").read_bytes())
    assert mas_ent == {
        "com.apple.security.app-sandbox": True,
        "com.apple.security.network.client": True,
        "com.apple.security.network.server": True,
        "com.apple.security.files.user-selected.read-write": True,
        "com.apple.security.files.bookmarks.app-scope": True,
    }

    inherit_ent = plistlib.loads((ROOT / "packaging" / "entitlements" / "mas-inherit.plist").read_bytes())
    assert inherit_ent == {
        "com.apple.security.app-sandbox": True,
        "com.apple.security.inherit": True,
    }

    spec_text = (ROOT / "packaging" / "blackboard_sync_mas.spec").read_text(encoding="utf-8")
    assert '"playwright"' in spec_text and "excludes=[" in spec_text
    assert '"blackboard_sync.min_version"' in spec_text
    assert "mas-distribution" in spec_text
    assert '"LSMinimumSystemVersion": "13.0"' in spec_text
    assert '"ITSAppUsesNonExemptEncryption": False' in spec_text
    assert (ROOT / "packaging" / "mas-distribution").is_file()
    assert (ROOT / "docs" / "MAC_APP_STORE.md").is_file()
