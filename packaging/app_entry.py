"""Entry point of the packaged "Blackboard Sync.app".

The menu bar app runs syncs by re-invoking this same executable with a CLI
subcommand (there is no separate ``python`` inside the bundle). With no
arguments, or with the menu bar options, it starts the menu bar app.
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
    from blackboard_sync.menubar.app import main as menubar_main

    return menubar_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
