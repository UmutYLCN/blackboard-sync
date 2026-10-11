"""Lay out the MSIX package of the Windows app for ``makeappx pack``.

    python packaging/msix/make_layout.py "dist/Blackboard Sync" build/msix

copies the PyInstaller build into the layout folder, writes AppxManifest.xml
from AppxManifest.xml.in (identity from identity.toml, version from the app) and
the logos Windows and the Store need, drawn from assets/icon/logo.png. Run by
scripts/build-msix.ps1; needs Pillow (a dependency of the Windows app).
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from string import Template
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOGO = ROOT / "assets" / "icon" / "logo.png"
IDENTITY_KEYS = ("name", "publisher", "publisher_display_name", "display_name")
# File name -> (width, height, logo height as a share of the image height).
ASSETS = {
    "StoreLogo.png": (50, 50, 1.0),
    "Square44x44Logo.png": (44, 44, 1.0),
    "Square150x150Logo.png": (150, 150, 0.6),
    "Wide310x150Logo.png": (310, 150, 0.6),
}
VERSION_PART_MAX = 65535


def app_version() -> str:
    text = (ROOT / "src" / "blackboard_sync" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def msix_version(version: str) -> str:
    """1.5.1 -> 1.5.1.0. The Store keeps the fourth part for itself (always 0).

    A pre-release suffix (1.6.0rc1) is dropped: MSIX versions are numbers only,
    so a test package of a pre-release carries the version it leads up to.
    """
    match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?![.\d])", version)
    if not match:
        raise ValueError(f"Not a release version: {version!r}")
    parts = [int(part or 0) for part in match.groups()]
    if any(part > VERSION_PART_MAX for part in parts):
        raise ValueError(f"MSIX version parts must be at most {VERSION_PART_MAX}: {version!r}")
    return ".".join(str(part) for part in (*parts, 0))


def load_identity(path: Path = HERE / "identity.toml") -> dict[str, str]:
    identity = tomllib.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in IDENTITY_KEYS if not identity.get(key)]
    if missing:
        raise ValueError(f"{path.name} is missing {', '.join(missing)}")
    return {key: identity[key] for key in IDENTITY_KEYS}


def manifest(identity: dict[str, str], version: str) -> str:
    values = {key: escape(value, {'"': "&quot;"}) for key, value in identity.items()}
    text = Template((HERE / "AppxManifest.xml.in").read_text(encoding="utf-8")).substitute(
        values, version=version
    )
    ET.fromstring(text.encode("utf-8"))  # well-formed, or stop here rather than in makeappx
    return text


def placeholders(identity: dict[str, str]) -> list[str]:
    return [key for key, value in identity.items() if "PLACEHOLDER" in value]


def draw_asset(width: int, height: int, share: float):
    from PIL import Image

    logo = Image.open(LOGO).convert("RGBA")
    logo = logo.crop(logo.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
    box = round(min(width, height) * share)
    scale = box / max(logo.size)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(logo, ((width - logo.width) // 2, (height - logo.height) // 2))
    return canvas


def make_layout(app_dir: Path, layout: Path, identity: dict[str, str] | None = None) -> str:
    """Fill ``layout`` (replaced) and return the package version."""
    if not (app_dir / "Blackboard Sync.exe").is_file():
        raise FileNotFoundError(f"No PyInstaller build in {app_dir}")
    identity = identity or load_identity()
    version = msix_version(app_version())
    if layout.exists():
        shutil.rmtree(layout)
    shutil.copytree(app_dir, layout)
    (layout / "AppxManifest.xml").write_text(manifest(identity, version), encoding="utf-8")
    assets = layout / "Assets"
    assets.mkdir()
    for name, (width, height, share) in ASSETS.items():
        draw_asset(width, height, share).save(assets / name)
    return version


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    identity = load_identity()
    version = make_layout(Path(argv[0]), Path(argv[1]), identity)
    print(f"MSIX layout {argv[1]}: version {version}")
    for key in placeholders(identity):
        print(f"note: {key} is a placeholder (packaging/msix/identity.toml); fine for a test package only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
