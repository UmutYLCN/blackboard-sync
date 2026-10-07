"""A fake Blackboard server for tests: routes GET requests to fixture data."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config

FIXTURES = Path(__file__).parent / "fixtures"
# POSIX permission bits exist only off Windows (there the data folder's ACL applies).
POSIX = sys.platform != "win32"


def assert_owner_only(path: Path, mode: int = 0o600) -> None:
    if POSIX:
        assert (path.stat().st_mode & 0o777) == mode
BASE_URL = "https://blackboard.example.edu"


class FakeResponse:
    def __init__(self, status_code=200, url="", json_body=None, content=b"", headers=None):
        self.status_code = status_code
        self.url = url
        self._json = json_body
        self.content = content if json_body is None else json.dumps(json_body).encode()
        self.headers = headers or (
            {"Content-Type": "application/json"} if json_body is not None else {}
        )

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def close(self):
        pass


class FakeBlackboard:
    """Stands in for ``requests.Session``; only ``get`` is used by the client."""

    def __init__(self, routes: dict, files: dict[str, bytes] | None = None):
        self.routes = routes
        self.files = files or {}
        self.headers: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.calls: list[str] = []
        self.expired = False
        self.redirect_to_login = False
        # Opt-in HTTP validators: download path -> ETag. Sent with Content-Length and
        # honoured on If-None-Match (304) like a real file server.
        self.etags: dict[str, str] = {}
        self.conditional_requests: list[str] = []
        self.ignore_conditional = False

    def get(self, url, params=None, timeout=None, stream=False, headers=None):
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if params:
            query.update({k: [str(v)] for k, v in params.items()})
        key = parts.path
        if "offset" in query:
            key += f"?offset={query['offset'][0]}"
        self.calls.append(key)
        if self.expired:
            return FakeResponse(401, url, {"status": 401, "message": "Unauthorized"})
        if self.redirect_to_login:
            return FakeResponse(
                200,
                f"{BASE_URL}/webapps/login/?action=relogin",
                content=b"<html>login</html>",
                headers={"Content-Type": "text/html"},
            )
        if key in self.files:
            resp_headers = {"Content-Type": "application/octet-stream"}
            etag = self.etags.get(key)
            if etag:
                resp_headers["ETag"] = etag
                resp_headers["Content-Length"] = str(len(self.files[key]))
                if not self.ignore_conditional and (headers or {}).get("If-None-Match") == etag:
                    self.conditional_requests.append(key)
                    return FakeResponse(304, url, content=b"", headers=resp_headers)
            return FakeResponse(200, url, content=self.files[key], headers=resp_headers)
        if key in self.routes:
            return FakeResponse(200, url, copy.deepcopy(self.routes[key]))
        return FakeResponse(404, url, {"status": 404, "message": "Not found"})

    def downloads(self) -> list[str]:
        return [c for c in self.calls if c in self.files]


def load_routes() -> dict:
    data = json.loads((FIXTURES / "blackboard_api.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


SAMPLE_FILES = {
    "/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments/_a11_1/download": b"%PDF syllabus v1",
    "/learn/api/public/v1/courses/_13004_1/contents/_c4_1/attachments/_a41_1/download": b"%PDF homework 1",
    "/bbcswebdav/xid-777_1": b"%PDF week 1 slides",
}


@pytest.fixture
def fake_bb() -> FakeBlackboard:
    return FakeBlackboard(load_routes(), dict(SAMPLE_FILES))


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(base_url=BASE_URL, dest=tmp_path / "University", data_dir=tmp_path / "data")


@pytest.fixture
def client(fake_bb) -> BlackboardClient:
    return BlackboardClient(BASE_URL, fake_bb)
