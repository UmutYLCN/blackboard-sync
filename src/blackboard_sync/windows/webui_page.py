"""The WebView2 main window's page: one self-contained HTML document, no GUI code.

``webui/index.html`` is a template; ``document`` puts the stylesheet, the script
and the icons into it, so the page loads nothing from disk or the network and
works the same under pywebview (``html=``) and in the preview
(``scripts/webui-preview.py``). The Content-Security-Policy allows only the
style and script carrying this launch's random nonce: text the page shows (an
announcement title, a file name) can never become markup or code.

Icons are Material Symbols Rounded (Apache-2.0, ``webui/icons/LICENSE``).
"""

from __future__ import annotations

import base64
import re
import secrets
from pathlib import Path

ASSETS = Path(__file__).with_name("webui")
ICON_DIR = ASSETS / "icons"
_PATH = re.compile(r'<path d="([^"]+)"')


def csp(nonce: str) -> str:
    """No markup can bring a script, style or request of its own.

    'unsafe-eval' is there for pywebview alone: its bridge builds the ``api`` functions with
    ``new Function`` and returns every result through ``evaluate_js``, which is an ``eval``.
    That reaches only code already running (ours and pywebview's); ``app.js`` never evaluates
    a string (``tests/test_webui.py`` checks).
    """
    return (f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}' 'unsafe-eval'; "
            "img-src data:; font-src data:; base-uri 'none'; form-action 'none'")


def icon_sprite() -> str:
    """Every icon once, as ``<symbol id="i-NAME">``; the page draws them with ``<use>``."""
    symbols = []
    for path in sorted(ICON_DIR.glob("*.svg")):
        match = _PATH.search(path.read_text(encoding="utf-8"))
        if match:
            symbols.append(f'<symbol id="i-{path.stem}" viewBox="0 -960 960 960"><path d="{match.group(1)}"/></symbol>')
    # ``hidden`` does not hide an <svg> (it is not an HTML element); the class gives it no size.
    return '<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true">' + "".join(symbols) + "</svg>"


def new_nonce() -> str:
    return secrets.token_urlsafe(18)


def logo() -> str:
    """The app's logo (``webui/logo.png``, 128 px) as a data URI: the page loads no files."""
    return "data:image/png;base64," + base64.b64encode((ASSETS / "logo.png").read_bytes()).decode()


def document(nonce: str | None = None, extra_style: str = "", extra_script: str = "", lang: str = "en",
             theme: str = "system") -> str:
    """The whole page; ``theme`` is ``Settings.theme`` (the page follows later changes itself).

    ``extra_style``/``extra_script`` are for the preview only (its font, a fixed state).
    """
    nonce = nonce or new_nonce()
    template = (ASSETS / "index.html").read_text(encoding="utf-8")
    style = (ASSETS / "app.css").read_text(encoding="utf-8") + extra_style
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    before = f'<script nonce="{nonce}">{extra_script}</script>' if extra_script else ""
    replacements = {
        "{{LANG}}": lang,
        "{{THEME}}": theme,
        "{{LOGO}}": logo(),
        "{{CSP}}": csp(nonce),
        "{{STYLE}}": f'<style nonce="{nonce}">{style}</style>',
        "{{ICONS}}": icon_sprite(),
        "{{SCRIPT}}": f'{before}<script nonce="{nonce}">{script}</script>',
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template
