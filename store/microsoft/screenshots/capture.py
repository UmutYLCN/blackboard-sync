"""Capture the Windows app for the Store screenshots: src/windows/<id>.png.

PYTHONPATH=src python store/microsoft/screenshots/capture.py --font inter-latin.woff2 --font inter-latin-ext.woff2

Each window capture is the app's own WebView2 page (windows/webui) with a state from
scripts/webui-preview.py, in a Windows 11 frame, at 2x. The tray capture draws the
notification-area menu with the app's Turkish menu texts and the tray icon (the logo).
Linux has no Segoe UI: --font embeds another font. Then run render.sh for the final images.
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

# id -> (preview state, theme, content width, content height, element to scroll into view)
WINDOWS = {
    "02-genel-bakis": ("up-to-date", "light", 1180, 760, None),
    "03-teslim-tarihleri": ("calendar", "light", 1180, 760, None),
    "04-google-takvim": ("settings", "light", 1180, 760, "Görünüm"),
    "05-duyurular": ("announcements-page", "light", 1180, 760, None),
    "06-dersler": ("courses", "light", 1180, 760, None),
    "07-koyu-tema": ("up-to-date", "dark", 1180, 760, None),
    "08-baslangic": ("start", "light", 1180, 760, None),
}
TRAY = "09-tepsi-menusu"

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

# The menu the tray icon opens after a sync (menubar/model.py Model.menu, Turkish catalog).
TRAY_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
{font}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ background: transparent; font-family: 'Capture', 'Segoe UI', sans-serif; color: #f3f3f3; }}
.wrap {{ display: inline-flex; flex-direction: column; align-items: flex-end; gap: 14px; padding: 2px; }}
.menu {{ width: 430px; padding: 4px; border-radius: 8px; background: #2c2c2c; border: 1px solid #454545; font-size: 14px; }}
.menu div {{ height: 30px; display: flex; align-items: center; padding: 0 12px 0 34px; border-radius: 4px; position: relative; }}
.menu div.off {{ color: #9d9d9d; }}
.menu div.hot {{ background: #3d3d3d; }}
.menu div b {{ position: absolute; right: 12px; font-weight: 400; font-size: 13px; }}
.menu hr {{ border: 0; border-top: 1px solid #454545; margin: 4px 0; }}
.bar {{ display: flex; align-items: center; gap: 2px; height: 48px; padding: 0 10px; border-radius: 8px;
        background: #1c1c1c; border: 1px solid #333; font-size: 12px; }}
.slot {{ width: 32px; height: 40px; display: grid; place-items: center; border-radius: 4px; }}
.slot.hot {{ background: #2f2f2f; }}
.slot img {{ width: 20px; height: 20px; }}
.slot svg {{ width: 16px; height: 16px; fill: #f3f3f3; }}
.clock {{ text-align: right; line-height: 1.35; margin-left: 8px; padding: 0 4px; }}
</style></head><body><div class="wrap">
<div class="menu">
  <div class="off">✓ UMUT YALÇIN · 18:14 senkronize edildi</div>
  <div class="off">5 yeni dosya, 3 yeni duyuru · sonraki: 19:14</div>
  <hr>
  <div class="hot">Şimdi senkronize et</div>
  <div>Senkronu duraklat</div>
  <div>Dersler<b>›</b></div>
  <div>Son indirilenler<b>›</b></div>
  <div>University klasörünü aç</div>
  <hr>
  <div>Ayarlar…</div>
  <div>Çık</div>
</div>
<div class="bar">
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{up}"/></svg></div>
  <div class="slot hot"><img src="{logo}" alt=""></div>
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{wifi}"/></svg></div>
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{volume}"/></svg></div>
  <div class="slot"><svg viewBox="0 -960 960 960"><path d="{battery}"/></svg></div>
  <div class="clock">18:14<br>18.10.2026</div>
</div>
</div></body></html>"""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", type=Path, action="append", default=[],
                        help="a .woff2 used in place of Segoe UI (repeat for more files of one family)")
    parser.add_argument("--only", action="append", help="only these ids")
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


def states() -> dict:
    """scripts/webui-preview.py's states, in Turkish on Istanbul's clock."""
    os.environ["TZ"] = "Europe/Istanbul"
    time.tzset()
    sys.path.insert(0, str(ROOT / "src"))
    from blackboard_sync import i18n

    i18n.set_language("tr")  # before the modules with tr() constants are imported
    from dataclasses import replace

    from blackboard_sync.windows import webui_state

    # As the Store package shows them: the Store updates the app, so no update rows or offers.
    window_state = webui_state.window_state

    def packaged_state(status, *args, **kwargs):
        status = replace(status, attention=tuple(item for item in status.attention if item.action != "update"))
        return window_state(status, *args, **{**kwargs, "packaged": True})

    webui_state.window_state = packaged_state
    script = ROOT / "scripts" / "webui-preview.py"
    namespace = {"__name__": "webui_preview"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    now = datetime.now(timezone.utc).replace(hour=15, minute=14, second=0, microsecond=0)  # 18:14 in Istanbul
    return namespace["fixtures"](now)


def chromium() -> str | None:
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root:
        return None
    return next((str(p) for p in sorted(Path(root).glob("chromium-*/chrome-linux*/chrome"), reverse=True)), None)


def main(argv=None) -> int:
    args = parse_args(argv)
    fixtures = states()
    from blackboard_sync.windows import webui_page
    from playwright.sync_api import sync_playwright

    wanted = args.only or [*WINDOWS, TRAY]
    frame_font = font_css(args.font, "Capture")
    app_style = font_css(args.font, "Preview") + (
        ":root{--font:'Preview',system-ui,sans-serif;--font-display:'Preview',system-ui,sans-serif}" if args.font else "")
    errors = []
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium())
        for shot_id in wanted:
            out = OUT / f"{shot_id}.png"
            if shot_id == TRAY:
                page = browser.new_page(viewport={"width": 600, "height": 600}, device_scale_factor=2)
                page.set_content(TRAY_PAGE.format(font=frame_font, logo=logo(64), up=icon_path("keyboard_arrow_up"),
                                                  wifi=icon_path("wifi"), volume=icon_path("volume_up"),
                                                  battery=icon_path("battery_full")))
                page.evaluate("document.fonts.ready")
                page.locator(".wrap").screenshot(path=str(out), omit_background=True)
                page.close()
                print(out)
                continue
            name, theme, width, height, scroll = WINDOWS[shot_id]
            page = browser.new_page(viewport={"width": width + 40, "height": height + 80}, device_scale_factor=2,
                                    color_scheme=theme)
            page.on("pageerror", lambda exc, shot_id=shot_id: errors.append(f"{shot_id}: {exc}"))
            page.set_content(FRAME.format(font=frame_font, theme=theme, logo=logo(32), width=width, height=height))
            script = "window.__PREVIEW_STATE__ = " + json.dumps(fixtures[name], ensure_ascii=True) + ";"
            html = webui_page.document(extra_style=app_style, extra_script=script, lang="tr")
            page.locator("#app").evaluate("(el, html) => { el.srcdoc = html; }", html)
            app = page.frame_locator("#app")
            app.locator("body").wait_for()
            page.wait_for_timeout(300)
            if scroll:
                app.get_by_text(scroll, exact=True).first.evaluate("el => el.scrollIntoView({block: 'start'})")
                page.wait_for_timeout(100)
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
