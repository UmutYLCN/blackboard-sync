"""Entry point of the packaged "Blackboard Sync.app" and Windows app.

The menu bar / tray app runs syncs by re-invoking this same program with a CLI
subcommand (there is no separate ``python`` inside the bundle). With no
arguments, or with the app's own options, it starts the menu bar app (macOS) or
the tray app (Windows).
"""

import sys

CLI_COMMANDS = {"login", "sync", "check", "--version", "-h", "--help"}
# CLI options that come before the subcommand; the menu bar app passes the
# school from its settings window as ``--base-url URL sync ...``.
CLI_GLOBAL_OPTIONS = {"--base-url", "--data-dir", "-v", "--verbose"}


def main() -> int:
    args = sys.argv[1:]
    if args and (args[0] in CLI_COMMANDS or args[0].split("=", 1)[0] in CLI_GLOBAL_OPTIONS):
        from blackboard_sync.cli import main as cli_main

        return cli_main(args)
    if sys.platform == "win32":
        from blackboard_sync.windows.app import main as tray_main

        return tray_main(args)
    from blackboard_sync.menubar.app import main as menubar_main

    return menubar_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
