"""The WebView2 main window's page and the state it draws, without Windows."""

import json
import os
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from blackboard_sync import deadlines
from blackboard_sync.announcements import AnnouncementRow
from blackboard_sync.courses import CourseRow
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar.settings_form import WindowStatus
from blackboard_sync.windows import webui_page, webui_state

APP_JS = (webui_page.ASSETS / "app.js").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
FORM = WindowStatus(account="Signed in as UMUT YALÇIN", account_warning=False, account_title="Sign out",
                    account_action="logout", account_enabled=True, version="1.6.1", update_title="Check now",
                    update_action="check_updates", update_enabled=True)
ACCOUNT = main.AccountCard("UY", "UMUT YALÇIN", "Last synced: today 18:14")
RECENT = tuple(main.RecentRow(f"file{i}.{kind.lower()}", "CSE303 · today 12:36", f"Term/CSE303/file{i}.{kind.lower()}",
                              kind, "2026-10-18T09:36:00Z", is_new=i == 0)
               for i, kind in enumerate(("PDF", "PPTX", "DOCX", "XLSX", "ZIP")))


def status(**changes):
    base = main.MainStatus(first_run=False, account=ACCOUNT, sync_title="Sync now", sync_enabled=True, recent=RECENT,
                           form=FORM, home=main.HomeState(main.STATE_SYNCED, "Up to date", ACCOUNT.detail),
                           pause_enabled=True, home_heading="Good afternoon, Umut", home_subtitle="1 deadline today")
    return replace(base, **changes)


def deadline_page():
    due = datetime(2026, 10, 18, 20, 59, tzinfo=timezone.utc)
    rows = (deadlines.DeadlineRow("Proposal", "CSE301 Database", due, "Term/CSE301/Proposal.pdf"),
            deadlines.DeadlineRow("Report", "PHY101 Physics", due + timedelta(days=2), "https://bb.example/report"))
    return deadlines.DeadlinePage((deadlines.DeadlineDay(due.date(), "", False, rows[:1]),
                                   deadlines.DeadlineDay((due + timedelta(days=2)).date(), "", False, rows[1:])), "")


ANNOUNCEMENTS = (AnnouncementRow("k1", "CSE301", "Exercise 2", "15.10.2026", "", "", ""),
                 AnnouncementRow("k2", "CSE303", "Online lecture", "15.10.2026", "", "", ""),
                 AnnouncementRow("k3", "COE305", "Third", "15.10.2026", "", "", ""))


COURSES = tuple(CourseRow(f"_{i}_1", f"CSE30{i}", "Course", "2026-2027 Güz", i != 4) for i in range(5))


def state(current=None, rows=ANNOUNCEMENTS, page=None):
    return webui_state.window_state(current or status(), main.OVERVIEW, main.OVERVIEW, rows,
                                    page or deadline_page(), date(2026, 10, 18), course_rows=COURSES)


@pytest.mark.parametrize("extension, kind", [
    ("PDF", "pdf"), ("pptx", "slides"), ("DOCX", "doc"), ("XLSX", "sheet"), ("CSV", "sheet"),
    ("ZIP", "archive"), ("PNG", "image"), ("MD", "note"), ("EXE", "other"), ("", "other"),
])
def test_file_kinds(extension, kind):
    assert webui_state.file_kind(extension) == kind


def test_window_state_is_plain_json_with_home_and_sidebar():
    data = state()
    assert json.loads(json.dumps(data)) == data
    assert [item["id"] for item in data["nav"]] == list(main.NAV_SECTIONS)
    assert {item["id"]: item["badge"] for item in data["nav"]}[main.COURSES] == "4/5"
    home = data["home"]
    assert home["heading"] == "Good afternoon, Umut" and home["subtitle"] == "1 deadline today"
    assert home["button"] == {"id": "sync", "title": "Sync now", "enabled": True}
    assert len(home["recent"]) == main.HOME_RECENT_ROWS  # the fifth waits for "View all"
    assert [row["kind"] for row in home["recent"]] == ["pdf", "slides", "doc", "sheet"]
    assert home["recent"][0]["new"] and not home["recent"][1]["new"]
    assert home["recent_count"] == "5 files"
    assert [row["id"] for row in home["deadlines"]] == ["Term/CSE301/Proposal.pdf", "https://bb.example/report"]
    assert data["chrome"]["account"] == {"initials": "UY", "name": "UMUT YALÇIN", "warning": False,
                                         "header": FORM.account, "action": "logout", "action_title": "Sign out",
                                         "action_enabled": True}


def test_home_button_follows_the_state():
    signed_out = status(home=main.HomeState(main.STATE_ATTENTION, "Sign-in needed", "", "login", "Sign in"))
    assert state(signed_out)["home"]["button"] == {"id": "home_action", "title": "Sign in", "enabled": True}
    paused = status(paused=True, home=main.HomeState(main.STATE_PAUSED, "Paused", ""))
    assert state(paused)["home"]["button"] is None  # the play button at the top right resumes
    busy = status(sync_title="Syncing…", sync_enabled=False)
    assert state(busy)["home"]["button"] == {"id": "sync", "title": "Syncing…", "enabled": False}


def test_attention_comes_before_announcements_and_ids_are_what_was_drawn():
    item = main.AttentionItem("Session expired", "Sign in to get new files.", "login", "Sign in")
    note = main.AttentionItem("Note", "Something", warning=False)
    data = state(status(attention=(item, note)))
    home = data["home"]
    assert [entry["title"] for entry in home["attention"]] == ["Session expired", "Note"]
    assert [row["id"] for row in home["announcements"]] == ["k1"]  # three rows in all
    assert {item["id"] for item in data["nav"] if item["badge"] == "2"} == {main.ANNOUNCEMENTS}
    ids = webui_state.ids(data)
    assert ids["file"] == {row.path for row in RECENT[:main.HOME_RECENT_ROWS]}
    assert ids["announcement"] == {"k1", "k2", "k3"}  # k1 on Home, all three on Announcements
    assert ids["attention"] == {"login"}  # a note without an action offers no click
    assert ids["deadline"] == {"Term/CSE301/Proposal.pdf", "https://bb.example/report"}


def test_empty_home_says_why():
    data = state(status(recent=()), rows=(), page=deadlines.DeadlinePage())
    assert data["home"]["recent"] == [] and data["home"]["recent_count"] == ""
    assert data["home"]["deadlines_message"] == deadlines.T_NOT_SYNCED


def test_update_banner_only_where_the_updater_runs():
    banner = main.UpdateBanner("Blackboard Sync 1.7.0 is ready", "Update", True)
    assert state(status(update_banner=banner))["banner"] == {"title": banner.title, "button": "Update", "enabled": True}
    stored = webui_state.window_state(status(update_banner=banner), main.OVERVIEW, main.OVERVIEW, (), deadline_page(),
                                      date(2026, 10, 18), updates_enabled=False)
    assert stored["banner"] is None


def test_document_is_self_contained_and_every_script_and_style_carries_the_nonce():
    html = webui_page.document("abc123")
    assert "{{" not in html
    assert "script-src 'nonce-abc123' 'unsafe-eval';" in html and "style-src 'nonce-abc123';" in html
    assert "unsafe-inline" not in html
    assert "default-src 'none'" in html
    assert re.findall(r"<script(?: [^>]*)?>", html) == ['<script nonce="abc123">']
    assert re.findall(r"<style(?: [^>]*)?>", html) == ['<style nonce="abc123">']
    assert " style=" not in html  # inline style attributes would be blocked by the policy
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in html


def test_every_icon_the_page_draws_is_in_the_sprite():
    sprite = webui_page.icon_sprite()
    names = set(re.findall(r'icon\("([a-z_-]+)"', APP_JS))
    names |= set(re.findall(r'"([a-z_]+(?:-fill)?)"', APP_JS.split("const STATE_ICONS")[1].split("const RECENT")[0]))
    names |= set(re.findall(r'href="#i-([a-z_-]+)"', (webui_page.ASSETS / "index.html").read_text()))
    names |= set(re.findall(r'#i-([a-z_-]+)', APP_JS))
    for nav_icon in webui_state.NAV_ICONS.values():
        names |= {nav_icon, f"{nav_icon}-fill"}  # the selected section shows the filled icon
    missing = sorted(name for name in names if f'id="i-{name}"' not in sprite)
    assert not missing


def test_page_script_never_turns_text_into_markup():
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                   "setTimeout(\"", "setInterval(\""):
        assert unsafe not in APP_JS, unsafe


def test_icon_license_ships_with_the_icons():
    assert "Apache License" in (webui_page.ICON_DIR / "LICENSE").read_text()


def test_page_renders_without_script_errors(tmp_path):
    """A real Chromium draws every preview state (skipped where no browser is installed)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    script = Path(__file__).resolve().parents[1] / "scripts" / "webui-preview.py"
    namespace = {"__name__": "webui_preview"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    states = namespace["fixtures"](NOW)
    executable = namespace["chromium"]()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable)
            errors = []
            for name, data in states.items():
                page = browser.new_page()
                page.on("pageerror", lambda exc, name=name: errors.append(f"{name}: {exc}"))
                page.on("console", lambda msg, name=name: msg.type == "error" and errors.append(f"{name}: {msg.text}"))
                html = webui_page.document(extra_script="window.__PREVIEW_STATE__ = " + json.dumps(data) + ";")
                page.set_content(html)
                titles = {item["id"]: item["title"] for item in data["nav"]}
                heading = (data["home"]["heading"] if data["page"] == main.OVERVIEW
                           else data["text"]["settings"] if data["section"] == main.GENERAL
                           else titles[data["section"]])
                assert page.text_content("h1") == heading
                assert "[object" not in page.text_content("#content")
                assert page.locator(".nav-item").count() == len(main.NAV_SECTIONS)
                if data["dialog"]:  # modal: the page behind it takes no clicks
                    assert page.is_visible("dialog[open]")
                    page.click('dialog [data-default="true"]')
                    assert ["dialog_answer", data["dialog"]["id"], "cancel", False] in page.evaluate("window.__calls")
                else:
                    page.click("#open-folder")
                    assert ["action", "folder"] in page.evaluate("window.__calls")
                page.close()
            browser.close()
    except sync_api.Error as exc:
        if "Executable doesn't exist" in str(exc) or "browserType.launch" in str(exc):
            pytest.skip(f"no Chromium: {exc}")
        raise
    assert not errors


def test_tray_icon_is_the_logo_with_a_status_dot():
    from blackboard_sync.menubar.model import Icon
    from blackboard_sync.windows import presentation

    idle = presentation.icon_image(Icon.IDLE)
    assert idle.size == (presentation.ICON_SIZE, presentation.ICON_SIZE)
    left, top, right, bottom = presentation.DOT
    centre = ((left + right) // 2, (top + bottom) // 2)
    for state in (Icon.SYNCING, Icon.EXPIRED, Icon.ERROR, Icon.PAUSED):
        color = presentation.COLORS[state].lstrip("#")
        assert presentation.icon_image(state).getpixel(centre)[:3] == tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    assert idle.getpixel(centre) != presentation.icon_image(Icon.ERROR).getpixel(centre)  # all is well: no dot


def settings_rows(data):
    return {row["key"]: row for section in data["settings"]["sections"] for row in section["rows"]}


def test_settings_page_rows_follow_the_model():
    from blackboard_sync.gcal import CalendarStatus

    connected = replace(FORM, calendar=CalendarStatus(connected=True, last_sync="2026-10-18T12:05:00+00:00"))
    data = webui_state.window_state(status(form=connected), main.GENERAL, main.GENERAL, theme="dark")
    keys = [section["key"] for section in data["settings"]["sections"]]
    assert keys[:4] == ["account", "sync", "appearance", "calendar"] and keys[-1] == "danger"
    rows = settings_rows(data)
    assert rows["theme"]["choices"] == [{"value": "system", "title": "System"}, {"value": "light", "title": "Light"},
                                        {"value": "dark", "title": "Dark"}]
    assert data["settings"]["theme"] == "dark" and data["theme"] == "dark"
    assert rows["interval"]["field"] == "sync_interval_minutes" and rows["interval"]["choices"][1]["value"] == 60
    calendar = rows["google_calendar"]
    assert calendar["control"] == "buttons" and calendar["title"] == "Connected"
    assert [button["key"] for button in calendar["buttons"]] == ["google_calendar_sync", "google_calendar_disconnect"]
    assert rows["google_calendar_sync"]["hidden"] and rows["google_calendar_disconnect"]["hidden"]
    assert {"google_calendar_sync", "google_calendar_disconnect", "account"} <= webui_state.ids(data)["button"]
    assert "uninstall" not in webui_state.ids(data)["button"]  # disabled while not idle (FORM default)


def test_store_build_settings_hide_updates_and_removal():
    data = webui_state.window_state(status(), main.GENERAL, main.GENERAL, packaged=True)
    sections = {section["key"]: section for section in data["settings"]["sections"]}
    assert "danger" not in sections
    rows = settings_rows(data)
    assert "check_updates" not in rows and rows["update"]["control"] == ""
    assert len(sections["updates"]["notes"]) == 2


def test_other_pages_carry_their_rows_and_ids():
    activity = (main.ActivityRow("a.pdf", "CSE303", "CSE303 · today", "Downloaded", "2 MB", "Term/CSE303/a.pdf", "PDF"),)
    data = webui_state.window_state(status(activity=activity), main.ACTIVITY, main.ACTIVITY, ANNOUNCEMENTS,
                                    deadline_page(), date(2026, 10, 18), course_rows=COURSES)
    assert data["activity"]["rows"][0] == {"id": "Term/CSE303/a.pdf", "name": "a.pdf", "detail": "CSE303 · today",
                                           "kind": "pdf", "size": "2 MB", "status": "Downloaded"}
    assert [row["enabled"] for row in data["courses"]["rows"]] == [True, True, True, True, False]
    assert [len(day["rows"]) for day in data["calendar"]["days"]] == [1, 1]
    ids = webui_state.ids(data)
    assert "Term/CSE303/a.pdf" in ids["file"] and ids["course"] == {row.id for row in COURSES}
    first = webui_state.window_state(status(first_run=True), main.OVERVIEW, "start")
    assert first["page"] == "start" and first["start"]["button"]["login"] is True


def test_theme_is_saved_and_kept_across_save():
    from blackboard_sync.menubar.settings_form import FormValues, submit
    from blackboard_sync.settings import Settings, load_settings, normalize_theme, save_settings

    assert normalize_theme("dark") == "dark" and normalize_theme("purple") == "system"
    current = Settings("https://bb.example", Path("/home/u/Documents"), theme="dark")
    submission = submit(FormValues("https://bb.example", "/home/u/Documents", True), current)
    assert submission.settings.theme == "dark"  # the form does not carry it; saving keeps it


def test_theme_survives_settings_json(tmp_path):
    from blackboard_sync.settings import Settings, load_settings, save_settings

    save_settings(tmp_path, Settings("https://bb.example", tmp_path, theme="light"))
    assert load_settings(tmp_path).theme == "light"


def test_settings_form_edits_save_and_theme_in_a_browser():
    """Typing shows the Save bar, Save sends the edited form, the theme switches at once."""
    sync_api = pytest.importorskip("playwright.sync_api")
    script = Path(__file__).resolve().parents[1] / "scripts" / "webui-preview.py"
    namespace = {"__name__": "webui_preview"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    data = namespace["fixtures"](NOW)["settings"]
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=namespace["chromium"]())
            page = browser.new_page(color_scheme="light")
            page.set_content(webui_page.document(extra_script="window.__PREVIEW_STATE__ = " + json.dumps(data) + ";"))
            assert page.is_hidden("#save-bar")
            page.fill('[data-key="field-base_url"]', "https://other.school.edu")
            assert page.is_visible("#save-bar")
            page.click("#save-bar .pill.filled")
            saved = [entry for entry in page.evaluate("window.__calls") if entry[0] == "save"]
            assert saved[-1][1]["base_url"] == "https://other.school.edu" and saved[-1][2] is False
            background = page.evaluate("getComputedStyle(document.body).backgroundColor")
            page.select_option('[data-key="select-theme"]', index=2)  # Dark
            assert page.evaluate("document.documentElement.dataset.theme") == "dark"
            assert page.evaluate("getComputedStyle(document.body).backgroundColor") != background
            assert ["set_theme", "dark"] in page.evaluate("window.__calls")
            page.click("#save-bar .pill.gray")  # Cancel: back to what is saved
            assert page.input_value('[data-key="field-base_url"]') == data["settings"]["values"]["base_url"]
            browser.close()
    except sync_api.Error as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip(f"no Chromium: {exc}")
        raise
