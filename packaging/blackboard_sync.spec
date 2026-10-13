# PyInstaller spec for "Blackboard Sync.app". Build with scripts/build-app.sh.
import re
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "blackboard_sync" / "__init__.py").read_text()
).group(1)

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "assets" / "menubar" / "idle.png"), "assets/menubar"),
        (str(ROOT / "assets" / "menubar" / "idle@2x.png"), "assets/menubar"),
        # Fonts of the PDF notes (blackboard_sync.notepdf), with their license.
        (str(ROOT / "assets" / "fonts"), "assets/fonts"),
    ],
    # The sync child run and the menu bar app are imported lazily by app_entry,
    # the in-app sign-in window (WKWebView) lazily by login.
    hiddenimports=[
        "blackboard_sync.cli",
        "blackboard_sync.menubar.app",
        "rumps",
        "playwright.sync_api",
        "blackboard_sync.inapp_macos",
        "WebKit",
    ],
    excludes=[
        "pytest", "tkinter", "unittest", "pydoc_data",
        # ReportLab (the PDF notes) imports only PIL.Image and never opens an image
        # for them; Pillow's other native parts and their libraries (AVIF, WebP,
        # FreeType, HarfBuzz, LittleCMS, ...) would add about 6 MB to the .dmg.
        # Pillow skips image plugins it cannot import.
        "PIL._avif", "PIL.AvifImagePlugin", "PIL._webp", "PIL.WebPImagePlugin",
        "PIL._imagingft", "PIL.ImageFont", "PIL._imagingcms", "PIL.ImageCms",
        "PIL._imagingtk", "PIL.ImageTk", "PIL._imagingmath", "PIL.ImageMath",
        "PIL._imagingmorph", "PIL.ImageMorph",
        # Charts and barcodes; a note never draws one.
        "reportlab.graphics",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Blackboard Sync", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Blackboard Sync")
app = BUNDLE(
    coll,
    name="Blackboard Sync.app",
    bundle_identifier="io.github.umutylcn.blackboard-sync",
    icon=str(ROOT / "assets" / "icon" / "app.icns"),
    version=VERSION,
    info_plist={
        "CFBundleName": "Blackboard Sync",
        "CFBundleDisplayName": "Blackboard Sync",
        "CFBundleIconFile": "app.icns",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSUIElement": True,  # menu bar app: no Dock icon
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "Copyright (c) 2026 Umut Yalcin. MIT License.",
    },
)
