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
    excludes=["pytest", "tkinter", "unittest", "pydoc_data"],
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
