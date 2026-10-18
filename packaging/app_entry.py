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
CLI_COMMANDS = {"login", "sync", "check", "past-terms", "uninstall", "calendar", "--version", "-h", "--help"}
# CLI options that come before the subcommand; the menu bar app passes the
# school from its settings window as ``--base-url URL sync ...``.
CLI_GLOBAL_OPTIONS = {"--base-url", "--data-dir", "-v", "--verbose"}


def main() -> int:
    args = sys.argv[1:]
    if args == [CHECK_LOGIN_RUNTIME]:
        from blackboard_sync.login import check_runtime

        web_view = check_runtime()
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
