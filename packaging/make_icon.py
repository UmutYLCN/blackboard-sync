"""Ensure the Windows app icon exists as a multi-size .ico."""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ICO = ROOT / "assets" / "icon" / "icon.ico"

out = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE_ICO
out.parent.mkdir(parents=True, exist_ok=True)
if SOURCE_ICO.exists() and SOURCE_ICO.resolve() != out.resolve():
    shutil.copyfile(SOURCE_ICO, out)

