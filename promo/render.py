"""Render a promo film (promo/*.html) to an MP4, frame by frame in Chromium.

PYTHONPATH=src python promo/render.py promo/mac.html --out mac.mp4 --font Inter.woff2 [--font ...]
python promo/render.py promo/mac.html --still 3 --still 20.5 --out-dir /tmp/stills   # single frames

The page builds its scenes from the time render.py gives it (window.seek), so the
same film gives the same frames on every run. Icons are Material Symbols Rounded
(Apache-2.0) from promo/icons and the app's own set; the logo is assets/icon/logo.png.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMO = ROOT / "promo"
ICON_DIRS = (PROMO / "icons", ROOT / "src" / "blackboard_sync" / "windows" / "webui" / "icons")
_PATH = re.compile(r'<path d="([^"]+)"')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("film", type=Path)
    parser.add_argument("--out", type=Path, help="the MP4 to write")
    parser.add_argument("--font", type=Path, action="append", default=[], help="a .woff2 of the film's font family")
    parser.add_argument("--still", type=float, action="append", default=[], help="write the frame at this second")
    parser.add_argument("--out-dir", type=Path, default=Path("."), help="where stills go")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--crf", type=int, default=17)
    return parser.parse_args(argv)


def icon_sprite(html: str) -> str:
    names = set(re.findall(r"#i-([a-z0-9_-]+)", html)) | set(re.findall(r'icon\("([a-z0-9_-]+)"', html))
    symbols, missing = [], []
    for name in sorted(names):
        source = next((folder / f"{name}.svg" for folder in ICON_DIRS if (folder / f"{name}.svg").exists()), None)
        match = _PATH.search(source.read_text(encoding="utf-8")) if source else None
        if match is None:
            missing.append(name)
            continue
        symbols.append(f'<symbol id="i-{name}" viewBox="0 -960 960 960"><path d="{match.group(1)}"/></symbol>')
    if missing:
        raise SystemExit(f"missing icons: {', '.join(missing)}")
    return '<svg xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0">' + "".join(symbols) + "</svg>"


def logo(size: int = 512) -> str:
    from PIL import Image

    image = Image.open(ROOT / "assets" / "icon" / "logo.png").convert("RGBA")
    image = image.crop(image.getbbox())
    image.thumbnail((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def font_css(fonts: list[Path]) -> str:
    return "".join("@font-face{font-family:'Film';font-weight:100 900;font-display:block;"
                   f"src:url(data:font/woff2;base64,{base64.b64encode(f.read_bytes()).decode()}) format('woff2')}}"
                   for f in fonts)


def app_language(html: str) -> None:
    """The app's texts in the film's language (``<html lang>``), Istanbul's clock; before any app import."""
    import time

    sys.path.insert(0, str(ROOT / "src"))
    os.environ["TZ"] = "Europe/Istanbul"
    time.tzset()
    from blackboard_sync import i18n

    match = re.search(r'<html lang="([a-z]+)"', html)
    i18n.set_language(match.group(1) if match else "en")


def webui(fonts: list[Path]) -> str:
    """The Windows app's real main-window page (the Windows film's screen), in the film's font."""
    from blackboard_sync.windows import webui_page

    style = font_css(fonts) + ":root{--font:'Film',system-ui,sans-serif;--font-display:'Film',system-ui,sans-serif}"
    return webui_page.document(extra_style=style, lang="tr")


def states() -> str:
    """The app states the Windows film shows (scripts/webui-preview.py's fixtures), as a JS literal."""
    import json
    from datetime import datetime, timezone

    script = ROOT / "scripts" / "webui-preview.py"
    namespace = {"__name__": "webui_preview"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    now = datetime.now(timezone.utc).replace(hour=15, minute=14, second=0, microsecond=0)  # 18:14 in Istanbul
    return json.dumps(namespace["fixtures"](now), ensure_ascii=True).replace("</", "<\\/")


def build(film: Path, fonts: list[Path]) -> str:
    html = film.read_text(encoding="utf-8")
    replacements = {
        "{{FONT}}": font_css(fonts),
        "{{FILM_CSS}}": (PROMO / "film.css").read_text(encoding="utf-8"),
        "{{FILM_JS}}": (PROMO / "film.js").read_text(encoding="utf-8"),
        "{{LOGO}}": logo(),
    }
    if "{{WEBUI}}" in html or "{{STATES}}" in html:
        app_language(html)
        replacements["{{WEBUI}}"] = base64.b64encode(webui(fonts).encode("utf-8")).decode()
        replacements["{{STATES}}"] = states()
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html.replace("{{ICONS}}", icon_sprite(html))


def chromium() -> str | None:
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root:
        return None
    return next((str(p) for p in sorted(Path(root).glob("chromium-*/chrome-linux*/chrome"), reverse=True)), None)


def main(argv=None) -> int:
    args = parse_args(argv)
    html = build(args.film, args.font)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium())
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.set_content(html, wait_until="load")
        page.evaluate("document.fonts.ready")
        film = page.evaluate("window.FILM")
        if (film["width"], film["height"]) != (1080, 1350):
            page.set_viewport_size({"width": film["width"], "height": film["height"]})
        if hasattr(page, "evaluate") and page.evaluate("typeof window.ready === 'function'"):
            page.evaluate("window.ready()")
        fps = args.fps or film["fps"]
        if args.still:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            for t in args.still:
                page.evaluate(f"window.seek({t})")
                path = args.out_dir / f"{args.film.stem}-{t:06.2f}.png"
                page.screenshot(path=str(path))
                print(path)
        if args.out:
            end = args.end if args.end is not None else film["duration"]
            frames = int(round((end - args.start) * fps))
            encoder = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png",
                 "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", str(args.out)], stdin=subprocess.PIPE)
            for frame in range(frames):
                page.evaluate(f"window.seek({args.start + frame / fps})")
                encoder.stdin.write(page.screenshot(type="png"))
                if frame % (fps * 5) == 0:
                    print(f"{frame / fps:5.1f}s", file=sys.stderr, flush=True)
            encoder.stdin.close()
            if encoder.wait():
                raise SystemExit("ffmpeg failed")
            print(args.out)
        browser.close()
    for error in errors:
        print("page error:", error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
