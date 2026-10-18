"""Optional one-way Google Calendar integration; no GUI or Blackboard sync imports.

Only app-created secondary calendars and events bearing our private bbKey are
accessed. HTTP and credentials are injectable so tests never need Google or an OS vault.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import requests

from blackboard_sync.config import Config
from blackboard_sync.deadlines import parse_due
from blackboard_sync.errors import ApiError, BlackboardSyncError, CalendarAuthExpired
from blackboard_sync.i18n import tr
from blackboard_sync.session import write_private_json
from blackboard_sync.state import State
from blackboard_sync.system import try_lock

CLIENT_ID = "299496359002-cfritvblpnjn64s3nj8fme6eeoaktlol.apps.googleusercontent.com"
# Public Desktop OAuth client ID; override with BBSYNC_GOOGLE_CLIENT_ID.
SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
API = "https://www.googleapis.com/calendar/v3"
TOKEN = "https://oauth2.googleapis.com/token"
REVOKE = "https://oauth2.googleapis.com/revoke"
CALENDAR_NAME = "Blackboard Deadlines"


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def oauth_client_settings() -> dict:
    """Public Desktop metadata from the bundle or an explicitly local dev file."""
    override = os.environ.get("BBSYNC_GOOGLE_OAUTH_CLIENT_FILE")
    if override:
        path = Path(override).expanduser()
    elif getattr(sys, "frozen", False):
        path = Path(getattr(sys, "_MEIPASS", "")) / "assets/google-oauth-client.json"
    else:
        path = Path(__file__).resolve().parents[2] / ".bbsync/google-oauth-client.json"
    installed = _read(path).get("installed", {})
    if not isinstance(installed, dict):
        return {}
    return {key: installed[key] for key in ("client_id", "client_secret")
            if isinstance(installed.get(key), str) and installed[key]}


@dataclass(frozen=True)
class CalendarStatus:
    connected: bool = False
    last_sync: str | None = None
    last_error: str | None = None
    needs_reconnect: bool = False


class CredentialStore:
    """Refresh tokens in the native vault, private JSON only on other platforms.

    A vault failure is reported, never silently downgraded to plaintext.
    Each data directory has a separate credential, including isolated CLI profiles.
    """
    def __init__(self, directory: Path, *, platform: str | None = None):
        self.platform = platform or sys.platform
        self.path = directory / "google-token.json"
        self.account = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()
        self.service = "blackboard-sync.google-calendar"

    def get(self) -> str | None:
        if self.platform == "darwin":
            result = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", self.service,
                                     "-a", self.account, "-w"], capture_output=True, text=True)
            if result.returncode == 44:
                return None
            if result.returncode:
                raise BlackboardSyncError(tr("Could not access the Google Calendar credential store."))
            return result.stdout.strip() or None
        if self.platform == "win32":
            import win32cred
            import pywintypes
            try:
                data = win32cred.CredRead(self.service + self.account, win32cred.CRED_TYPE_GENERIC)
            except pywintypes.error as exc:
                if exc.winerror == 1168:
                    return None
                raise BlackboardSyncError(tr("Could not access the Google Calendar credential store.")) from None
            blob = data["CredentialBlob"]
            return blob.decode("utf-16-le") if isinstance(blob, bytes) else blob
        return _read(self.path).get("refresh_token")

    def set(self, token: str) -> None:
        if self.platform == "darwin":
            # Send the token over stdin, never in argv or a log message.
            command = shlex.join(["add-generic-password", "-U", "-s", self.service,
                                  "-a", self.account, "-w", token]) + "\n"
            result = subprocess.run(["/usr/bin/security", "-i"], input=command,
                                    capture_output=True, text=True)
            if result.returncode:
                raise BlackboardSyncError(tr("Could not access the Google Calendar credential store."))
        elif self.platform == "win32":
            import win32cred
            win32cred.CredWrite({"Type": win32cred.CRED_TYPE_GENERIC,
                                "TargetName": self.service + self.account,
                                "UserName": self.account, "CredentialBlob": token,
                                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE}, 0)
        else:
            write_private_json(self.path, {"refresh_token": token})

    def clear(self) -> None:
        if self.platform == "darwin":
            result = subprocess.run(["/usr/bin/security", "delete-generic-password", "-s", self.service,
                                     "-a", self.account], capture_output=True)
            if result.returncode not in (0, 44):
                raise BlackboardSyncError(tr("Could not access the Google Calendar credential store."))
        elif self.platform == "win32":
            import win32cred
            import pywintypes
            try:
                win32cred.CredDelete(self.service + self.account, win32cred.CRED_TYPE_GENERIC, 0)
            except pywintypes.error as exc:
                if exc.winerror != 1168:
                    raise BlackboardSyncError(tr("Could not access the Google Calendar credential store.")) from None
        self.path.unlink(missing_ok=True)


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()


def callback_code(query: str, state: str) -> str:
    params = parse_qs(query)
    actual = params.get("state", [""])
    if len(actual) != 1 or not secrets.compare_digest(actual[0].encode("utf-8"), state.encode("utf-8")):
        raise BlackboardSyncError(tr("Google Calendar authorization state did not match."))
    if "error" in params or len(params.get("code", [])) != 1:
        raise BlackboardSyncError(tr("Google Calendar authorization was cancelled."))
    return params["code"][0]


class CalendarClient:
    def __init__(self, config: Config, *, http=None, credentials=None, sleep=time.sleep,
                 now=None, cancel: threading.Event | None = None):
        self.config = config
        self.http = http if http is not None else requests.Session()
        self.credentials = credentials if credentials is not None else CredentialStore(config.data_dir)
        self.sleep = sleep
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.cancel = cancel or threading.Event()
        self.path = config.data_dir / "google-calendar.json"
        self.mapping_path = config.data_dir / "google-calendar-events.json"
        # Non-secret resource handle survives a disconnect that keeps the calendar.
        self.target_path = config.data_dir / "google-calendar-target.json"
        self.data = _read(self.path)
        self.access_token = ""
        self.expires = 0.0
        self.oauth_client = oauth_client_settings()
        self.client_id = os.environ.get("BBSYNC_GOOGLE_CLIENT_ID") or self.oauth_client.get("client_id") or CLIENT_ID

    def _save(self):
        write_private_json(self.path, self.data)

    def _check_cancel(self):
        if self.cancel.is_set():
            raise BlackboardSyncError(tr("Google Calendar operation was cancelled."))

    def _request(self, method, url, **kwargs):
        # Error bodies may contain private information. Never include them in exceptions.
        for attempt in range(5):
            self._check_cancel()
            try:
                response = self.http.request(method, url, timeout=30, **kwargs)
            except requests.RequestException:
                raise BlackboardSyncError(tr("Could not reach Google Calendar.")) from None
            try:
                body = response.json()
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            if (url == TOKEN and response.status_code == 400
                    and body.get("error") == "invalid_request"
                    and "client_secret" in str(body.get("error_description", "")).lower()):
                raise BlackboardSyncError(tr(
                    "Google requires this Desktop client's secret. Set BBSYNC_GOOGLE_CLIENT_SECRET locally and connect again."
                ))
            if body.get("error") == "invalid_grant" or response.status_code == 401:
                self.data.update(needs_reconnect=True, last_error=tr("Google Calendar needs to be reconnected"))
                self._save()
                raise CalendarAuthExpired()
            error = body.get("error")
            reasons = [e.get("reason") for e in error.get("errors", [])] if isinstance(error, dict) else []
            retry = response.status_code == 429 or response.status_code >= 500 or any(
                reason in ("rateLimitExceeded", "userRateLimitExceeded") for reason in reasons)
            if retry and attempt < 4:
                try:
                    delay = min(60, max(0, float(response.headers.get("Retry-After", 2 ** attempt))))
                except ValueError:
                    delay = 2 ** attempt
                if self.sleep is time.sleep:
                    if self.cancel.wait(delay):
                        self._check_cancel()
                else:
                    self.sleep(delay)
                continue
            if response.status_code >= 400:
                raise ApiError(response.status_code, url)
            return body
        raise AssertionError("unreachable")

    def _client_fields(self):
        if not self.client_id:
            raise BlackboardSyncError(tr("Set BBSYNC_GOOGLE_CLIENT_ID to your Desktop OAuth client ID."))
        fields = {"client_id": self.client_id}
        # Some Desktop clients require the downloaded client secret at the token endpoint.
        # It is public-client metadata, but remains an environment value, never committed.
        secret = os.environ.get("BBSYNC_GOOGLE_CLIENT_SECRET") or self.oauth_client.get("client_secret")
        if secret:
            fields["client_secret"] = secret
        return fields

    def connect(self, *, timeout=240, open_browser=webbrowser.open):
        fields = self._client_fields()
        verifier, state = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        result = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass  # The callback URL contains the authorization code.

            def do_GET(self):
                if urlsplit(self.path).path != "/":
                    self.send_error(404)
                    return
                try:
                    result["code"] = callback_code(urlsplit(self.path).query, state)
                except BlackboardSyncError as exc:
                    result["error"] = exc
                self.send_response(200 if "code" in result else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(tr("You can close this browser window and return to Blackboard Sync.").encode())

        class LoopbackServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(1)  # A stalled local connection cannot defeat cancel/timeout.
                return connection, address

        with LoopbackServer(("127.0.0.1", 0), Handler) as server:
            server.timeout = 0.25
            redirect = f"http://127.0.0.1:{server.server_port}/"
            url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
                "client_id": fields["client_id"], "redirect_uri": redirect, "response_type": "code",
                "scope": SCOPE, "state": state, "code_challenge": pkce_challenge(verifier),
                "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"})
            if not open_browser(url):
                raise BlackboardSyncError(tr("Could not open the browser for Google Calendar."))
            deadline = time.monotonic() + timeout
            while not result:
                self._check_cancel()
                if time.monotonic() >= deadline:
                    raise BlackboardSyncError(tr("Google Calendar authorization timed out."))
                server.handle_request()
        if "error" in result:
            raise result["error"]
        token = self._request("POST", TOKEN, data={**fields, "code": result["code"],
                              "code_verifier": verifier, "redirect_uri": redirect,
                              "grant_type": "authorization_code"})
        self._check_cancel()
        if not token.get("refresh_token"):
            raise CalendarAuthExpired()
        self.credentials.set(token["refresh_token"])
        self._accept_token(token)
        if not self.data.get("calendar_id"):
            calendar = _read(self.target_path).get("calendar_id")
            if calendar:
                self.data["calendar_id"] = calendar
        self.data.update(connected=True, needs_reconnect=False, last_error=None)
        self._save()

    def _accept_token(self, token):
        if not isinstance(token.get("access_token"), str) or not token["access_token"]:
            raise BlackboardSyncError(tr("Google Calendar returned an invalid response."))
        self.access_token = token["access_token"]
        self.expires = time.monotonic() + float(token.get("expires_in", 3600)) - 60

    def _api(self, method, path, **kwargs):
        if not self.access_token or time.monotonic() >= self.expires:
            refresh = self.credentials.get()
            if not refresh:
                raise CalendarAuthExpired()
            token = self._request("POST", TOKEN, data={**self._client_fields(),
                                  "refresh_token": refresh, "grant_type": "refresh_token"})
            if token.get("refresh_token"):
                self.credentials.set(token["refresh_token"])
            self._accept_token(token)
        return self._request(method, API + path, headers={"Authorization": "Bearer " + self.access_token}, **kwargs)

    def _calendar(self):
        calendar = self.data.get("calendar_id")
        if calendar:
            if calendar == "primary" or "@group.calendar.google.com" not in calendar:
                raise BlackboardSyncError(tr("The saved Google Calendar is not a dedicated secondary calendar."))
            try:
                self._api("GET", "/calendars/" + quote(calendar, safe=""))
                write_private_json(self.target_path, {"calendar_id": calendar})
                return calendar
            except ApiError as exc:
                if exc.status not in (404, 410):
                    raise
        calendar = self._api("POST", "/calendars", json={"summary": CALENDAR_NAME, "timeZone": "UTC"})["id"]
        self.data["calendar_id"] = calendar
        self._save()
        write_private_json(self.target_path, {"calendar_id": calendar})
        write_private_json(self.mapping_path, {})
        return calendar

    def _managed_events(self, calendar):
        page = None
        events = {}
        while True:
            params = {"privateExtendedProperty": "bbManaged=1", "maxResults": 2500}
            if page:
                params["pageToken"] = page
            body = self._api("GET", f"/calendars/{quote(calendar, safe='')}/events", params=params)
            for event in body.get("items", []):
                private = event.get("extendedProperties", {}).get("private", {})
                if private.get("bbKey") and event.get("status") != "cancelled":
                    events[private["bbKey"]] = event
            page = body.get("nextPageToken")
            if not page:
                return events

    def sync(self, *, reminders=False):
        """Sequential diff; checkpoint every write, retain old-but-still-present deadlines."""
        try:
            calendar = self._calendar()
            remote = self._managed_events(calendar)
            # Read only app-managed events; recovery never enumerates a user's calendars/events.
            mapping = {key: {"eventId": event["id"], "hash": event.get("extendedProperties", {})
                       .get("private", {}).get("bbHash", "")} for key, event in remote.items()}
            write_private_json(self.mapping_path, mapping)
            from blackboard_sync.courses import load_disabled
            hidden = load_disabled(self.config)
            state = State.load(self.config.state_file, backup=False)
            if not self.config.state_file.exists() or state.recovery:
                raise BlackboardSyncError(tr("Sync Blackboard successfully before syncing Google Calendar."))
            desired = {}
            for course_id, course in state.deadline_courses.items():
                if course_id in hidden:
                    continue
                for item in course.get("items", []):
                    due = parse_due(item.get("due"))
                    if not item.get("id") or due is None:
                        continue
                    key = f"{course_id}:{item['id']}"
                    course_name = course.get("name", "")
                    identity = [item.get("title", ""), due.isoformat(), item.get("url", ""), course_name, reminders]
                    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
                    stamp = lambda instant: instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    event = {"summary": f"[{course_name}] {item.get('title', '')}",
                             "status": "confirmed",
                             "start": {"dateTime": stamp(due - timedelta(minutes=30))},
                             "end": {"dateTime": stamp(due)},
                             "description": item.get("url", "") + "\n\n" + tr("This event is managed by Blackboard Sync."),
                             "reminders": {"useDefault": bool(reminders)},
                             "extendedProperties": {"private": {"bbKey": key, "bbHash": digest, "bbManaged": "1"}}}
                    desired[key] = (event, digest, due)
            base = f"/calendars/{quote(calendar, safe='')}/events"
            writes = 0
            for key, (event, digest, due) in desired.items():
                previous = mapping.get(key)
                if previous and previous["hash"] == digest:
                    continue
                if not previous and due < self.now() - timedelta(days=14):
                    continue
                if previous:
                    saved = self._api("PATCH", base + "/" + quote(previous["eventId"], safe=""), json=event)
                else:
                    # One ID per insertion, reused by HTTP retries. Deleted IDs can
                    # remain as tombstones in Google and must not be reused when
                    # a hidden course is enabled again. A successful insert whose
                    # local checkpoint was lost is recovered through bbKey.
                    event["id"] = secrets.token_hex(16)
                    try:
                        saved = self._api("POST", base, json=event)
                    except ApiError as exc:
                        if exc.status != 409:
                            raise
                        saved = self._api("PATCH", base + "/" + event["id"], json=event)
                mapping[key] = {"eventId": saved["id"], "hash": digest}
                write_private_json(self.mapping_path, mapping)
                writes += 1
            for key in set(mapping) - set(desired):
                try:
                    self._api("DELETE", base + "/" + quote(mapping[key]["eventId"], safe=""))
                except ApiError as exc:
                    if exc.status not in (404, 410):
                        raise
                del mapping[key]
                write_private_json(self.mapping_path, mapping)
                writes += 1
            self.data.update(last_sync=self.now().isoformat(), last_error=None, needs_reconnect=False)
            self._save()
            return writes
        except Exception as exc:
            self.data["last_error"] = str(exc) if isinstance(exc, BlackboardSyncError) else tr("Google Calendar sync failed.")
            if isinstance(exc, CalendarAuthExpired):
                self.data["needs_reconnect"] = True
            self._save()
            raise

    def disconnect(self, *, delete_calendar=False):
        calendar = self.data.get("calendar_id") or _read(self.target_path).get("calendar_id")
        if delete_calendar and not calendar:
            raise BlackboardSyncError(tr(
                "The calendar's saved ID is missing. Delete the existing Blackboard Deadlines calendar in Google Calendar settings."
            ))
        if calendar:
            if calendar == "primary" or "@group.calendar.google.com" not in calendar:
                raise BlackboardSyncError(tr("The saved Google Calendar is not a dedicated secondary calendar."))
        if delete_calendar:
            try:
                self._api("DELETE", "/calendars/" + quote(calendar, safe=""))
            except ApiError as exc:
                if exc.status not in (404, 410):
                    raise
            self.target_path.unlink(missing_ok=True)
        elif calendar:
            write_private_json(self.target_path, {"calendar_id": calendar})
        token = self.credentials.get()
        if token:
            try:
                self._request("POST", REVOKE, data={"token": token})
            except (ApiError, CalendarAuthExpired) as exc:
                if isinstance(exc, ApiError) and exc.status != 400:
                    raise
        self.credentials.clear()
        self.path.unlink(missing_ok=True)
        self.mapping_path.unlink(missing_ok=True)
        self.data = {}
        self.access_token = ""


def status(config: Config) -> CalendarStatus:
    data = _read(config.data_dir / "google-calendar.json")
    return CalendarStatus(bool(data.get("connected")), data.get("last_sync"), data.get("last_error"),
                          bool(data.get("needs_reconnect")))


def perform(config: Config, action: str, *, cancel=None, **options):
    """Cross-process serialization covers CLI, automatic sync and immediate GUI actions."""
    config.ensure_data_dir()
    with open(config.data_dir / "google-calendar.lock", "a+") as lock:
        if not try_lock(lock):
            raise BlackboardSyncError(tr("A Google Calendar operation is already running."))
        client = CalendarClient(config, cancel=cancel)
        try:
            return getattr(client, action)(**options)
        except Exception as exc:
            client.data["last_error"] = (str(exc) if isinstance(exc, BlackboardSyncError)
                                         else tr("Google Calendar operation failed."))
            if isinstance(exc, CalendarAuthExpired):
                client.data["needs_reconnect"] = True
            client._save()
            raise
