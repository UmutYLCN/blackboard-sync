"""Build-only OAuth metadata injection; credentials never enter tracked source.

Desktop OAuth clients are public clients: bundled metadata can be extracted from
an installer. User access/refresh tokens must never be included here.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping


def oauth_datas(root: Path, env: Mapping[str, str] | None = None) -> list[tuple[str, str]]:
    """PyInstaller data entries from an Actions secret or a gitignored local JSON."""
    env = os.environ if env is None else env
    raw = env.get("BBSYNC_GOOGLE_OAUTH_CLIENT_JSON")
    source = Path(env.get("BBSYNC_GOOGLE_OAUTH_CLIENT_FILE") or root / ".bbsync/google-oauth-client.json")
    if not raw and source.is_file():
        raw = source.read_text(encoding="utf-8")
    if not raw:
        if env.get("BBSYNC_REQUIRE_GOOGLE_OAUTH") == "1":
            raise ValueError("Google Desktop OAuth metadata is required for this release build.")
        return []
    try:
        data = json.loads(raw)
        installed = data["installed"]
        client_id, secret = installed["client_id"], installed["client_secret"]
        if (not isinstance(client_id, str) or not client_id.endswith(".apps.googleusercontent.com")
                or not isinstance(secret, str) or not secret.strip()):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError("Invalid Google Desktop OAuth metadata; values are not displayed.") from None
    # Emit only the two fields the public client needs. Never bundle user tokens.
    directory = root / "build" / "private"
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory)
    target = directory / "google-oauth-client.json"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"installed": {"client_id": client_id, "client_secret": secret}}, output)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return [(str(target), "assets")]
