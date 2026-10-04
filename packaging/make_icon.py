"""Build the app icons from assets/icon/logo.png.

Writes assets/icon/app.icns (macOS: logo on a rounded dark-slate plate with the
standard macOS icon padding) and assets/icon/app.ico (Windows: the logo without
a plate, which reads larger at 16-48 px). Both are committed; run this after
changing logo.png. Needs Pillow, and iconutil (macOS) for the .icns.
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icon"
SLATE_TOP, SLATE_BOTTOM = (15, 23, 42), (30, 41, 59)  # #0F172A -> #1E293B


def _trimmed_logo() -> Image.Image:
    logo = Image.open(ICON_DIR / "logo.png").convert("RGBA")
    return logo.crop(logo.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())


def _fit(image: Image.Image, box: int) -> Image.Image:
    scale = box / max(image.size)
    return image.resize(
        (round(image.width * scale), round(image.height * scale)), Image.LANCZOS
    )


def _paste_centered(canvas: Image.Image, image: Image.Image, dy: int = 0) -> None:
    canvas.alpha_composite(
        image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2 + dy)
    )


def mac_icon(size: int = 1024) -> Image.Image:
    """Logo on a rounded-square plate: 824/1024 plate, 185 px corners (Apple's template)."""
    scale = 2  # draw at 2x, then downsample for smooth edges
    big = size * scale
    plate = round(big * 824 / 1024)
    margin = (big - plate) // 2
    gradient = Image.linear_gradient("L").resize((plate, plate))  # black top -> white bottom
    fill = ImageChops.composite(
        Image.new("RGB", (plate, plate), SLATE_BOTTOM),
        Image.new("RGB", (plate, plate), SLATE_TOP),
        gradient,
    ).convert("RGBA")
    mask = Image.new("L", (plate, plate), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, plate - 1, plate - 1), radius=round(big * 185 / 1024), fill=255
    )
    fill.putalpha(mask)
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    canvas.alpha_composite(fill, (margin, margin))
    _paste_centered(canvas, _fit(_trimmed_logo(), round(plate * 0.72)))
    return canvas.resize((size, size), Image.LANCZOS)


def plain_icon(size: int = 256) -> Image.Image:
    canvas = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    _paste_centered(canvas, _fit(_trimmed_logo(), round(size * 4 * 0.94)))
    return canvas.resize((size, size), Image.LANCZOS)


def write_icns(out: Path) -> None:
    master = mac_icon(1024)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "app.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            master.resize((base, base), Image.LANCZOS).save(iconset / f"icon_{base}x{base}.png")
            master.resize((base * 2, base * 2), Image.LANCZOS).save(
                iconset / f"icon_{base}x{base}@2x.png"
            )
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)


def write_ico(out: Path) -> None:
    plain_icon(256).save(
        out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )


if __name__ == "__main__":
    write_icns(ICON_DIR / "app.icns")
    write_ico(ICON_DIR / "app.ico")
