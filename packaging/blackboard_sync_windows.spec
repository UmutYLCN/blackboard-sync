# PyInstaller spec for the Windows tray app. Build with scripts/build-windows.ps1.
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "packaging"))
from google_oauth_bundle import oauth_datas
GOOGLE_OAUTH_DATAS = oauth_datas(ROOT)
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "blackboard_sync" / "__init__.py").read_text()
).group(1)
ICON = str(ROOT / "assets" / "icon" / "app.ico")

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT / "src")],
    # Fonts of the PDF notes (blackboard_sync.notepdf), with their license.
    datas=[(str(ROOT / "assets" / "fonts"), "assets/fonts")] + GOOGLE_OAUTH_DATAS,
    # The sync child run and the tray app are imported lazily by app_entry, the
    # in-app sign-in window (pywebview on WebView2, through pythonnet) by login.
    # pyinstaller-hooks-contrib's pywebview hook bundles the WebView2 interop DLLs.
    hiddenimports=[
        "blackboard_sync.cli",
        "blackboard_sync.windows.app",
        "pystray._win32",
        "playwright.sync_api",
        "blackboard_sync.inapp_windows",
        "blackboard_sync.locale_tr",  # Turkish, loaded once the language is known
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "clr",
        "send2trash.win.IFileOperationProgressSink",
        "win32cred",  # Google Calendar refresh tokens in Credential Manager
        "win32com.shell.shell",
        "win32com.server.policy",
    ],
    # reportlab.graphics: charts and barcodes, which the PDF notes never draw.
    excludes=["pytest", "unittest", "pydoc_data", "reportlab.graphics"],
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
