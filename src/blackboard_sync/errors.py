"""Exceptions and process exit codes."""

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
            f"{reason} Run `blackboard-sync login` to sign in to Blackboard."
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
