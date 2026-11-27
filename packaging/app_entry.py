"""Entry point of the packaged "Blackboard Sync.app" and Windows app.

The menu bar / tray app runs syncs by re-invoking this same program with a CLI
subcommand (there is no separate ``python`` inside the bundle). With no
arguments, or with the app's own options, it starts the menu bar app (macOS) or
the tray app (Windows).
"""

import sys

# Hidden self-test used by CI: starts the Playwright driver the browser sign-in
# needs and loads the web component of the in-app sign-in window.
CHECK_LOGIN_RUNTIME = "--check-login-runtime"
# Hidden self-test used by CI on the installed MSIX package: package identity and
# the start-at-login startup task (see docs/MSIX.md).
CHECK_PACKAGE = "--check-package"
# Hidden self-test used by CI: draws a PDF note with the bundled fonts.
CHECK_NOTE_PDF = "--check-note-pdf"
CHECK_GOOGLE_CALENDAR = "--check-google-calendar"
# Hidden self-test used by CI: loads the NotebookLM library, which is imported only by a run.
CHECK_NOTEBOOKLM = "--check-notebooklm"
# Hidden self-test for the Mac App Store ("mas") sandboxed bundle: verifies App Sandbox
# container paths, onboarding MainWindow controls, WKWebView + persistent data store,
# security-scoped bookmarks, SMAppService, loopback OAuth socket, and notifications.
CHECK_MAS_SANDBOX = "--check-mas-sandbox"
CLI_COMMANDS = {
    "login", "refresh-session", "sync", "check", "uninstall", "calendar", "notebooklm",
    "--version", "-h", "--help",
}
# CLI options that come before the subcommand; the menu bar app passes the
# school from its settings window as ``--base-url URL sync ...``.
CLI_GLOBAL_OPTIONS = {"--base-url", "--data-dir", "-v", "--verbose"}


def _has_aqua_session() -> bool:
    import subprocess

    try:
        res = subprocess.run(
            ["/bin/launchctl", "managername"],
            capture_output=True,
            text=True,
            timeout=3,
            stdin=subprocess.DEVNULL,
        )
        return res.returncode == 0 and res.stdout.strip() == "Aqua"
    except Exception:
        return False


def _check_mas_sandbox() -> int:
    import json
    import os
    import socket
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path

    from blackboard_sync import ai_launcher, demo, licensing, login, macos_bookmarks, system, updater
    from blackboard_sync.config import Config
    from blackboard_sync.menubar import jobs, launchagent, main_window_model as main_model, settings_form
    from blackboard_sync.menubar.model import AppModel

    aqua = _has_aqua_session()
    container_id = os.environ.get(licensing.SANDBOX_CONTAINER_ENV, "")
    home = Path.home()
    real_home = system.real_user_home()
    data_dir = system.default_data_dir()

    # Verify kernel sandbox denies writing to real home root when sandboxed.
    outside_denied = False
    if container_id:
        probe = real_home / ".bbsync-mas-sandbox-probe-should-fail"
        try:
            probe.write_text("x", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except PermissionError:
            outside_denied = True

    # Verify 127.0.0.1 loopback bind/listen (network.server for Google Calendar OAuth).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        loopback_port = srv.getsockname()[1]

    # Verify onboarding form, MainStatus, and security-scoped bookmark round-trip.
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(home)) as tmp:
        tmp_root = Path(tmp)
        cfg = Config(data_dir=tmp_root / "data", dest=tmp_root / "Docs")
        now = datetime.now(timezone.utc)
        form = settings_form.initial_values(None, jobs.effective_settings(cfg), autostart=False)
        model = AppModel(dest=cfg.dest, now=now, configured=False)
        status = main_model.main_status(model, now)
        onboarding_ok = (
            form.base_url == ""
            and form.dest == ""
            and form.autostart is False
            and status.first_run is True
            and status.shows_demo is True
            and status.shows_notebooklm is False
        )
        if aqua:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSOpenPanel
            from blackboard_sync.menubar.main_window import MainWindow

            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            win = MainWindow(
                form,
                status,
                on_submit=lambda *_a: None,
                on_action=lambda *_a: None,
                on_close=lambda: None,
                on_values=lambda: form,
                on_open=lambda *_a: None,
                on_reveal=lambda *_a: None,
                on_deadlines=lambda: None,
                on_deadline=lambda *_a: None,
                on_announcements=lambda: (),
                on_open_announcement=lambda *_a: None,
                on_courses=lambda: (),
                on_course_toggle=lambda *_a: None,
                on_section=lambda *_a: None,
            )
            panel = NSOpenPanel.openPanel()
            onboarding_ok = onboarding_ok and (
                not bool(win.start_dest.isEditable())
                and not bool(win.dest_field.isEditable())
                and not bool(win.demo_button.isHidden())
                and str(win.demo_button.title()) == "Try the demo"
                and panel is not None
            )

        bm_folder = tmp_root / "ChosenFolder"
        bm_folder.mkdir()
        saved_bm = macos_bookmarks.save_bookmark(cfg.data_dir, bm_folder)
        macos_bookmarks.release_all()
        resolved_bm = macos_bookmarks.activate_saved_bookmark(cfg.data_dir)
        macos_bookmarks.release_all()
        bookmark_ok = resolved_bm is not None and resolved_bm.resolve() == saved_bm.resolve()

    # Verify WKWebView login runtime (and live WKWebsiteDataStore when Aqua WindowServer is attached).
    wk_ok = login.check_runtime() == "WKWebView"
    if aqua:
        from WebKit import WKWebsiteDataStore, WKWebView, WKWebViewConfiguration

        wk_cfg = WKWebViewConfiguration.alloc().init()
        wk_store = WKWebsiteDataStore.defaultDataStore()
        wk_cfg.setWebsiteDataStore_(wk_store)
        wk_view = WKWebView.alloc().initWithFrame_configuration_(((0, 0), (400, 300)), wk_cfg)
        wk_ok = wk_ok and wk_view is not None and bool(wk_store.isPersistent()) and wk_store.httpCookieStore() is not None

    sm_installed = launchagent.is_installed()
    notification_status = "skipped_headless"
    if aqua:
        import rumps

        try:
            rumps.notification("Blackboard Sync", None, "Mac App Store sandbox self-test")
            notification_status = "posted"
        except RuntimeError as exc:
            notification_status = f"runtime_error_handled:{exc}"

    summary = {
        "aqua_session": aqua,
        "distribution": licensing.current_distribution(),
        "is_mas_packaged": licensing.is_mas_packaged(),
        "sandbox_container_id": container_id,
        "home": str(home),
        "real_user_home": str(real_home),
        "default_data_dir": str(data_dir),
        "outside_container_write_denied": outside_denied,
        "loopback_listen_port": loopback_port,
        "onboarding_ok": onboarding_ok,
        "security_scoped_bookmark_ok": bookmark_ok,
        "wkwebview_runtime_ok": wk_ok,
        "smappservice_queried": isinstance(sm_installed, bool),
        "updater_enabled": updater.enabled(),
        "store_update_url": updater.store_update_url(),
        "ai_copy_command_sample": ai_launcher.copy_command_text(Path("/tmp/2026-2027 Fall"), ai_launcher.TOOLS["claude"]),
        "demo_base_url": demo.DEMO_BASE_URL,
        "notification_status": notification_status,
    }
    print(json.dumps(summary, indent=2))
    ok = (
        summary["distribution"] == "mas"
        and summary["is_mas_packaged"] is True
        and summary["onboarding_ok"] is True
        and summary["security_scoped_bookmark_ok"] is True
        and summary["wkwebview_runtime_ok"] is True
        and summary["updater_enabled"] is False
    )
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if args == [CHECK_LOGIN_RUNTIME]:
        from blackboard_sync import licensing
        from blackboard_sync.login import check_runtime

        web_view = check_runtime()
        if licensing.is_mas():
            print(f"login runtime ok ({web_view})")
        else:
            print(f"login runtime ok (Playwright, {web_view})")
        return 0
    if args == [CHECK_GOOGLE_CALENDAR]:
        from blackboard_sync.gcal import oauth_client_settings

        client = oauth_client_settings()
        if not client.get("client_id") or not client.get("client_secret"):
            print("Google Calendar client configuration is missing.", file=sys.stderr)
            return 1
        print("Google Calendar client configuration OK.")
        return 0
    if args == [CHECK_NOTE_PDF]:
        from blackboard_sync.notepdf import check_runtime as check_note_pdf

        print(check_note_pdf())
        return 0
    if args == [CHECK_NOTEBOOKLM]:
        from blackboard_sync.notebooklm.gateway import check_runtime as check_notebooklm

        print(check_notebooklm())
        return 0
    if args == [CHECK_MAS_SANDBOX] and sys.platform == "darwin":
        return _check_mas_sandbox()
    if args == [CHECK_PACKAGE] and sys.platform == "win32":
        from blackboard_sync.windows.autostart import check_package

        print(check_package())
        return 0
    if args and (args[0] in CLI_COMMANDS or args[0].split("=", 1)[0] in CLI_GLOBAL_OPTIONS):
        from blackboard_sync.cli import main as cli_main

        return cli_main(args)
    if sys.platform == "win32":
        # Sets up windows-tray.log before the tray app is imported.
        from blackboard_sync.windows.startup import run as tray_main

        return tray_main(args)
    from blackboard_sync.menubar.app import main as menubar_main

    return menubar_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
