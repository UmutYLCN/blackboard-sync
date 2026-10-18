"""Render the Windows WebView2 main window with invented data, without Windows or signing in.

PYTHONPATH=src python scripts/webui-preview.py [--lang en|tr] [--out DIR] [--font FILE.woff2]
           [--state NAME ...] [--html-only]

Writes one HTML file per state to DIR and, unless --html-only, Playwright screenshots in
light and dark at 1024x720 and 1280x900. The page is the app's own (windows/webui_page.py);
only the state is invented. Linux has no Segoe UI: --font embeds another font for the shot.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SIZES = ((1024, 720), (1280, 900))
THEMES = ("light", "dark")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="en", choices=("en", "tr"))
    parser.add_argument("--out", type=Path, default=Path("docs/screenshots/windows-webui"))
    parser.add_argument("--font", type=Path, action="append", default=[],
                        help="a .woff2 used in place of Segoe UI (repeat for more files of one family)")
    parser.add_argument("--state", action="append", help="only these states (default: all)")
    parser.add_argument("--html-only", action="store_true")
    return parser.parse_args(argv)


def fixtures(now: datetime) -> dict[str, dict]:
    """name -> window state, built through the app's own model and serializer."""
    from dataclasses import replace

    from blackboard_sync import __version__, deadlines
    from blackboard_sync.announcements import AnnouncementRow
    from blackboard_sync.i18n import tr
    from blackboard_sync.menubar import main_window_model as main
    from blackboard_sync.menubar.model import T_SYNC_NOW
    from blackboard_sync.menubar.settings_form import WindowStatus
    from blackboard_sync.windows import webui_state

    form =WindowStatus(account=tr("Signed in as {name}").format(name="UMUT YALÇIN"), account_warning=False,
                        account_title=tr("Sign out"), account_action="logout", account_enabled=True,
                        version=__version__, update_title=tr("Check now"), update_action="check_updates",
                        update_enabled=True)
    files = (
        ("SPM Slides-3 PDF.pdf", "PDF", "COE305"), ("Lecture 4 - Normalization.pptx", "PPTX", "CSE301"),
        ("Assignment 1.docx", "DOCX", "COE305"), ("Grades week 5.xlsx", "XLSX", "PHY101"),
        ("Lab material.zip", "ZIP", "CSE303"),
    )
    recent = tuple(main.RecentRow(name, f"{course} · {tr('today {time}').format(time='12:36')}",
                                  f"2026-2027 Güz/{course}/{name}", kind, "2026-10-18T09:36:00Z", is_new=index < 2)
                   for index, (name, kind, course) in enumerate(files))
    announcements = (
        AnnouncementRow("a1", "CSE301 Database Management", "Home Exercise 2 Hk", "15.10.2026 15:04", "", "", ""),
        AnnouncementRow("a2", "CSE303 Algorithm Analysis", "16.10.2026 Cuma Dersi - Online", "15.10.2026 13:07",
                        "", "", ""),
        AnnouncementRow("a3", "COE305 Software Project Management", "Software Project Management Online Lecture",
                        "15.10.2026 12:36", "", "", ""),
    )
    local = now.astimezone()
    due = (("PROJECT PROPOSAL SUBMISSION", "CSE301 Database Management", local.replace(hour=23, minute=59)),
           ("Report 2 Due Date: 23.10.2025 11:59 pm", "PHY101 Physics I (Mechatronics - CENG - Chemical Eng.)",
            local.replace(hour=23, minute=59) + timedelta(days=5)),
           ("Report 3 Due Date: 23.10.2025 11:59 pm", "PHY101 Physics I (Mechatronics - CENG - Chemical Eng.)",
            local.replace(hour=23, minute=59) + timedelta(days=5)),
           ("Assignment 1", "COE305 Software Project Management", local.replace(hour=23, minute=59) + timedelta(days=13)))
    days = {}
    for title, course, when in due:
        days.setdefault(when.date(), []).append(deadlines.DeadlineRow(title, course, when, f"https://bb.example/{title}"))
    page = deadlines.DeadlinePage(tuple(deadlines.DeadlineDay(day, "", False, tuple(rows))
                                        for day, rows in sorted(days.items())), "")
    heading = main.greeting("UMUT YALÇIN", now)
    subtitle = main.deadline_subtitle(page, now)
    account = main.AccountCard("UY", "UMUT YALÇIN", tr("Last synced: {time}").format(time=tr("today {time}").format(time="18:14")))
    synced = main.MainStatus(
        first_run=False, account=account, sync_title=T_SYNC_NOW, sync_enabled=True, recent=recent, form=form,
        home=main.HomeState(main.STATE_SYNCED, main.T_STATE_TITLES[main.STATE_SYNCED], account.detail),
        pause_enabled=True, home_heading=heading, home_subtitle=subtitle)
    states = {
        "up-to-date": (synced, announcements, page),
        "syncing": (replace(synced, sync_title=tr("Syncing…"), sync_enabled=False, scene=main.SCENE_COMPACT,
                            home=main.HomeState(main.STATE_SYNCING, main.T_STATE_TITLES[main.STATE_SYNCING],
                                                tr("CSE303: 2 new files"))), announcements, page),
        "first-sync": (replace(synced, recent=(), sync_title=tr("Syncing…"), sync_enabled=False, scene=main.SCENE_FIRST,
                               scene_line=main.T_FIRST_SYNC, home_heading="", home_subtitle="",
                               home=main.HomeState(main.STATE_SYNCING, main.T_STATE_TITLES[main.STATE_SYNCING],
                                                   main.T_FIRST_SYNC)), (), deadlines.DeadlinePage(message=deadlines.T_NOT_SYNCED)),
        "signed-out": (replace(synced, account=main.AccountCard("!", main.T_EXPIRED, account.detail, warning=True),
                               form=replace(form, account=main.T_EXPIRED, account_warning=True, account_title=tr("Sign in"),
                                            account_action="login"),
                               home=main.HomeState(main.STATE_ATTENTION, main.T_STATE_TITLES[main.STATE_ATTENTION],
                                                   account.detail, "login", tr("Sign in")),
                               attention=(main.AttentionItem(main.T_EXPIRED, tr("Sign in to get new files."), "login",
                                                             tr("Sign in")),)), announcements, page),
        "error": (replace(synced, account=replace(account, message=tr("Sync did not finish: {error}").format(
                              error="Blackboard did not answer in time."), warning=True),
                          home=main.HomeState(main.STATE_ERROR, main.T_STATE_TITLES[main.STATE_ERROR],
                                              "Blackboard did not answer in time.")), announcements, page),
        "paused": (replace(synced, paused=True, pause_title=tr("Resume"),
                           home=main.HomeState(main.STATE_PAUSED, main.T_STATE_TITLES[main.STATE_PAUSED],
                                               account.detail)), announcements, page),
        "empty": (replace(synced, recent=(), home_heading=main.greeting("Umut", now),
                          home_subtitle=tr("No deadlines this week")), (), deadlines.DeadlinePage()),
        "update": (replace(synced, update_banner=main.UpdateBanner(
                       tr("Blackboard Sync {version} is ready").format(version="1.7.0"), main.T_UPDATE, True)),
                   announcements, page),
    }
    result = {}
    for name, (status, rows, deadline_page) in states.items():
        result[name] = webui_state.window_state(status, main.OVERVIEW, main.OVERVIEW, rows, deadline_page,
                                                now.astimezone().date(), course_count="4/5" if name == "up-to-date" else "")
    return result


def font_style(fonts: list[Path]) -> str:
    """One family from several files (a font split by script: Latin, Latin Extended for ş, ğ, İ)."""
    if not fonts:
        return ""
    faces = "".join("@font-face{font-family:'Preview';font-weight:100 900;"
                    f"src:url(data:font/woff2;base64,{base64.b64encode(font.read_bytes()).decode()}) format('woff2')}}"
                    for font in fonts)
    return faces + ":root{--font:'Preview',system-ui,sans-serif;--font-display:'Preview',system-ui,sans-serif}"


def chromium() -> str | None:
    """The preinstalled Chromium of a CI or cloud box (PLAYWRIGHT_BROWSERS_PATH), if any."""
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root:
        return None
    for candidate in sorted(Path(root).glob("chromium-*/chrome-linux*/chrome"), reverse=True):
        return str(candidate)
    return None


def main(argv=None) -> int:
    args = parse_args(argv)
    from blackboard_sync import i18n

    i18n.set_language(args.lang)  # before the modules with tr() constants are imported
    from blackboard_sync.windows import webui_page

    now = datetime.now(timezone.utc).replace(hour=15, minute=30, second=0, microsecond=0)
    states = fixtures(now)
    wanted = args.state or list(states)
    args.out.mkdir(parents=True, exist_ok=True)
    pages = {}
    for name in wanted:
        script = "window.__PREVIEW_STATE__ = " + json.dumps(states[name], ensure_ascii=True) + ";"
        html = webui_page.document(extra_style=font_style(args.font), extra_script=script, lang=args.lang)
        path = args.out / f"{name}-{args.lang}.html"
        path.write_text(html, encoding="utf-8")
        pages[name] = path
    if args.html_only:
        print("\n".join(str(path) for path in pages.values()))
        return 0
    from playwright.sync_api import sync_playwright

    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium())
        for name, path in pages.items():
            for theme in THEMES:
                for width, height in SIZES:
                    page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
                    page.on("pageerror", lambda exc, name=name: errors.append(f"{name}: {exc}"))
                    page.on("console", lambda msg, name=name: msg.type == "error" and errors.append(f"{name}: {msg.text}"))
                    page.goto(path.resolve().as_uri())
                    page.wait_for_timeout(150)
                    shot = args.out / f"{name}-{args.lang}-{theme}-{width}x{height}.png"
                    page.screenshot(path=str(shot), animations="disabled")
                    page.close()
                    print(shot)
        browser.close()
    for error in errors:
        print("page error:", error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
