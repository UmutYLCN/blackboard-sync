"""The only module that talks to NotebookLM; undocumented Google endpoints that may break.

``notebooklm-py`` is pinned and upgraded on purpose. Everything else depends on the small
``Gateway`` surface below, so a browser-driven fallback would replace this one file. The
library wraps a dead session in several classes, so ``translate_exception`` sorts every failure
into what the caller can do: sign in again, try again, or give up on this file.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from notebooklm import (
    AuthError,
    ConfigurationError,
    NetworkError,
    NotebookLMClient,
    RateLimitError,
    RPCTimeoutError,
    ServerError,
    SourceAddError,
    WaitTimeoutError,
)

from blackboard_sync.errors import (
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMRateLimited,
    NotebookLMTransient,
)
from blackboard_sync.notebooklm.planner import nfc

TRANSIENT = (NetworkError, RateLimitError, ServerError, RPCTimeoutError, WaitTimeoutError, SourceAddError,
             asyncio.TimeoutError)
RATE_MARKERS = ("429", "rate limit", "rate-limit", "too many requests", "resource_exhausted", "resource exhausted")
AUTH_MARKERS = ("unauthenticated", "authentication expired", "signed-out", "notebooklm login")
FIRST_POLL, LAST_POLL = 3.0, 10.0  # seconds between looks at a file NotebookLM is processing
# Google only renews a session when asked, and uploads alone do not ask, so a long run does.
KEEPALIVE_SECONDS = 600.0


@dataclass(frozen=True)
class RemoteNotebook:
    id: str
    title: str


@dataclass(frozen=True)
class RemoteSource:
    id: str
    title: str
    status: str  # ready | processing | preparing | error | unknown


def check_runtime() -> str:
    """For the packaged app's self-test: this module and the library loaded, version included."""
    return f"notebooklm ok ({version('notebooklm-py')})"


def looks_like_auth_failure(exc: BaseException | None) -> bool:
    for _ in range(5):
        if exc is None:
            return False
        if isinstance(exc, AuthError) or any(marker in str(exc).lower() for marker in AUTH_MARKERS):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def looks_like_rate_limit(exc: BaseException | None) -> bool:
    """The library also wraps a 429 in its other errors, so the chain counts as well."""
    seen = 0
    while exc is not None and seen < 8:
        text = str(exc).lower()
        if isinstance(exc, RateLimitError) or any(marker in text for marker in RATE_MARKERS):
            return True
        exc, seen = exc.__cause__ or exc.__context__, seen + 1
    return False


def translate_exception(exc: Exception) -> Exception:
    if isinstance(exc, (NotebookLMLoginRequired, NotebookLMTransient, NotebookLMPermanent)):
        return exc
    if looks_like_auth_failure(exc):
        return NotebookLMLoginRequired()
    if isinstance(exc, TRANSIENT):
        if looks_like_rate_limit(exc):
            return NotebookLMRateLimited(f"{type(exc).__name__}: {exc}")
        return NotebookLMTransient(f"{type(exc).__name__}: {exc}")
    return NotebookLMPermanent(f"{type(exc).__name__}: {exc}")


class Gateway:
    def __init__(self, session: Path):
        self.session = session
        self._context = None
        self._client = None
        self._notebooks: list[RemoteNotebook] | None = None

    async def open(self) -> "Gateway":
        """Start a client on the session; listing the notebooks proves Google still accepts it."""
        try:
            context = NotebookLMClient.from_storage(path=str(self.session), keepalive=KEEPALIVE_SECONDS)
            self._client = await context.__aenter__()
        except (AuthError, ConfigurationError, FileNotFoundError, ValueError) as exc:
            raise NotebookLMLoginRequired() from exc
        except Exception as exc:
            raise translate_exception(exc) from exc
        self._context = context
        try:
            await self.list_notebooks()
        except Exception:
            await self.close()
            raise
        return self

    async def close(self) -> None:
        if self._context is not None:
            context, self._context, self._client = self._context, None, None
            await context.__aexit__(None, None, None)

    async def source_limit(self) -> int | None:
        """The account's limit per notebook; None when it cannot be read."""
        try:
            return (await self._client.settings.get_account_limits()).source_limit
        except Exception:
            return None

    async def list_notebooks(self) -> list[RemoteNotebook]:
        if self._notebooks is None:
            try:
                raw = await self._client.notebooks.list()
            except Exception as exc:
                raise translate_exception(exc) from exc
            self._notebooks = [RemoteNotebook(notebook.id, nfc(notebook.title or "").strip()) for notebook in raw]
        return self._notebooks

    async def find_notebooks(self, title: str) -> list[RemoteNotebook]:
        wanted = nfc(title).strip()
        return [notebook for notebook in await self.list_notebooks() if notebook.title == wanted]

    async def create_notebook(self, title: str) -> RemoteNotebook:
        try:
            notebook = await self._client.notebooks.create(title)
        except Exception as exc:
            raise translate_exception(exc) from exc
        created = RemoteNotebook(notebook.id, nfc(notebook.title or title).strip())
        (await self.list_notebooks()).append(created)
        return created

    async def list_sources(self, notebook_id: str) -> list[RemoteSource]:
        try:
            raw = await self._client.sources.list(notebook_id)
        except Exception as exc:
            raise translate_exception(exc) from exc
        return [RemoteSource(source.id, nfc(source.title or ""), getattr(source.status, "name", "unknown").lower())
                for source in raw]

    async def add_file(self, notebook_id: str, path: Path, title: str) -> str:
        try:
            source = await self._client.sources.add_file(notebook_id, Path(path), title=title, wait=False)
        except Exception as exc:
            raise translate_exception(exc) from exc
        return source.id

    async def wait_ready(self, notebook_id: str, source_ids: list[str], timeout: float) -> dict[str, str]:
        """Each source's status once none is still processing, or at ``timeout``."""
        pending = set(source_ids)
        status: dict[str, str] = {}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        interval = FIRST_POLL
        while True:
            for source in await self.list_sources(notebook_id):
                if source.id in pending:
                    status[source.id] = source.status
            pending -= {source_id for source_id in pending if status.get(source_id) in ("ready", "error")}
            if not pending or loop.time() >= deadline:
                break
            await asyncio.sleep(interval)
            interval = min(interval * 1.5, LAST_POLL)
        for source_id in pending:
            status.setdefault(source_id, "missing")
        return status
