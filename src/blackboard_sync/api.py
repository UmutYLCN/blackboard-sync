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

log = logging.getLogger(__name__)

PUBLIC = "/learn/api/public"
PRIVATE = "/learn/api/v1"
USER_AGENT = "blackboard-sync/0.1 (+personal course mirror)"
# Paths that mean Blackboard bounced us to a login page instead of answering.
_LOGIN_MARKERS = ("/webapps/login", "/auth-saml", "/webapps/bb-auth-provider", "/ultra/logout")
_FILENAME_STAR = re.compile(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", re.IGNORECASE)
_FILENAME = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.IGNORECASE)


@dataclass
class Download:
    path: Path  # temporary file holding the body
    sha256: str
    size: int
    filename: str | None  # from Content-Disposition, if any


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

    def download(self, path_or_url: str, into_dir: Path, expected_name: str = "") -> Download:
        """Stream a file into a temporary ``.partial`` file inside ``into_dir``."""
        url = self.url(path_or_url) if "://" not in path_or_url else path_or_url
        into_dir.mkdir(parents=True, exist_ok=True)
        resp = self.http.get(
            url, stream=True, timeout=self.timeout, headers={"Accept": "*/*"}
        )
        try:
            self._check_login(resp, same_host=False)
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
            return Download(Path(tmp), digest.hexdigest(), size, filename)
        finally:
            resp.close()


def _mkstemp(directory: Path) -> tuple[int, str]:
    return tempfile.mkstemp(prefix=".bbsync-", suffix=".partial", dir=directory)


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
