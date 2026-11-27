"""Blackboard Learn REST client that rides on the student's browser session.

Blackboard Learn Ultra's own web UI calls the REST API under ``/learn/api``
with the logged-in session cookies, so a student session can read the same
course data without an application key. Only GET requests are made.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import unquote, urljoin, urlsplit

import requests

from blackboard_sync.errors import ApiError, LoginRequired, SkippedMedia
from blackboard_sync.i18n import tr
from blackboard_sync.report import UNAVAILABLE_STATUSES
from blackboard_sync.system import set_hidden

log = logging.getLogger(__name__)

PUBLIC = "/learn/api/public"
PRIVATE = "/learn/api/v1"
# Temp files of in-flight downloads; sync start removes the ones a killed run left.
PARTIAL_PREFIX = ".bbsync-"
PARTIAL_SUFFIX = ".partial"
USER_AGENT = "blackboard-sync/0.1 (+personal course mirror)"
MAX_DOWNLOAD_SIZE = 500_000_000  # 500 MB (decimal)
# How many times a dropped download resumes with HTTP Range before giving up for this run.
MAX_RESUME_ATTEMPTS = 3
RESUME_BACKOFF_BASE = 0.5
_sleep = time.sleep  # a seam for tests
# Paths that mean Blackboard bounced us to a login page instead of answering.
_LOGIN_MARKERS = ("/webapps/login", "/auth-saml", "/webapps/bb-auth-provider", "/ultra/logout")
_FILENAME_STAR = re.compile(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", re.IGNORECASE)
_FILENAME = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.IGNORECASE)
_CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)
# Videos and audio recordings are never downloaded (they are huge); they become links.
MEDIA_EXTENSIONS = (
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".flv", ".f4v", ".mpg", ".mpeg",
    ".3gp", ".3g2", ".ogv", ".m2ts", ".mts", ".vob", ".asf",
    ".mp3", ".m4a", ".m4b", ".wav", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".aif",
    ".aiff", ".amr", ".mka",
)


@dataclass
class PartialTransfer:
    """Resumable partial file left on disk after a dropped download."""

    path: Path
    size: int | None = None  # expected total bytes, if known
    etag: str | None = None
    last_modified: str | None = None
    filename: str | None = None
    content_type: str = ""


@dataclass
class Download:
    path: Path | None  # temporary file holding the body (None when unchanged)
    sha256: str
    size: int
    filename: str | None  # from Content-Disposition, if any
    unchanged: bool = False  # the server confirmed our recorded copy is current; no body was read
    etag: str | None = None
    last_modified: str | None = None
    content_type: str = ""
    drops: int = 0  # mid-transfer drops recovered via HTTP Range resume


class BlackboardClient:
    def __init__(self, base_url: str, http: requests.Session, timeout: float = 60):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.timeout = timeout
        self.http.headers.setdefault("User-Agent", USER_AGENT)
        self.http.headers["Accept"] = "application/json"

    def close(self) -> None:
        close = getattr(self.http, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "BlackboardClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # -- low level ------------------------------------------------------
    def url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _check_login(self, resp: requests.Response, same_host: bool = True) -> None:
        if resp.status_code == 401:
            raise LoginRequired(tr("Your Blackboard session has expired."))
        final = urlsplit(resp.url or "")
        base = urlsplit(self.base_url)
        # API calls never leave Blackboard unless bounced to a single-sign-on page.
        # Downloads may legitimately redirect to file storage on another host.
        if same_host and final.netloc and final.netloc != base.netloc:
            raise LoginRequired(tr("Blackboard redirected to a sign-in page."))
        if any(marker in final.path for marker in _LOGIN_MARKERS):
            raise LoginRequired(tr("Blackboard redirected to a sign-in page."))

    def get_json(self, path: str, params: dict | None = None) -> dict:
        url = self.url(path)
        resp = self.http.get(url, params=params, timeout=self.timeout)
        try:
            self._check_login(resp)
            if resp.status_code >= 400:
                raise ApiError(resp.status_code, path, _error_message(resp))
            ctype = resp.headers.get("Content-Type", "")
            if "json" not in ctype:
                # A real sign-in redirect was already caught by _check_login via the final
                # URL; any other HTML (e.g. a maintenance page) is transient, not an expired
                # session, so retry on the next run instead of asking the user to sign in.
                raise ApiError(resp.status_code, path, tr("Blackboard answered with a web page instead of data."))
            return resp.json()
        finally:
            _close_response(resp)

    def get_paged(self, path: str, params: dict | None = None) -> Iterator[dict]:
        """Yield every result across ``paging.nextPage`` links."""
        params = dict(params or {})
        while path:
            data = self.get_json(path, params)
            yield from data.get("results", [])
            path = (data.get("paging") or {}).get("nextPage")
            params = None  # nextPage already carries the query string

    # -- endpoints ------------------------------------------------------
    def me(self) -> dict:
        return self.get_json(f"{PUBLIC}/v1/users/me")

    def memberships(self, user_id: str) -> list[dict]:
        return list(
            self.get_paged(
                f"{PUBLIC}/v1/users/{user_id}/courses",
                {"expand": "course", "limit": 100},
            )
        )

    def course(self, course_id: str) -> dict:
        return self.get_json(f"{PUBLIC}/v3/courses/{course_id}")

    def term(self, term_id: str) -> dict | None:
        for path in (f"{PUBLIC}/v1/terms/{term_id}", f"{PRIVATE}/terms/{term_id}"):
            try:
                return self.get_json(path)
            except ApiError as exc:
                log.debug("term lookup failed via %s: %s", path, exc)
        return None

    def contents(self, course_id: str) -> list[dict]:
        return list(self.get_paged(f"{PUBLIC}/v1/courses/{course_id}/contents", {"limit": 200}))

    def grade_columns(self, course_id: str) -> list[dict]:
        """Student-visible metadata only; never grades, submissions or attempts."""
        return list(self.get_paged(f"{PUBLIC}/v2/courses/{course_id}/gradebook/columns", {"limit": 200}))

    def children(self, course_id: str, content_id: str) -> list[dict]:
        return list(
            self.get_paged(
                f"{PUBLIC}/v1/courses/{course_id}/contents/{content_id}/children",
                {"limit": 200},
            )
        )

    def attachments(self, course_id: str, content_id: str) -> list[dict]:
        return list(
            self.get_paged(f"{PUBLIC}/v1/courses/{course_id}/contents/{content_id}/attachments")
        )

    def announcements(self, course_id: str) -> list[dict]:
        last_error: ApiError | None = None
        for path in (
            f"{PUBLIC}/v1/courses/{course_id}/announcements",
            f"{PRIVATE}/courses/{course_id}/announcements",
        ):
            try:
                return list(self.get_paged(path, {"limit": 100}))
            except ApiError as exc:
                last_error = exc
                log.debug("announcements unavailable via %s: %s", path, exc)
        assert last_error is not None
        raise last_error

    def attachment_url(self, course_id: str, content_id: str, attachment_id: str) -> str:
        return (
            f"{PUBLIC}/v1/courses/{course_id}/contents/{content_id}"
            f"/attachments/{attachment_id}/download"
        )

    def download(
        self,
        path_or_url: str,
        into_dir: Path,
        expected_name: str = "",
        known: dict | None = None,
        *,
        resume: PartialTransfer | None = None,
        on_drop: Callable[[], None] | None = None,
        on_partial: Callable[[PartialTransfer], None] | None = None,
        max_resume_attempts: int = MAX_RESUME_ATTEMPTS,
    ) -> Download:
        """Stream a file into a temporary ``.partial`` file inside ``into_dir``.

        ``known`` holds what was recorded for the copy we already have (``etag``,
        ``last_modified``, ``size``). It is sent as a conditional request, and when the
        response headers show that copy is still current the body is never read and
        the result has ``unchanged=True`` and no file.

        When a transfer drops mid-stream (or ends short of ``Content-Length``), the
        partial file is kept and resumed with HTTP ``Range`` requests up to
        ``max_resume_attempts`` times. A ``206 Partial Content`` response is appended
        only when its byte range, total size and validators match; otherwise the
        download restarts cleanly from byte 0.
        """
        url = self.url(path_or_url) if "://" not in path_or_url else path_or_url
        tmp: Path | None = None
        digest = hashlib.sha256()
        offset = 0
        expected_total: int | None = None
        etag: str | None = None
        last_modified: str | None = None
        filename: str | None = None
        content_type = ""

        if resume is not None and resume.path.is_file():
            try:
                existing_size = resume.path.stat().st_size
            except OSError:
                existing_size = 0
            if existing_size > 0 and (resume.size is None or existing_size < resume.size):
                tmp = resume.path
                digest, offset = _hash_existing(tmp)
                expected_total = resume.size
                etag = resume.etag
                last_modified = resume.last_modified
                filename = resume.filename
                content_type = resume.content_type
            else:
                resume.path.unlink(missing_ok=True)

        drops = 0
        restarted = False

        def reset_transfer() -> None:
            nonlocal digest, offset, expected_total, etag, last_modified, filename, content_type
            digest = hashlib.sha256()
            offset = 0
            expected_total = None
            etag = None
            last_modified = None
            filename = None
            content_type = ""

        def save_or_discard_partial() -> None:
            if tmp is not None and offset > 0 and tmp.is_file() and on_partial is not None:
                on_partial(
                    PartialTransfer(
                        path=tmp,
                        size=expected_total,
                        etag=etag,
                        last_modified=last_modified,
                        filename=filename,
                        content_type=content_type,
                    )
                )
            elif tmp is not None:
                tmp.unlink(missing_ok=True)

        while True:
            headers = {"Accept": "*/*"}
            if offset > 0:
                headers["Range"] = f"bytes={offset}-"
                if etag:
                    headers["If-Range"] = etag
                elif last_modified:
                    headers["If-Range"] = last_modified
            else:
                if known and known.get("etag"):
                    headers["If-None-Match"] = known["etag"]
                elif known and known.get("last_modified"):
                    headers["If-Modified-Since"] = known["last_modified"]

            try:
                resp = self.http.get(url, stream=True, timeout=self.timeout, headers=headers)
            except requests.RequestException:
                if offset > 0:
                    drops += 1
                    if on_drop is not None:
                        on_drop()
                    if drops <= max_resume_attempts:
                        _sleep(RESUME_BACKOFF_BASE * (2 ** (drops - 1)))
                        continue
                save_or_discard_partial()
                raise

            try:
                self._check_login(resp, same_host=False)
                if offset == 0 and known and _still_current(resp, known):
                    if tmp is not None:
                        tmp.unlink(missing_ok=True)
                    return Download(None, "", int(known.get("size") or 0), None, unchanged=True)

                append = False
                if offset > 0:
                    if resp.status_code == 206:
                        parsed = _parse_content_range(resp.headers.get("Content-Range", ""))
                        resp_etag = resp.headers.get("ETag")
                        resp_lm = resp.headers.get("Last-Modified")
                        range_ok = (
                            parsed is not None
                            and parsed[0] == offset
                            and (parsed[2] is None or parsed[1] < parsed[2])
                        )
                        size_ok = (
                            parsed is not None
                            and (expected_total is None or parsed[2] is None or parsed[2] == expected_total)
                        )
                        validator_ok = (
                            not (etag and resp_etag and resp_etag != etag)
                            and not (last_modified and resp_lm and resp_lm != last_modified)
                        )
                        if not (range_ok and size_ok and validator_ok):
                            if not restarted:
                                restarted = True
                                reset_transfer()
                                continue
                            if tmp is not None:
                                tmp.unlink(missing_ok=True)
                            raise requests.exceptions.ChunkedEncodingError(
                                "Server returned an unexpected Content-Range while resuming download."
                            )
                        total = parsed[2]
                        if total is not None:
                            if total > MAX_DOWNLOAD_SIZE:
                                if tmp is not None:
                                    tmp.unlink(missing_ok=True)
                                raise SkippedMedia(
                                    url, filename or expected_name, content_type, reason="size", size=total
                                )
                            expected_total = total
                        etag = resp_etag or etag
                        last_modified = resp_lm or last_modified
                        filename = filename_from_disposition(resp.headers.get("Content-Disposition", "")) or filename
                        content_type = resp.headers.get("Content-Type", "") or content_type
                        append = True
                    elif resp.status_code == 200:
                        # Server ignored Range or the file changed (If-Range): restart cleanly from byte 0.
                        reset_transfer()
                    elif resp.status_code == 416 and not restarted:
                        restarted = True
                        reset_transfer()
                        continue
                    elif resp.status_code >= 400:
                        if resp.status_code in UNAVAILABLE_STATUSES:
                            if tmp is not None:
                                tmp.unlink(missing_ok=True)
                        else:
                            save_or_discard_partial()
                        raise ApiError(resp.status_code, url, _error_message(resp))
                    else:
                        if not restarted:
                            restarted = True
                            reset_transfer()
                            continue
                        if tmp is not None:
                            tmp.unlink(missing_ok=True)
                        raise ApiError(resp.status_code, url, _error_message(resp))

                if not append:
                    if resp.status_code >= 400:
                        if tmp is not None:
                            tmp.unlink(missing_ok=True)
                        raise ApiError(resp.status_code, url, _error_message(resp))
                    ctype = resp.headers.get("Content-Type", "")
                    filename = filename_from_disposition(resp.headers.get("Content-Disposition", ""))
                    content_type = ctype
                    name = (filename or expected_name).lower()
                    if is_media(ctype, filename, expected_name):
                        # Decided from the headers alone: closing the response (below) drops the
                        # connection without reading the body, and no temporary file exists yet.
                        if tmp is not None:
                            tmp.unlink(missing_ok=True)
                        raise SkippedMedia(url, filename or expected_name, ctype)
                    content_length = resp.headers.get("Content-Length", "")
                    if content_length.isdigit():
                        expected_total = int(content_length)
                        if expected_total > MAX_DOWNLOAD_SIZE:
                            if tmp is not None:
                                tmp.unlink(missing_ok=True)
                            raise SkippedMedia(
                                url, filename or expected_name, ctype, reason="size", size=expected_total
                            )
                    if "text/html" in ctype and not filename and not name.endswith((".html", ".htm")):
                        # A web page where a PDF/slide deck was expected, with no file name from the
                        # server, is an error page. A sign-in redirect was already caught above via
                        # the final URL, so skip just this item instead of reporting an expired
                        # session. A file the server names explicitly (Content-Disposition) is saved
                        # as-is, so a real .php/.xhtml/extensionless upload is never dropped.
                        if tmp is not None:
                            tmp.unlink(missing_ok=True)
                        raise ApiError(resp.status_code, url, tr("Blackboard answered a download with a web page."))
                    etag = resp.headers.get("ETag")
                    last_modified = resp.headers.get("Last-Modified")

                stream_error: requests.RequestException | None = None
                try:
                    if tmp is None:
                        fd, tmp_str = _mkstemp(into_dir)
                        tmp = Path(tmp_str)
                        fh = os.fdopen(fd, "wb")
                    else:
                        fh = _open_for_write(tmp, append=append)
                    with fh:
                        for chunk in resp.iter_content(chunk_size=1 << 16):
                            if chunk:
                                if offset + len(chunk) > MAX_DOWNLOAD_SIZE:
                                    raise SkippedMedia(
                                        url, filename or expected_name, content_type,
                                        reason="size", size=offset + len(chunk),
                                    )
                                fh.write(chunk)
                                digest.update(chunk)
                                offset += len(chunk)
                except requests.RequestException as exc:
                    stream_error = exc
                except BaseException:
                    if tmp is not None:
                        tmp.unlink(missing_ok=True)
                    raise

                if stream_error is None and expected_total is not None and offset < expected_total:
                    stream_error = requests.exceptions.ChunkedEncodingError(
                        f"Download ended early ({offset} of {expected_total} bytes)."
                    )
                if stream_error is not None:
                    drops += 1
                    if on_drop is not None:
                        on_drop()
                    if offset > 0 and drops <= max_resume_attempts:
                        _sleep(RESUME_BACKOFF_BASE * (2 ** (drops - 1)))
                        continue
                    save_or_discard_partial()
                    raise stream_error

                if expected_total is not None and offset > expected_total:
                    if not restarted:
                        restarted = True
                        reset_transfer()
                        continue
                    if tmp is not None:
                        tmp.unlink(missing_ok=True)
                    raise requests.exceptions.ChunkedEncodingError(
                        f"Download exceeded expected size ({offset} > {expected_total} bytes)."
                    )

                assert tmp is not None
                return Download(
                    tmp,
                    digest.hexdigest(),
                    offset,
                    filename,
                    etag=etag,
                    last_modified=last_modified,
                    content_type=content_type,
                    drops=drops,
                )
            finally:
                _close_response(resp)


def _close_response(resp) -> None:
    """Release an HTTP response cleanly, ignoring bare test stubs with ``raw=None``."""
    if getattr(resp, "_content_consumed", True) is False and getattr(resp, "raw", None) is None:
        return
    close = getattr(resp, "close", None)
    if callable(close):
        close()


def _parse_content_range(header: str) -> tuple[int, int, int | None] | None:
    """Parse ``Content-Range: bytes <start>-<end>/<total>``; returns None if malformed."""
    match = _CONTENT_RANGE.match((header or "").strip())
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    total = None if match.group(3) == "*" else int(match.group(3))
    if end < start or (total is not None and end >= total):
        return None
    return start, end, total


def _hash_existing(path: Path) -> tuple[hashlib._Hash, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest, size


def _open_for_write(path: Path, *, append: bool):
    """Open an existing hidden-safe temp file for appending or clean overwrite."""
    fh = open(path, "r+b")
    if append:
        fh.seek(0, os.SEEK_END)
    else:
        fh.seek(0)
        fh.truncate(0)
    return fh


def is_media(content_type: str | None, *names: str | None) -> bool:
    """True for a ``video/*`` or ``audio/*`` type, or a name with a video or audio extension."""
    if (content_type or "").strip().lower().startswith(("video/", "audio/")):
        return True
    return any(n.strip().lower().endswith(MEDIA_EXTENSIONS) for n in names if n)


def _still_current(resp: requests.Response, known: dict) -> bool:
    """True when the headers prove the copy we recorded is what the server would send."""
    if resp.status_code == 304:
        return True
    if resp.status_code != 200:
        return False
    etag, modified = resp.headers.get("ETag"), resp.headers.get("Last-Modified")
    if etag and known.get("etag"):
        same = etag == known["etag"]
    elif modified and known.get("last_modified"):
        same = modified == known["last_modified"]
    else:
        return False  # no validator to compare: only the body can tell
    length = resp.headers.get("Content-Length")
    if same and length and known.get("size") is not None and length.isdigit():
        same = int(length) == known["size"]
    return same


def _mkstemp(directory: Path) -> tuple[int, str]:
    fd, tmp = tempfile.mkstemp(prefix=PARTIAL_PREFIX, suffix=PARTIAL_SUFFIX, dir=directory)
    set_hidden(Path(tmp), True)
    return fd, tmp


def _error_message(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return ""
    if isinstance(data, dict):
        return str(data.get("message") or "")
    return ""


def filename_from_disposition(header: str) -> str | None:
    if not header:
        return None
    match = _FILENAME_STAR.search(header)
    if match:
        return unquote(match.group(2).strip().strip('"'))
    match = _FILENAME.search(header)
    if match:
        return match.group(1).strip()
    return None
