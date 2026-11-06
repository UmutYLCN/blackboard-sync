"""One run: plan every course, add what is new, say how it went.

Uploads run one at a time with a pause between them, and only a passing failure is retried.
Each file is saved to the state as soon as it is up, so a run stopped at any moment (Pause, the
app quitting) loses nothing. A file that fails is reported and the rest go on; an expired session
ends the run, since nothing else can work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from blackboard_sync import courses
from blackboard_sync.config import Config
from blackboard_sync.errors import (
    EXIT_ERROR,
    EXIT_LOCKED,
    EXIT_LOGIN_REQUIRED,
    EXIT_OK,
    AlreadyRunning,
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMTransient,
)
from blackboard_sync.i18n import ntr, tr
from blackboard_sync.notebooklm import planner, store
from blackboard_sync.notebooklm.planner import CoursePlan, CourseScan, FileAction
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock
from blackboard_sync.system import make_private_dir

log = logging.getLogger(__name__)

DELAY_SECONDS = 2.5  # between uploads
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 5.0  # waits of 5, 15 and 45 seconds
FALLBACK_SOURCE_LIMIT = 50  # the free plan's, when the account's cannot be read
PROCESSING_WAIT_SECONDS = 300.0
# Google's session dies if nothing renews it, and a term has weeks without new files. So an
# automatic run with nothing to add still opens the session this often; the library renews it.
SESSION_REFRESH_SECONDS = 12 * 60 * 60
EXIT_CODES = {"ok": EXIT_OK, "login_required": EXIT_LOGIN_REQUIRED, "locked": EXIT_LOCKED, "error": EXIT_ERROR}

Sleep = Callable[[float], Awaitable[None]]
Events = Callable[[dict], None]


@dataclass
class RunResult:
    status: str = "ok"  # ok | login_required | locked | error
    message: str = ""
    added: list[str] = field(default_factory=list)
    adopted: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    blocked: list[tuple[str, int, int]] = field(default_factory=list)  # title, overflow, limit
    ambiguous: list[str] = field(default_factory=list)
    processing_errors: list[str] = field(default_factory=list)
    still_processing: list[str] = field(default_factory=list)
    skipped: int = 0
    notebooks_created: int = 0
    worked: bool = True  # False: an automatic run found nothing new, so there is nothing to report

    def notice(self) -> str:
        """The one line that says what the student should know, most pressing first."""
        if self.blocked:
            title, overflow, limit = self.blocked[0]
            return tr("{course}: {n} over the {limit} source limit; nothing added.").format(
                course=title, n=overflow, limit=limit)
        if self.ambiguous:
            return tr("{course}: several notebooks have this name, so it was skipped.").format(
                course=self.ambiguous[0])
        failed = len(self.failed) + len(self.processing_errors)
        if failed:
            return ntr("{n} file could not be added; the next sync tries again.",
                       "{n} files could not be added; the next sync tries again.", failed).format(n=failed)
        return ""

    def last_run(self) -> dict:
        return {
            "status": self.status,
            "finished_at": store.utcnow_text(),
            "added": len(self.added),
            "skipped": self.skipped,
            "modified": len(self.modified),
            "blocked": len(self.blocked),
            "failed": len(self.failed) + len(self.processing_errors),
            "message": self.message or self.notice(),
        }


def wait_seconds(attempt: int) -> float:
    return RETRY_BASE_SECONDS * 3 ** (attempt - 1)


async def upload_with_retry(gateway, notebook_id: str, action: FileAction, sleep: Sleep) -> str:
    """Add one file, retrying only passing failures.

    A failed add can still have landed, and adding it again would make a duplicate, so the
    notebook is looked at before each retry. It may still carry the bare file name then.
    """
    title = action.file.rel
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await gateway.add_file(notebook_id, action.file.path, title)
        except NotebookLMTransient as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            log.warning("attempt %d of %d failed: %s", attempt, MAX_ATTEMPTS, exc)
            await sleep(wait_seconds(attempt))
            names = {title, action.file.path.name}
            for source in await gateway.list_sources(notebook_id):
                if source.title in names and source.status in ("ready", "processing"):
                    return source.id
    raise AssertionError("unreachable")


async def plan_all(scans: list[CourseScan], state: store.UploadState, gateway) -> list[CoursePlan]:
    """Read-only: the account's limit, the notebooks and the sources of each course."""
    limit = await gateway.source_limit() or FALLBACK_SOURCE_LIMIT
    plans = []
    for scan in scans:
        matches = await gateway.find_notebooks(scan.title)
        sources = await gateway.list_sources(matches[0].id) if len(matches) == 1 else None
        plans.append(planner.plan_course(scan, state, matches=matches, sources=sources, limit=limit))
    return plans


async def execute(plans: list[CoursePlan], state: store.UploadState, gateway, result: RunResult, sleep: Sleep,
                  events: Events) -> None:
    total = sum(len(plan.uploads) for plan in plans if plan.status == planner.READY)
    done = 0
    for plan in plans:
        scan = plan.course
        if plan.status == planner.BLOCKED:
            result.blocked.append((scan.title, plan.overflow, plan.limit))
            continue
        if plan.status == planner.AMBIGUOUS:
            result.ambiguous.append(scan.title)
            continue
        if plan.status != planner.READY:
            continue
        notebook_id = plan.notebook_id
        try:
            if plan.uploads and not notebook_id:
                notebook_id = (await gateway.create_notebook(scan.title)).id
                result.notebooks_created += 1
        except (NotebookLMTransient, NotebookLMPermanent) as exc:
            result.failed.extend((f"{scan.title}/{a.file.rel}", str(exc)) for a in plan.uploads)
            done += len(plan.uploads)
            continue
        if notebook_id:
            state.set_notebook(scan.folder, notebook_id)
            state.save()
        added: dict[str, str] = {}  # source id -> file
        for action in plan.actions:
            info = action.file
            label = f"{scan.title}/{info.rel}"
            if action.action == planner.TOUCHED:
                state.refresh(scan.folder, info.rel, size=info.size, mtime_ns=info.mtime_ns)
            elif action.action == planner.MODIFIED:
                result.modified.append(label)
            elif action.action == planner.ADOPT:
                try:
                    state.record(scan.folder, info.rel, notebook_id=notebook_id, source_id=action.source_id,
                                 size=info.size, mtime_ns=info.mtime_ns, sha256=store.sha256_file(info.path))
                    result.adopted.append(label)
                except OSError as exc:
                    result.failed.append((label, str(exc)))
            elif action.action == planner.UPLOAD:
                done += 1
                events({"event": "progress", "done": done, "total": total, "course": scan.title})
                try:
                    digest = action.sha256 or store.sha256_file(info.path)
                    source_id = await upload_with_retry(gateway, notebook_id, action, sleep)
                except (NotebookLMTransient, NotebookLMPermanent, OSError) as exc:
                    result.failed.append((label, str(exc)))
                else:
                    state.record(scan.folder, info.rel, notebook_id=notebook_id, source_id=source_id,
                                 size=info.size, mtime_ns=info.mtime_ns, sha256=digest)
                    state.save()
                    result.added.append(label)
                    added[source_id] = label
                await sleep(DELAY_SECONDS)
        state.save()
        if added:
            await _collect_processing(gateway, notebook_id, added, result)


async def _collect_processing(gateway, notebook_id: str, added: dict[str, str], result: RunResult) -> None:
    """A copy-protected or empty PDF only fails once NotebookLM has read it; report that too."""
    try:
        status = await gateway.wait_ready(notebook_id, list(added), PROCESSING_WAIT_SECONDS)
    except (NotebookLMTransient, NotebookLMPermanent) as exc:
        log.warning("could not check processing: %s", exc)
        result.still_processing.extend(added.values())
        return
    for source_id, value in status.items():
        if value == "error":
            result.processing_errors.append(added[source_id])
        elif value != "ready":
            result.still_processing.append(added[source_id])


async def open_gateway(config: Config):
    """The library is loaded here, with its home in the data directory; only a run needs it."""
    home = store.library_home(config)
    make_private_dir(home)
    os.environ["NOTEBOOKLM_HOME"] = str(home)
    from blackboard_sync.notebooklm.gateway import Gateway

    return await Gateway(store.session_file(config)).open()


async def _refresh_session(config: Config, opener) -> None:
    """Open and close the session if that was not done lately; only a lost session is news here."""
    session = store.session_file(config)
    if time.time() - session.stat().st_mtime < SESSION_REFRESH_SECONDS:
        return
    try:
        await (await opener(config)).close()
    except (NotebookLMTransient, NotebookLMPermanent) as exc:
        log.warning("could not refresh the session: %s", exc)
        return
    os.utime(session)


async def _run(config: Config, auto: bool, events: Events, opener, sleep: Sleep) -> RunResult:
    scans = planner.scan_courses(State.load(config.state_file, backup=False), config.root,
                                 courses.load_disabled(config))
    state = store.UploadState.load(store.state_file(config))
    result = RunResult(skipped=sum(len(scan.skipped) for scan in scans))
    todo = [scan for scan in scans if planner.has_new_files(scan, state)] if auto else scans
    if auto and not todo:
        await _refresh_session(config, opener)
        result.worked = False
        return result
    events({"event": "planning"})
    gateway = await opener(config)
    try:
        plans = await plan_all(todo, state, gateway)
        await execute(plans, state, gateway, result, sleep, events)
    finally:
        state.save()
        await gateway.close()
    os.utime(store.session_file(config))
    return result


def run(config: Config, *, auto: bool = False, events: Events = lambda event: None, opener=open_gateway,
        sleep: Sleep = asyncio.sleep) -> RunResult:
    """Add what is new and save how it went. Never raises for what can go wrong in a run.

    ``auto`` (after a Blackboard sync) looks only at the courses with something new, and needs
    no network without any, apart from keeping the session alive (``SESSION_REFRESH_SECONDS``).
    """
    config.ensure_data_dir()
    make_private_dir(config.notebooklm_dir)
    try:
        with run_lock(store.lock_file(config)):
            if not store.session_file(config).is_file():
                raise NotebookLMLoginRequired()
            result = asyncio.run(_run(config, auto, events, opener, sleep))
    except AlreadyRunning:
        return RunResult(status="locked", worked=False)
    except NotebookLMLoginRequired as exc:
        result = RunResult(status="login_required", message=str(exc))
    except (NotebookLMTransient, NotebookLMPermanent, OSError) as exc:
        result = RunResult(status="error", message=str(exc))
    if result.worked:
        store.save_last_run(config, result.last_run())
    return result
