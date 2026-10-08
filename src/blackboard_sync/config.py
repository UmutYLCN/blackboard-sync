"""Runtime configuration: where things live and which Blackboard to talk to.

Every setting has a default, which the settings saved by the menu bar app's
settings window (``settings.json`` in the data directory) replace. An
environment variable overrides both, and a command-line flag overrides that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from blackboard_sync.settings import load_settings, settings_path
from blackboard_sync.system import default_data_dir, default_dest, make_private_dir, sync_root

DEFAULT_BASE_URL = "https://blackboard.istun.edu.tr"
# macOS: ~/Documents/University and ~/Library/Application Support/blackboard-sync.
# Windows: <Documents>\University and %APPDATA%\blackboard-sync.
DEFAULT_DEST = default_dest()
DEFAULT_DATA_DIR = default_data_dir()
DEFAULT_ANNOUNCEMENTS_FOLDER = "Duyurular"


@dataclass
class Config:
    base_url: str = DEFAULT_BASE_URL
    dest: Path = DEFAULT_DEST
    data_dir: Path = DEFAULT_DATA_DIR
    announcements_folder: str = DEFAULT_ANNOUNCEMENTS_FOLDER

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.dest = Path(self.dest).expanduser()
        self.data_dir = Path(self.data_dir).expanduser()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, data_dir: Path | None = None) -> "Config":
        """Defaults, then saved settings, then environment variables.

        ``data_dir`` (the ``--data-dir`` flag) wins over ``BBSYNC_DATA_DIR`` and
        decides which saved settings are read.
        """
        env = os.environ if env is None else env
        data_dir = Path(data_dir or env.get("BBSYNC_DATA_DIR") or DEFAULT_DATA_DIR).expanduser()
        saved = load_settings(data_dir)
        return cls(
            base_url=env.get("BBSYNC_BASE_URL") or (saved.base_url if saved else DEFAULT_BASE_URL),
            dest=Path(env.get("BBSYNC_DEST") or (saved.dest if saved else DEFAULT_DEST)),
            data_dir=data_dir,
            announcements_folder=env.get(
                "BBSYNC_ANNOUNCEMENTS_FOLDER", DEFAULT_ANNOUNCEMENTS_FOLDER
            ),
        )

    @property
    def root(self) -> Path:
        """The folder the term folders go in: ``dest/University`` (``system.sync_root``).

        ``dest`` stays the folder the student chose; every file is read and
        written relative to this one.
        """
        return sync_root(self.dest)

    @property
    def session_file(self) -> Path:
        return self.data_dir / "session.json"

    @property
    def profile_dir(self) -> Path:
        return self.data_dir / "browser-profile"

    @property
    def inapp_profile_dir(self) -> Path:
        """The Windows sign-in window's web data (macOS keeps it in WebKit's store)."""
        return self.data_dir / "inapp-profile"

    @property
    def settings_file(self) -> Path:
        return settings_path(self.data_dir)

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def last_run_file(self) -> Path:
        return self.data_dir / "last-run.json"

    @property
    def lock_file(self) -> Path:
        return self.data_dir / "sync.lock"

    def ensure_data_dir(self) -> Path:
        """Create the private data directory (owner-only permissions)."""
        return make_private_dir(self.data_dir)
