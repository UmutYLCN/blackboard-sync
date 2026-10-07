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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urljoin, urlsplit

import requests

from blackboard_sync.errors import ApiError, LoginRequired
from blackboard_sync.system import set_hidden

log = logging.getLogger(__name__)

PUBLIC = "/learn/api/public"
PRIVATE = "/learn/api/v1"
# Temp files of in-flight downloads; sync start removes the ones a killed run left.
PARTIAL_PREFIX = ".bbsync-"
PARTIAL_SUFFIX = ".partial"
USER_AGENT = "blackboard-sync/0.1 (+personal course mirror)"
# Paths that mean Blackboard bounced us to a login page instead of answering.
_LOGIN_MARKERS = ("/webapps/login", "/auth-saml", "/webapps/bb-auth-provider", "/ultra/logout")
_FILENAME_STAR = re.compile(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", re.IGNORECASE)
_FILENAME = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.IGNORECASE)


@dataclass
class Download:
    path: Path | None  # temporary file holding the body (None when unchanged)
    sha256: str
    size: int
    filename: str | None  # from Content-Disposition, if any
    unchanged: bool = False  # the server confirmed our recorded copy is current; no body was read
    etag: str | None = None
    last_modified: str | None = None


class BlackboardClient:
    def __init__(self, base_url: str, http: requests.Session, timeout: float = 60):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.timeout = timeout
        self.http.headers.setdefault("User-Agent", USER_AGENT)
        self.http.headers["Accept"] = "application/json"

    # -- low level ------------------------------------------------------
    def url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _check_login(self, resp: requests.Response, same_host: bool = True) -> None:
        if resp.status_code == 401:
            raise LoginRequired("Your Blackboard session has expired.")
        final = urlsplit(resp.url or "")
        base = urlsplit(self.base_url)
        # API calls never leave Blackboard unless bounced to a single-sign-on page.
        # Downloads may legitimately redirect to file storage on another host.
        if same_host and final.netloc and final.netloc != base.netloc:
            raise LoginRequired("Blackboard redirected to a sign-in page.")
        if any(marker in final.path for marker in _LOGIN_MARKERS):
            raise LoginRequired("Blackboard redirected to a sign-in page.")

    def get_json(self, path: str, params: dict | None = None) -> dict:
        url = self.url(path)
        resp = self.http.get(url, params=params, timeout=self.timeout)
        self._check_login(resp)
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, path, _error_message(resp))
        ctype = resp.headers.get("Content-Type", "")
        if "json" not in ctype:
            # A real sign-in redirect was already caught by _check_login via the final
            # URL; any other HTML (e.g. a maintenance page) is transient, not an expired
            # session, so retry on the next run instead of asking the user to sign in.
            raise ApiError(resp.status_code, path, "Blackboard answered with a web page instead of data.")
        return resp.json()

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
    ) -> Download:
        """Stream a file into a temporary ``.partial`` file inside ``into_dir``.

        ``known`` holds what was recorded for the copy we already have (``etag``,
        ``last_modified``, ``size``). It is sent as a conditional request, and when the
        response headers show that copy is still current the body is never read and
        the result has ``unchanged=True`` and no file.
        """
        url = self.url(path_or_url) if "://" not in path_or_url else path_or_url
        headers = {"Accept": "*/*"}
        if known and known.get("etag"):
            headers["If-None-Match"] = known["etag"]
        elif known and known.get("last_modified"):
            headers["If-Modified-Since"] = known["last_modified"]
        resp = self.http.get(url, stream=True, timeout=self.timeout, headers=headers)
        try:
            self._check_login(resp, same_host=False)
            if known and _still_current(resp, known):
                return Download(None, "", int(known.get("size") or 0), None, unchanged=True)
            if resp.status_code >= 400:
                raise ApiError(resp.status_code, url, _error_message(resp))
            ctype = resp.headers.get("Content-Type", "")
            filename = filename_from_disposition(resp.headers.get("Content-Disposition", ""))
            name = (filename or expected_name).lower()
            if "text/html" in ctype and not filename and not name.endswith((".html", ".htm")):
                # A web page where a PDF/slide deck was expected, with no file name from the
                # server, is an error page. A sign-in redirect was already caught above via
                # the final URL, so skip just this item instead of reporting an expired
                # session. A file the server names explicitly (Content-Disposition) is saved
                # as-is, so a real .php/.xhtml/extensionless upload is never dropped.
                raise ApiError(resp.status_code, url, "Blackboard answered a download with a web page.")
            digest = hashlib.sha256()
            size = 0
            fd, tmp = _mkstemp(into_dir)
            try:
                with os.fdopen(fd, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        if chunk:
                            fh.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
            except BaseException:
                os.unlink(tmp)
                raise
            return Download(
                Path(tmp),
                digest.hexdigest(),
                size,
                filename,
                etag=resp.headers.get("ETag"),
                last_modified=resp.headers.get("Last-Modified"),
            )
        finally:
            resp.close()


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
