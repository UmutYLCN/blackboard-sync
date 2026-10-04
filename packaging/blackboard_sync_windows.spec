# PyInstaller spec for the Windows tray app. Build with scripts/build-windows.ps1.
import re
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "blackboard_sync" / "__init__.py").read_text()
).group(1)
ICON = str(ROOT / "assets" / "icon" / "icon.ico")

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT / "src")],
    # The sync child run and the tray app are imported lazily by app_entry, the
    # in-app sign-in window (pywebview on WebView2, through pythonnet) by login.
    # pyinstaller-hooks-contrib's pywebview hook bundles the WebView2 interop DLLs.
    hiddenimports=[
        "blackboard_sync.cli",
        "blackboard_sync.windows.app",
        "pystray._win32",
        "playwright.sync_api",
        "blackboard_sync.inapp_windows",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "clr",
    ],
    excludes=["pytest", "unittest", "pydoc_data"],
)
pyz = PYZ(a.pure)
# Two programs sharing one set of libraries: the windowed app, and a console
# twin that the app runs for CLI jobs (a windowed exe may lose its standard
# streams, and the job's JSON report is read from stdout).
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Blackboard Sync",
          console=False, icon=ICON)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="blackboard-sync-cli",
          console=True, icon=ICON)
coll = COLLECT(gui, cli, a.binaries, a.datas, name="Blackboard Sync")
