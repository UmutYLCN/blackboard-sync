import json
import time

import pytest

from blackboard_sync import cli
from blackboard_sync.errors import EXIT_LOGIN_REQUIRED, EXIT_OK, ApiError, LoginRequired
from blackboard_sync.session import (
    http_session,
    load_session,
    refresh_saved_cookies,
    save_session,
)

from .conftest import BASE_URL, FakeResponse, assert_owner_only


def _save(config, cookies=None):
    cookies = cookies or [
        {"name": "BbRouter", "value": "expires:1,id:x", "domain": "blackboard.example.edu",
         "path": "/", "secure": True, "expires": -1},
        {"name": "JSESSIONID", "value": "abc", "domain": "blackboard.example.edu", "path": "/",
         "secure": True, "expires": time.time() + 3600},
        {"name": "sso", "value": "other-site", "domain": "login.example.com", "path": "/",
         "secure": True, "expires": -1},
    ]
    config.ensure_data_dir()
    return save_session(config.session_file, BASE_URL, cookies, {"id": "_900_1", "userName": "s"})


def test_saved_session_is_private_and_only_holds_blackboard_cookies(config):
    assert _save(config) == 2
    assert_owner_only(config.session_file)
    assert_owner_only(config.data_dir, 0o700)
    data = json.loads(config.session_file.read_text(encoding="utf-8"))
    assert {c["name"] for c in data["cookies"]} == {"BbRouter", "JSESSIONID"}
    assert "password" not in config.session_file.read_text(encoding="utf-8").lower()


def test_missing_session_requires_login(config):
    with pytest.raises(LoginRequired, match="not signed in"):
        load_session(config.session_file, BASE_URL)


def test_expired_cookies_require_login(config):
    _save(config, [{"name": "JSESSIONID", "value": "abc", "domain": "blackboard.example.edu",
                    "path": "/", "expires": time.time() - 10}])
    with pytest.raises(LoginRequired, match="expired"):
        load_session(config.session_file, BASE_URL)


def test_session_for_another_site_requires_login(config):
    _save(config)
    with pytest.raises(LoginRequired):
        load_session(config.session_file, "https://other.example.edu")


def test_api_401_means_login_required(client, fake_bb):
    fake_bb.expired = True
    with pytest.raises(LoginRequired, match="expired"):
        client.me()


def test_redirect_to_login_page_means_login_required(client, fake_bb):
    fake_bb.redirect_to_login = True
    with pytest.raises(LoginRequired, match="sign-in"):
        client.me()


def test_sso_redirect_to_other_host_means_login_required(client, fake_bb):
    fake_bb.get = lambda url, **kw: FakeResponse(
        200, "https://login.example.com/saml", content=b"<html>", headers={"Content-Type": "text/html"}
    )
    with pytest.raises(LoginRequired):
        client.me()


def test_html_download_is_an_item_error_not_an_expired_session(client, fake_bb, tmp_path):
    fake_bb.get = lambda url, **kw: FakeResponse(
        200, url, content=b"<html>error</html>", headers={"Content-Type": "text/html"}
    )
    with pytest.raises(ApiError):
        client.download("/bbcswebdav/xid-1_1", tmp_path, expected_name="slides.pdf")
    assert list(tmp_path.iterdir()) == []
    # ...but an actual .html course file is fine.
    dl = client.download("/bbcswebdav/xid-1_1", tmp_path, expected_name="page.html")
    assert dl.path.read_bytes() == b"<html>error</html>"


def test_html_download_named_by_the_server_is_saved(client, fake_bb, tmp_path):
    fake_bb.get = lambda url, **kw: FakeResponse(
        200, url, content=b"<?php ?>",
        headers={"Content-Type": "text/html", "Content-Disposition": 'attachment; filename="lab.php"'},
    )
    dl = client.download("/bbcswebdav/xid-1_1", tmp_path, expected_name="")
    assert dl.filename == "lab.php" and dl.path.read_bytes() == b"<?php ?>"


def test_html_download_redirected_to_login_is_login_required(client, fake_bb, tmp_path):
    fake_bb.get = lambda url, **kw: FakeResponse(
        200, f"{BASE_URL}/webapps/login/?action=relogin", content=b"<html>", headers={"Content-Type": "text/html"}
    )
    with pytest.raises(LoginRequired):
        client.download("/bbcswebdav/xid-1_1", tmp_path, expected_name="slides.pdf")


def test_html_from_json_endpoint_is_transient_api_error(client, fake_bb):
    fake_bb.get = lambda url, **kw: FakeResponse(
        200, url, content=b"<html>maintenance</html>", headers={"Content-Type": "text/html"}
    )
    with pytest.raises(ApiError):
        client.me()


def test_html_attachment_does_not_stop_the_sync(config, client, fake_bb):
    from .test_sync import sync

    real_get = fake_bb.get

    def get(url, **kw):
        if url.endswith("/attachments/_a11_1/download"):
            return FakeResponse(200, url, content=b"<html>oops</html>", headers={"Content-Type": "text/html"})
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)
    assert report.totals()["new_files"] >= 1
    assert any("web page" in w for c in report.courses for w in c.warnings)


def test_refresh_saved_cookies_keeps_rotated_values(config):
    _save(config)
    data = load_session(config.session_file, BASE_URL)
    http = http_session(data)
    http.cookies.set("BbRouter", "rotated", domain="blackboard.example.edu", path="/")
    http.cookies.set("tracker", "x", domain="cdn.example.net", path="/")
    refresh_saved_cookies(config.session_file, data, http)
    saved = json.loads(config.session_file.read_text(encoding="utf-8"))
    values = {c["name"]: c["value"] for c in saved["cookies"]}
    assert values["BbRouter"] == "rotated"
    assert "tracker" not in values
    assert_owner_only(config.session_file)


def _run_cli(config, fake_bb, monkeypatch, *args):
    monkeypatch.setattr(cli, "http_session", lambda data: fake_bb)
    return cli.main(
        ["--base-url", BASE_URL, "--data-dir", str(config.data_dir), "sync",
         "--dest", str(config.dest), *args]
    )


def test_cli_exits_with_login_required_status_when_session_expired(config, fake_bb, monkeypatch, capsys):
    _save(config)
    fake_bb.expired = True
    code = _run_cli(config, fake_bb, monkeypatch, "--json")
    assert code == EXIT_LOGIN_REQUIRED
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "login_required"
    assert "blackboard-sync login" in out["message"]
    last = json.loads(config.last_run_file.read_text(encoding="utf-8"))
    assert last["status"] == "login_required"


def test_cli_without_session_says_to_log_in(config, fake_bb, monkeypatch, capsys):
    code = _run_cli(config, fake_bb, monkeypatch)
    assert code == EXIT_LOGIN_REQUIRED
    assert "blackboard-sync login" in capsys.readouterr().err


def test_cli_sync_json_summary(config, fake_bb, monkeypatch, capsys):
    _save(config)
    code = _run_cli(config, fake_bb, monkeypatch, "--json")
    assert code == EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["totals"]["new_files"] == 3
    assert [c["summary"] for c in out["changed_courses"]] == [
        "CSE303: 3 new files, 3 new notes, 1 new announcement"
    ]
    assert json.loads(config.last_run_file.read_text(encoding="utf-8"))["totals"] == out["totals"]
