"""How to start this program again: from source or from the packaged app.

The menu bar app runs syncs as child processes and registers itself as a login
item. From a checkout that means ``python -m ...``; inside the PyInstaller app
there is no separate Python, so the app's own executable is re-invoked (it
dispatches on its first argument, see ``packaging/app_entry.py``).
"""

from __future__ import annotations

import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def cli_command(*args: str, python: str | None = None) -> list[str]:
    """The command line for ``blackboard-sync <args>``."""
    if is_frozen() and python is None:
        return [sys.executable, *args]
    return [python or sys.executable, "-m", "blackboard_sync", *args]


def menubar_command(python: str | None = None) -> list[str]:
    """The command line that starts the menu bar app itself."""
    if is_frozen() and python is None:
        return [sys.executable]
    return [python or sys.executable, "-m", "blackboard_sync.menubar"]
