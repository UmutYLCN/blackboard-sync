"""Storing and reusing the Blackboard session cookies captured by ``login``.

The session file only ever holds cookies for the Blackboard host plus who they
belong to; it never contains a password. It is written with owner-only
permissions inside the private data directory.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from blackboard_sync.errors import LoginRequired

SESSION_VERSION = 1


def host_of(base_url: str) -> str:
    return urlsplit(base_url).hostname or ""


def cookie_matches_host(cookie_domain: str, host: str) -> bool:
    domain = cookie_domain.lstrip(".").lower()
    host = host.lower()
    return host == domain or host.endswith("." + domain)


def write_private_json(path: Path, data: dict) -> None:
    """Atomically write JSON readable only by the current user."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def save_session(path: Path, base_url: str, cookies: list[dict], user: dict | None) -> int:
    """Persist the Blackboard-host cookies; returns how many were kept."""
    host = host_of(base_url)
    kept = [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain") or host,
            "path": c.get("path") or "/",
            "secure": bool(c.get("secure", True)),
            "expires": c.get("expires") if (c.get("expires") or -1) > 0 else None,
        }
        for c in cookies
        if cookie_matches_host(c.get("domain") or host, host)
    ]
    user = user or {}
    write_private_json(
        path,
        {
            "version": SESSION_VERSION,
            "base_url": base_url,
            "saved_at": int(time.time()),
            "user": {"id": user.get("id"), "userName": user.get("userName")},
            "cookies": kept,
        },
    )
    return len(kept)


def load_session(path: Path, base_url: str) -> dict:
    if not path.exists():
        raise LoginRequired("You are not signed in yet.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LoginRequired("The saved session could not be read.")
    if data.get("base_url", "").rstrip("/") != base_url.rstrip("/"):
        raise LoginRequired(f"The saved session belongs to {data.get('base_url')}.")
    now = time.time()
    live = [c for c in data.get("cookies", []) if not c.get("expires") or c["expires"] > now]
    if not live:
        raise LoginRequired("Your Blackboard session has expired.")
    data["cookies"] = live
    return data


def http_session(session_data: dict) -> requests.Session:
    http = requests.Session()
    for c in session_data["cookies"]:
        http.cookies.set(
            c["name"],
            c["value"],
            domain=c["domain"],
            path=c.get("path") or "/",
            secure=c.get("secure", True),
            expires=c.get("expires"),
        )
    return http


def refresh_saved_cookies(path: Path, session_data: dict, http: requests.Session) -> None:
    """Write back cookies Blackboard rotated during a run so the session stays alive."""
    current = {(c["name"], c["domain"], c.get("path") or "/"): c for c in session_data["cookies"]}
    host = host_of(session_data["base_url"])
    changed = False
    for jar_cookie in http.cookies:
        if not cookie_matches_host(jar_cookie.domain or host, host):
            continue
        key = (jar_cookie.name, jar_cookie.domain, jar_cookie.path or "/")
        old = current.get(key)
        if old is None or old["value"] != jar_cookie.value or old.get("expires") != jar_cookie.expires:
            changed = True
            current[key] = {
                "name": jar_cookie.name,
                "value": jar_cookie.value,
                "domain": jar_cookie.domain,
                "path": jar_cookie.path or "/",
                "secure": bool(jar_cookie.secure),
                "expires": jar_cookie.expires,
            }
    if not changed:
        return
    session_data = dict(session_data, cookies=list(current.values()), refreshed_at=int(time.time()))
    write_private_json(path, session_data)
