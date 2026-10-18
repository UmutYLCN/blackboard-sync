"""Exceptions and process exit codes."""

from blackboard_sync.i18n import tr

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_LOGIN_REQUIRED = 3
EXIT_LOCKED = 4


class BlackboardSyncError(Exception):
    """Base class for expected, user-facing failures."""

    exit_code = EXIT_ERROR


class LoginRequired(BlackboardSyncError):
    """The stored session is missing or no longer accepted by Blackboard."""

    exit_code = EXIT_LOGIN_REQUIRED

    def __init__(self, reason: str):
        super().__init__(
            f"{reason} " + tr("Run `blackboard-sync login` to sign in to Blackboard.")
        )
        self.reason = reason


class AlreadyRunning(BlackboardSyncError):
    exit_code = EXIT_LOCKED


class ApiError(BlackboardSyncError):
    """A Blackboard request failed for a reason other than an expired session."""

    def __init__(self, status: int, url: str, message: str = ""):
        detail = f": {message}" if message else ""
        super().__init__(f"HTTP {status} for {url}{detail}")
        self.status = status
        self.url = url


class SkippedMedia(Exception):
    """A media or oversized file was not downloaded; the note links to Blackboard.

    Not an error: it carries no exit code and is never reported as a warning.
    """

    def __init__(
        self, url: str, name: str = "", content_type: str = "", *, reason: str = "media", size: int | None = None
    ):
        super().__init__(f"Not downloading {reason}: {name or url}")
        self.url = url
        self.name = name
        self.content_type = content_type
        self.reason = reason
        self.size = size


def human_size(size: int) -> str:
    """Format a byte count with Turkish decimal punctuation."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f}".replace(".", ",").rstrip("0").rstrip(",") + f" {unit}"
        value /= 1000
    return f"{value:.1f}".replace(".", ",") + " TB"
