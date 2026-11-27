# PyInstaller spec for the Mac App Store ("mas") build of "Blackboard Sync.app".
# Build and package with scripts/build-mas.sh (see docs/MAC_APP_STORE.md).
import os
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "packaging"))
from google_oauth_bundle import oauth_datas

GOOGLE_OAUTH_DATAS = oauth_datas(ROOT)
RAW_VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "blackboard_sync" / "__init__.py").read_text()
).group(1)
# App Store Connect requires a strict numeric X.Y.Z CFBundleShortVersionString.
SHORT_VERSION = re.match(r"(\d+\.\d+\.\d+)", RAW_VERSION).group(1)
BUILD_VERSION = os.environ.get("BBSYNC_MAS_BUILD_NUMBER") or SHORT_VERSION
BUNDLE_ID = (os.environ.get("BBSYNC_MAS_BUNDLE_ID") or "io.github.umutylcn.blackboard-sync.mas").strip()

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "assets" / "menubar" / "idle.png"), "assets/menubar"),
        (str(ROOT / "assets" / "menubar" / "idle@2x.png"), "assets/menubar"),
        # Fonts of the PDF notes (blackboard_sync.notepdf), with their license.
        (str(ROOT / "assets" / "fonts"), "assets/fonts"),
        # The main window's sidebar logo.
        (str(ROOT / "assets" / "icon" / "logo.png"), "assets/icon"),
        # The AI tools' logos on Home's card (copy-command mode in MAS).
        (str(ROOT / "src" / "blackboard_sync" / "ai_logos"), "blackboard_sync/ai_logos"),
        # Marks this frozen bundle as the Mac App Store flavor (licensing.MAS_MARKER_REL).
        (str(ROOT / "packaging" / "mas-distribution"), "assets"),
    ] + GOOGLE_OAUTH_DATAS,
    hiddenimports=[
        "blackboard_sync.cli",
        "blackboard_sync.demo",
        "blackboard_sync.inapp_macos",
        "blackboard_sync.licensing",
        "blackboard_sync.macos_bookmarks",
        "blackboard_sync.menubar.app",
        "rumps",
        "WebKit",
        # Each language's catalog, imported by name once the language is known.
        "blackboard_sync.locale_tr",
        "blackboard_sync.locale_es",
        "blackboard_sync.locale_fr",
        "blackboard_sync.locale_de",
        "blackboard_sync.locale_ar",
    ],
    excludes=[
        # MAS builds never ship Playwright's Node.js JIT driver or external Chromium automation.
        "playwright", "notebooklm",
        "pytest", "tkinter", "unittest", "pydoc_data",
        "PIL._avif", "PIL.AvifImagePlugin", "PIL._webp", "PIL.WebPImagePlugin",
        "PIL._imagingft", "PIL.ImageFont", "PIL._imagingcms", "PIL.ImageCms",
        "PIL._imagingtk", "PIL.ImageTk", "PIL._imagingmath", "PIL.ImageMath",
        "PIL._imagingmorph", "PIL.ImageMorph",
        "reportlab.graphics",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Blackboard Sync", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Blackboard Sync")
app = BUNDLE(
    coll,
    name="Blackboard Sync.app",
    bundle_identifier=BUNDLE_ID,
    icon=str(ROOT / "assets" / "icon" / "app.icns"),
    version=SHORT_VERSION,
    info_plist={
        "CFBundleName": "Blackboard Sync",
        "CFBundleDisplayName": "Blackboard Sync",
        "CFBundleIconFile": "app.icns",
        "CFBundleShortVersionString": SHORT_VERSION,
        "CFBundleVersion": BUILD_VERSION,
        "LSApplicationCategoryType": "public.app-category.education",
        "ITSAppUsesNonExemptEncryption": False,
        "LSUIElement": True,  # menu bar app: Dock icon appears while main window is open
        "LSMinimumSystemVersion": "13.0",  # SMAppService.mainApp requires macOS 13+
        "NSHumanReadableCopyright": "Copyright (c) 2026 Umut Yalcin. All rights reserved.",
    },
)
