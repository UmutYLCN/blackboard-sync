"""Capture the Windows app for the Store screenshots: src/windows/<id>.png.

PYTHONPATH=src python store/microsoft/screenshots/capture.py --font inter-latin.woff2 --font inter-latin-ext.woff2
PYTHONPATH=src python store/microsoft/screenshots/capture.py --lang en --font inter-latin.woff2 --font inter-latin-ext.woff2

Each window capture is the app's own WebView2 page (windows/webui) with a state from
scripts/webui-preview.py, in a Windows 11 frame, at 2x. The tray capture draws the
notification-area menu with the app's menu texts and the tray icon (the logo). The captures
go into src/windows/ for Turkish and into src/windows/<lang>/ for other languages.
Linux has no Segoe UI: --font embeds another font. Then run render.sh (--lang en) for the final images.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "src" / "windows"

# id -> (preview state, theme, content width, content height)
WINDOWS = {
    "01-home": ("notebooklm-idle", "light", 1180, 880),
    "02-school-search": ("start", "light", 1180, 760),
    "03-calendar": ("calendar", "light", 1180, 760),
    "04-google-calendar": ("settings", "light", 1180, 760),
    "05-announcements": ("announcements-page", "light", 1180, 760),
    "06-courses": ("courses", "light", 1180, 760),
    "07-languages": ("settings", "light", 1180, 760),
    "08-dark-theme": ("notebooklm-idle", "dark", 1180, 880),
}
TRAY = "09-tray"
SCHOOL_QUERY = "King"
COURSE_COLORS = {"COE305": 0, "CSE301": 1, "CSE303": 2, "PHY101": 3}

FRAME = """<!doctype html><html><head><meta charset="utf-8"><style>
{font}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ background: transparent; font-family: 'Capture', 'Segoe UI', sans-serif; }}
.win {{ display: inline-block; border-radius: 8px; overflow: hidden; border: 1px solid var(--edge); }}
.bar {{ height: 32px; display: flex; align-items: center; gap: 8px; padding-left: 12px; font-size: 12px;
        background: var(--bar); color: var(--title); }}
.bar img {{ width: 16px; height: 16px; }}
.ctrl {{ margin-left: auto; display: flex; height: 100%; }}
.ctrl svg {{ width: 46px; height: 32px; padding: 11px 18px; stroke: var(--title); fill: none; stroke-width: 1; }}
iframe {{ display: block; border: 0; }}
.light {{ --bar: #f3f3f3; --title: #1f1f1f; --edge: #c8c8c8; }}
.dark {{ --bar: #202020; --title: #f3f3f3; --edge: #3a3a3a; }}
</style></head><body>
<div class="win {theme}"><div class="bar"><img src="{logo}" alt="">Blackboard Sync<div class="ctrl">
<svg viewBox="0 0 10 10"><path d="M0 5.5h10"/></svg>
<svg viewBox="0 0 10 10"><rect x=".5" y=".5" width="9" height="9" rx="1.5"/></svg>
<svg viewBox="0 0 10 10"><path d="M.5.5l9 9M9.5.5l-9 9"/></svg></div></div>
<iframe id="app" width="{width}" height="{height}"></iframe></div>
</body></html>"""

# The menu the tray icon opens after a sync (menubar/model.py Model.menu); the texts are filled in
# from the app's catalog for the language (TRAY_TEXTS).
TRAY_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
{font}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ background: transparent; font-family: 'Capture', 'Segoe UI', sans-serif; color: #f3f3f3; }}
.wrap {{ display: inline-flex; flex-direction: column; align-items: flex-end; gap: 14px; padding: 2px; }}
.menu {{ width: 430px; padding: 4px; border-radius: 8px; background: #2c2c2c; border: 1px solid #454545; font-size: 14px; }}
.menu div {{ height: 30px; display: flex; align-items: center; padding-inline: 34px 12px; border-radius: 4px; position: relative; }}
.menu div.off {{ color: #9d9d9d; }}
.menu div.hot {{ background: #3d3d3d; }}
.menu div b {{ position: absolute; inset-inline-end: 12px; font-weight: 400; font-size: 13px; }}
.menu hr {{ border: 0; border-top: 1px solid #454545; margin: 4px 0; }}
.bar {{ display: flex; align-items: center; gap: 2px; height: 48px; padding: 0 10px; border-radius: 8px;
        background: #1c1c1c; border: 1px solid #333; font-size: 12px; }}
.slot {{ width: 32px; height: 40px; display: grid; place-items: center; border-radius: 4px; }}
.slot.hot {{ background: #2f2f2f; }}
.slot img {{ width: 20px; height: 20px; }}
.slot svg {{ width: 16px; height: 16px; fill: #f3f3f3; }}
.clock {{ text-align: right; line-height: 1.35; margin-left: 8px; padding: 0 4px; }}
</style></head><body><div class="wrap" dir="{direction}">
<div class="menu">
  <div class="off">✓ UMUT YALÇIN · {synced}</div>
  <div class="off">{summary} · {next}</div>
  <hr>
  <div class="hot">{sync_now}</div>
  <div>{pause}</div>
  <div>{courses}<b>›</b></div>
  <div>{recent}<b>›</b></div>
  <div>{open_folder}</div>
  <hr>
  <div>{settings}</div>
  <div>{quit}</div>
</div>
<div class="bar">
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{up}"/></svg></div>
  <div class="slot hot"><img src="{logo}" alt=""></div>
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{wifi}"/></svg></div>
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{volume}"/></svg></div>
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{battery}"/></svg></div>
  <div class="clock" dir="ltr">18:14<br>{date}</div>
</div>
</div></body></html>"""


def tray_texts() -> dict[str, str]:
    """The tray menu's texts in the app's language, from the same catalog the menu uses."""
    from blackboard_sync.i18n import tr

    summary = ", ".join((f"5 {tr('new files')}", f"3 {tr('new announcements')}"))
    return {
        "synced": tr("synced at {time}").format(time="18:14"),
        "summary": summary,
        "next": tr("next: {time}").format(time="19:14"),
        "sync_now": tr("Sync now"),
        "pause": tr("Pause syncing"),
        "courses": tr("Courses"),
        "recent": tr("Recent downloads"),
        "open_folder": tr("Open {folder} folder").format(folder="University"),
        "settings": tr("Settings…"),
        "quit": tr("Quit"),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", type=Path, action="append", default=[],
                        help="a .woff2 used in place of Segoe UI (repeat for more files of one family)")
    parser.add_argument("--only", action="append", help="only these ids")
    parser.add_argument("--lang", choices=("tr", "en", "es", "fr", "de", "ar"), default="tr",
                        help="the app's language (default tr)")
    return parser.parse_args(argv)


def font_css(fonts: list[Path], family: str) -> str:
    return "".join(f"@font-face{{font-family:'{family}';font-weight:100 900;"
                   f"src:url(data:font/woff2;base64,{base64.b64encode(f.read_bytes()).decode()}) format('woff2')}}"
                   for f in fonts)


def logo(size: int) -> str:
    from PIL import Image

    image = Image.open(ROOT / "assets" / "icon" / "logo.png").convert("RGBA")
    image = image.crop(image.getbbox())
    image.thumbnail((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def icon_path(name: str) -> str:
    import re

    text = (ROOT / "promo" / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    return re.search(r'<path d="([^"]+)"', text).group(1)


def states(lang: str) -> dict:
    """scripts/webui-preview.py's states, in ``lang`` on Istanbul's clock."""
    os.environ["TZ"] = "Europe/Istanbul"
    time.tzset()
    sys.path.insert(0, str(ROOT / "src"))
    from dataclasses import replace

    from blackboard_sync import i18n

    i18n.set_language(lang)  # before the modules with tr() constants are imported
    from blackboard_sync.menubar.main_window_model import fold_course_key
    from blackboard_sync.windows import webui_state

    # As the Store package shows them: the Store updates the app, so no update rows or offers.
    window_state = webui_state.window_state
    colors = {fold_course_key(code): color for code, color in COURSE_COLORS.items()}

    def packaged_state(status, section, page, announcements, deadlines, *args, values, **kwargs):
        recent = []
        for row in status.recent:
            code, _, when = row.detail.partition(" · ")
            recent.append(replace(row, course_code=code, when=when, color=COURSE_COLORS[code]))
        announcements = tuple(replace(row, course_code=row.course.split()[0]) for row in announcements)
        days = []
        for day in deadlines.days:
            rows = tuple(replace(row, course_code=row.course.split()[0], title=row.title.split(" Due Date:")[0])
                         for row in day.rows)
            days.append(replace(day, rows=rows))
        deadlines = replace(deadlines, days=tuple(days))
        status = replace(status, recent=tuple(recent), course_colors=colors)
        return window_state(status, section, page, announcements, deadlines, *args,
                            values=replace(values, language=lang), packaged=True, **kwargs)

    webui_state.window_state = packaged_state
    script = ROOT / "scripts" / "webui-preview.py"
    namespace = {"__name__": "webui_preview"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    now = datetime(2026, 10, 18, 15, 14, tzinfo=timezone.utc)  # 18:14 in Istanbul
    result = namespace["fixtures"](now)
    # Show a completed sync without the preview fixture's intentional held-file warning.
    result["notebooklm-idle"]["home"]["notebooklm"].update({"notice": "", "warning-counts": ""})
    return result


def chromium() -> str | None:
    if executable := os.environ.get("CHROME"):
        return executable
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root:
        return None
    return next((str(p) for p in sorted(Path(root).glob("chromium-*/chrome-linux*/chrome"), reverse=True)), None)


def main(argv=None) -> int:
    args = parse_args(argv)
    lang = args.lang
    fixtures = states(lang)
    out_dir = OUT if lang == "tr" else OUT / lang
    from blackboard_sync import schools
    from blackboard_sync.windows import webui_page
    from playwright.sync_api import sync_playwright

    wanted = args.only or [*WINDOWS, TRAY]
    frame_font = font_css(args.font, "Capture")
    app_style = font_css(args.font, "Preview") + (
        ":root{--font:'Preview',system-ui,sans-serif;--font-display:'Preview',system-ui,sans-serif}" if args.font else "")
    errors = []
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium())
        for shot_id in wanted:
            out = out_dir / f"{shot_id}.png"
            if shot_id == TRAY:
                page = browser.new_page(viewport={"width": 600, "height": 600}, device_scale_factor=2)
                page.set_content(TRAY_PAGE.format(font=frame_font, logo=logo(64), up=icon_path("keyboard_arrow_up"),
                                                  wifi=icon_path("wifi"), volume=icon_path("volume_up"),
                                                  battery=icon_path("battery_full"),
                                                  date="10/18/2026" if lang == "en" else "18.10.2026",
                                                  direction="rtl" if lang == "ar" else "ltr",
                                                  **tray_texts()))
                page.evaluate("document.fonts.ready")
                page.locator(".wrap").screenshot(path=str(out), omit_background=True)
                page.close()
                print(out)
                continue
            name, theme, width, height = WINDOWS[shot_id]
            page = browser.new_page(viewport={"width": width + 40, "height": height + 80}, device_scale_factor=2,
                                    color_scheme=theme)
            page.on("pageerror", lambda exc, shot_id=shot_id: errors.append(f"{shot_id}: {exc}"))
            page.set_content(FRAME.format(font=frame_font, theme=theme, logo=logo(32), width=width, height=height))
            script = "window.__PREVIEW_STATE__ = " + json.dumps(fixtures[name], ensure_ascii=True) + ";"
            if name == "start":
                matches = json.dumps([school.name for school in schools.search(SCHOOL_QUERY)])
                script += f"window.pywebview = {{api: {{search_schools: () => Promise.resolve({matches})}}}};"
            html = webui_page.document(extra_style=app_style, extra_script=script, lang=lang)
            page.locator("#app").evaluate("(el, html) => { el.srcdoc = html; }", html)
            app = page.frame_locator("#app")
            app.locator("body").wait_for()
            page.wait_for_timeout(300)
            if shot_id == "02-school-search":
                app.locator('input[aria-controls="school-list"]').fill(SCHOOL_QUERY)
                app.get_by_role("option").first.wait_for()
            if shot_id == "04-google-calendar":
                app.locator('[data-key="select-theme"]').evaluate("el => el.closest('.section-title + section').scrollIntoView()")
            if shot_id == "07-languages":
                language = app.locator('[data-key="select-language"]')
                # Native select popups are outside Chromium's page screenshot surface.
                # Expand the real app options as a listbox for the capture.
                language.evaluate("""el => {
                    el.size = el.options.length;
                    el.style.height = 'auto';
                    el.scrollIntoView({block: 'center'});
                }""")
            page.evaluate("document.fonts.ready")
            page.locator(".win").screenshot(path=str(out), omit_background=True, animations="disabled")
            page.close()
            print(out)
        browser.close()
    for error in errors:
        print("page error:", error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
