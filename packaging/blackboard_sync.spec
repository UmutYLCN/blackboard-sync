# PyInstaller spec for "Blackboard Sync.app". Build with scripts/build-app.sh.
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "packaging"))
from google_oauth_bundle import oauth_datas
GOOGLE_OAUTH_DATAS = oauth_datas(ROOT)
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "blackboard_sync" / "__init__.py").read_text()
).group(1)

# The NotebookLM library loads much of itself lazily; its own CLI and servers stay out.
NOTEBOOKLM_IMPORTS = collect_submodules(
    "notebooklm",
    filter=lambda name: not name.startswith(("notebooklm.cli", "notebooklm.mcp", "notebooklm.server")),
)

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "assets" / "menubar" / "idle.png"), "assets/menubar"),
        (str(ROOT / "assets" / "menubar" / "idle@2x.png"), "assets/menubar"),
        # Fonts of the PDF notes (blackboard_sync.notepdf), with their license.
        (str(ROOT / "assets" / "fonts"), "assets/fonts"),
        # The main window's sidebar logo (transparent; the .icns has a background).
        (str(ROOT / "assets" / "icon" / "logo.png"), "assets/icon"),
        # The AI tools' logos on Home's card (ai_launcher.LOGO_DIR).
        (str(ROOT / "src" / "blackboard_sync" / "ai_logos"), "blackboard_sync/ai_logos"),
    ] + GOOGLE_OAUTH_DATAS + copy_metadata("notebooklm-py"),
    # The sync child run and the menu bar app are imported lazily by app_entry,
    # the in-app sign-in window (WKWebView) lazily by login.
    hiddenimports=[
        "blackboard_sync.cli",
        "blackboard_sync.min_version",
        "blackboard_sync.menubar.app",
        "rumps",
        "playwright.sync_api",
        "blackboard_sync.inapp_macos",
        # Each language's catalog, imported by name once the language is known.
        "blackboard_sync.locale_tr",
        "blackboard_sync.locale_es",
        "blackboard_sync.locale_fr",
        "blackboard_sync.locale_de",
        "blackboard_sync.locale_ar",
        "blackboard_sync.notebooklm.gateway",  # imported only when a run starts
        "WebKit",
    ] + NOTEBOOKLM_IMPORTS,
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
        "NSHumanReadableCopyright": "Copyright (c) 2026 Umut Yalcin. All rights reserved.",
        # Asked once, when iTerm2 is the terminal chosen on Home's AI card (ai_launcher).
        "NSAppleEventsUsageDescription": "Blackboard Sync asks iTerm2 to open a new window with your AI tool.",
    },
)
