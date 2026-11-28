"""What a gateway hands back, and the waiting both gateways share; free of the library.

``gateway`` (the library, for the ``.dmg`` and Windows builds) and ``safari`` (the Mac App Store
build's Safari extension) both speak this, so ``runner`` never knows which one it has.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

FIRST_POLL, LAST_POLL = 3.0, 10.0  # seconds between looks at a file NotebookLM is processing


@dataclass(frozen=True)
class RemoteNotebook:
    id: str
    title: str


@dataclass(frozen=True)
class RemoteSource:
    id: str
    title: str
    status: str  # ready | processing | preparing | error | unknown


async def wait_ready(list_sources: Callable[[str], Awaitable[list[RemoteSource]]], notebook_id: str,
                     source_ids: list[str], timeout: float,
                     sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> dict[str, str]:
    """Each source's status once none is still processing, or at ``timeout``."""
    pending = set(source_ids)
    status: dict[str, str] = {}
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    interval = FIRST_POLL
    while True:
        for source in await list_sources(notebook_id):
            if source.id in pending:
                status[source.id] = source.status
        pending -= {source_id for source_id in pending if status.get(source_id) in ("ready", "error")}
        if not pending or loop.time() >= deadline:
            break
        await sleep(interval)
        interval = min(interval * 1.5, LAST_POLL)
    for source_id in pending:
        status.setdefault(source_id, "missing")
    return status
