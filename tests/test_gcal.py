"""Google Calendar contract tests, with no Google network or native vault calls."""
import copy
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from blackboard_sync import gcal
from blackboard_sync.config import Config
from blackboard_sync.errors import ApiError, BlackboardSyncError, CalendarAuthExpired
from blackboard_sync.session import write_private_json

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
CALENDAR = 'dedicated@group.calendar.google.com'


class Credentials:
    def __init__(self, token='refresh-private'):
        self.token = token

    def get(self):
        return self.token

    def set(self, token):
        self.token = token

    def clear(self):
        self.token = None


class Response:
    def __init__(self, body=None, status=200, headers=None):
        self.body, self.status_code, self.headers = body or {}, status, headers or {}

    def json(self):
        return copy.deepcopy(self.body)


class Google:
    def __init__(self):
        self.calendar = True
        self.events = {}
        self.calls = []
        self.responses = []
        self.fail_event = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, copy.deepcopy(kwargs)))
        if self.responses:
            return self.responses.pop(0)
        if url == gcal.TOKEN:
            return Response({'access_token': 'access-private', 'expires_in': 3600,
                             'refresh_token': 'refresh-private'})
        if url == gcal.REVOKE:
            return Response()
        path = url.removeprefix(gcal.API)
        if path == '/calendars' and method == 'POST':
            self.calendar = True
            self.events = {}
            return Response({'id': CALENDAR})
        if not self.calendar:
            return Response(status=404)
        if '/events' not in path:
            return Response({'id': CALENDAR})
        if method == 'GET':
            return Response({'items': list(self.events.values())})
        event_id = path.rsplit('/', 1)[-1]
        if method == 'DELETE':
            self.events.pop(event_id, None)
            return Response(status=204)
        event = copy.deepcopy(kwargs['json'])
        if method == 'POST':
            event_id = event['id']
        if event['extendedProperties']['private']['bbKey'] == self.fail_event:
            return Response(status=403)
        event['id'] = event_id
        self.events[event_id] = event
        return Response(event)

    def writes(self):
        return [(m, u) for m, u, _ in self.calls if u.startswith(gcal.API) and m != 'GET']


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BBSYNC_GOOGLE_CLIENT_ID', 'desktop-client')
    monkeypatch.setenv('BBSYNC_GOOGLE_OAUTH_CLIENT_FILE', str(tmp_path / 'no-oauth-config.json'))
    monkeypatch.delenv('BBSYNC_GOOGLE_CLIENT_SECRET', raising=False)
    config = Config(data_dir=tmp_path, dest=tmp_path)
    write_private_json(tmp_path / 'google-calendar.json', {'calendar_id': CALENDAR, 'connected': True})
    return gcal.CalendarClient(config, http=Google(), credentials=Credentials(), sleep=lambda _: None, now=lambda: NOW)


def deadlines(client, items=None):
    if items is None:
        items = [{'id': 'column', 'title': 'Essay', 'url': 'https://bb.example/work', 'due': (NOW + timedelta(days=1)).isoformat()}]
    write_private_json(client.config.state_file, {'version': 1, 'deadline_courses': {'course': {'name': 'CSE101', 'items': items}}})


def test_pkce_rfc7636():
    assert gcal.pkce_challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk') == 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'


@pytest.mark.parametrize('query', ['state=wrong&code=secret', 'code=secret', 'state=expected&state=evil&code=secret', 'state=%C3%BC&code=secret'])
def test_state_mismatch(query):
    with pytest.raises(BlackboardSyncError, match='state did not match'):
        gcal.callback_code(query, 'expected')


def test_state_valid_and_denied():
    assert gcal.callback_code('state=expected&code=abc', 'expected') == 'abc'
    with pytest.raises(BlackboardSyncError, match='cancelled'):
        gcal.callback_code('state=expected&error=access_denied', 'expected')


def test_token_refresh(client):
    deadlines(client)
    client.sync()
    tokens = [kw['data'] for _, url, kw in client.http.calls if url == gcal.TOKEN]
    assert len(tokens) == 1
    assert tokens[0]['grant_type'] == 'refresh_token'
    assert tokens[0]['refresh_token'] == 'refresh-private'
    assert 'access-private' not in client.path.read_text()
    assert 'refresh-private' not in client.path.read_text()
    client.expires = 0
    client.sync()
    assert sum(url == gcal.TOKEN for _, url, _ in client.http.calls) == 2


def test_invalid_grant(client):
    client.http.responses = [Response({'error': 'invalid_grant'}, 400)]
    with pytest.raises(CalendarAuthExpired):
        client.sync()
    status = gcal.status(client.config)
    assert status.needs_reconnect and status.last_error


def test_create_update_delete_idempotency_and_recovery(client):
    deadlines(client)
    assert client.sync() == 1
    event, = client.http.events.values()
    assert event['summary'] == '[CSE101] Essay'
    assert event['start']['dateTime'] == '2026-10-19T11:30:00Z'
    assert event['end']['dateTime'] == '2026-10-19T12:00:00Z'
    assert event['reminders'] == {'useDefault': False}
    assert event['extendedProperties']['private']['bbKey'] == 'course:column'
    assert 'https://bb.example/work' in event['description']
    client.http.calls.clear()
    assert client.sync() == 0
    assert client.http.writes() == []
    client.mapping_path.unlink()
    assert client.sync() == 0
    assert json.loads(client.mapping_path.read_text())['course:column']['eventId'] == event['id']
    deadlines(client, [{'id': 'column', 'title': 'Updated', 'url': 'https://bb.example/new',
                       'due': '2026-10-20T12:00:00+00:00'}])
    assert client.sync() == 1
    assert list(client.http.events.values())[0]['summary'] == '[CSE101] Updated'
    assert list(client.http.events.values())[0]['end']['dateTime'] == '2026-10-20T12:00:00Z'
    deadlines(client, [])
    assert client.sync() == 1
    assert not client.http.events
    assert gcal.status(client.config).last_sync == NOW.isoformat()


def test_hidden_course_deleted(client):
    from blackboard_sync.courses import set_enabled
    deadlines(client)
    client.sync()
    set_enabled(client.config, 'course', False)
    assert client.sync() == 1
    assert not client.http.events


def test_past_due_retained_but_old_not_created(client):
    deadlines(client)
    client.sync()
    client.now = lambda: NOW + timedelta(days=30)
    assert client.sync() == 0
    assert client.http.events
    client.http.events = {}
    assert client.sync() == 0
    assert not client.http.events


@pytest.mark.parametrize('status', [404, 410])
def test_calendar_deleted(client, status):
    deadlines(client)
    client.sync()
    client.http.responses = [Response(status=status)]
    assert client.sync() == 1
    assert any(method == 'POST' and url.endswith('/calendars') for method, url, _ in client.http.calls)


@pytest.mark.parametrize('response', [Response(status=429), Response(status=503),
    Response({'error': {'errors': [{'reason': 'rateLimitExceeded'}]}}, 403)])
def test_retry_backoff(client, response):
    sleeps = []
    client.sleep = sleeps.append
    client.http.responses = [response, response]
    assert client._request('GET', gcal.API + '/calendars/x/events') == {'items': []}
    assert sleeps == [1, 2]


def test_retry_exhaustion_and_retry_after(client):
    sleeps = []
    client.sleep = sleeps.append
    client.http.responses = [Response(status=429, headers={'Retry-After': '3'})] * 5
    with pytest.raises(ApiError):
        client._request('GET', gcal.API + '/calendars/x')
    assert sleeps == [3] * 4


def test_partial_failure_checkpoint(client):
    deadlines(client, [{'id': x, 'title': x, 'due': '2026-10-19T12:00:00Z', 'url': ''} for x in ('a', 'b')])
    client.http.fail_event = 'course:b'
    with pytest.raises(ApiError):
        client.sync()
    assert set(json.loads(client.mapping_path.read_text())) == {'course:a'}
    client.http.fail_event = None
    assert client.sync() == 1
    assert len(client.http.events) == 2


def test_disconnect_revokes_and_clears(client):
    deadlines(client)
    client.sync()
    client.disconnect(delete_calendar=True)
    assert not client.credentials.token
    assert not client.mapping_path.exists() and not client.path.exists()
    assert any(url == gcal.REVOKE for _, url, _ in client.http.calls)
    assert ('DELETE', gcal.API + '/calendars/' + CALENDAR.replace('@', '%40')) in client.http.writes()


def test_never_primary(client):
    client.data['calendar_id'] = 'primary'
    with pytest.raises(BlackboardSyncError, match='secondary'):
        client.sync()
    with pytest.raises(BlackboardSyncError, match='secondary'):
        client.disconnect(delete_calendar=True)
    assert client.http.calls == []


def test_cancel(client):
    client.cancel.set()
    with pytest.raises(BlackboardSyncError, match='cancelled'):
        client.sync()
    assert not client.http.calls


def test_connect_pkce_and_loopback(client, monkeypatch):
    """Exercise the stdlib redirect handler without a real listener or HTTP network."""
    class Server:
        server_port = 32123
        def __init__(self, address, handler):
            assert address == ('127.0.0.1', 0)
            self.handler = handler
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def handle_request(self):
            import io
            handler = object.__new__(self.handler)
            handler.path = '/?state=' + params['state'][0] + '&code=authorization'
            handler.send_response = lambda *_: None
            handler.send_header = lambda *_: None
            handler.end_headers = lambda: None
            handler.wfile = io.BytesIO()
            handler.do_GET()
    monkeypatch.setattr(gcal, 'HTTPServer', Server)
    params = {}
    def browser(url):
        params.update(parse_qs(urlsplit(url).query))
        return True
    client.data = {}
    write_private_json(client.target_path, {'calendar_id': CALENDAR})
    client.connect(open_browser=browser)
    assert client.data['calendar_id'] == CALENDAR
    assert params['redirect_uri'] == ['http://127.0.0.1:32123/']
    assert params['scope'] == [gcal.SCOPE]
    assert params['code_challenge_method'] == ['S256']
    data = client.http.calls[0][2]['data']
    assert gcal.pkce_challenge(data['code_verifier']) == params['code_challenge'][0]
    assert gcal.status(client.config).connected


def test_pagination(client):
    client.access_token, client.expires = 'access', float('inf')
    event = {'id': 'one', 'extendedProperties': {'private': {'bbKey': 'course:column'}}}
    client.http.responses = [Response({'items': [], 'nextPageToken': 'second'}), Response({'items': [event]})]
    assert set(client._managed_events(CALENDAR)) == {'course:column'}
    assert client.http.calls[-1][2]['params']['pageToken'] == 'second'


def test_cli_calendar_parser_and_status(tmp_path, capsys):
    from blackboard_sync.cli import main, build_parser
    for action in ('connect', 'status', 'sync', 'disconnect'):
        assert build_parser().parse_args(['calendar', action]).calendar_action == action
    assert main(['--data-dir', str(tmp_path), 'calendar', 'status']) == 0
    assert json.loads(capsys.readouterr().out)['connected'] is False


def test_recovery_with_bbkey_and_no_hash_updates_existing_id(client):
    deadlines(client)
    client.http.events['old'] = {'id': 'old', 'extendedProperties': {'private': {'bbKey': 'course:column'}}}
    assert client.sync() == 1
    assert set(client.http.events) == {'old'}
    assert client.http.events['old']['summary'] == '[CSE101] Essay'


def test_unmanaged_events_are_not_changed(client):
    deadlines(client, [])
    client.http.events['personal'] = {'id': 'personal', 'summary': 'Unrelated'}
    assert client.sync() == 0
    assert set(client.http.events) == {'personal'}
    params = next(kw['params'] for _, url, kw in client.http.calls if '/events' in url)
    assert params['privateExtendedProperty'] == 'bbManaged=1'


def test_reminders_parameter_updates_existing_event(client):
    deadlines(client)
    client.sync()
    assert client.sync(reminders=True) == 1
    assert list(client.http.events.values())[0]['reminders'] == {'useDefault': True}
    assert client.sync(reminders=True) == 0


@pytest.mark.parametrize('missing', [False, True])
def test_unreadable_blackboard_cache_does_not_delete_events(client, missing):
    deadlines(client)
    client.sync()
    if missing:
        client.config.state_file.unlink()
    else:
        client.config.state_file.write_text('{broken')
    client.http.calls.clear()
    with pytest.raises(BlackboardSyncError, match='Sync Blackboard'):
        client.sync()
    assert client.http.events
    assert client.http.writes() == []


def test_insert_conflict_uses_same_stable_id(client):
    deadlines(client)
    original = client.http.request
    def request(method, url, **kwargs):
        if method == 'POST' and url.endswith('/events'):
            return Response(status=409)
        return original(method, url, **kwargs)
    client.http.request = request
    assert client.sync() == 1
    event, = client.http.events.values()
    assert event['summary'] == '[CSE101] Essay'


def test_fallback_credentials_are_private(tmp_path):
    from tests.conftest import assert_owner_only
    store = gcal.CredentialStore(tmp_path, platform='linux')
    assert store.get() is None
    store.set('refresh-private')
    assert store.get() == 'refresh-private'
    assert_owner_only(store.path)
    store.clear()
    assert store.get() is None


def test_keychain_uses_stdin_not_argv(tmp_path, monkeypatch):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(gcal.sys, 'platform', 'darwin')
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='refresh-private\n')
    monkeypatch.setattr(gcal.subprocess, 'run', run)
    store = gcal.CredentialStore(tmp_path)
    store.set('refresh-private')
    args, kwargs = calls.pop()
    assert args == ['/usr/bin/security', '-i']
    assert 'refresh-private' in kwargs['input']
    assert store.get() == 'refresh-private'
    store.clear()
    assert all('refresh-private' not in str(args) for args, _ in calls)


def test_windows_credentials_roundtrip(tmp_path, monkeypatch):
    from types import SimpleNamespace
    values = {}
    class Missing(Exception):
        winerror = 1168
    def read(target, kind):
        if target not in values:
            raise Missing()
        return {'CredentialBlob': values[target].encode('utf-16-le')}
    def write(data, _):
        values[data['TargetName']] = data['CredentialBlob']
    def delete(target, *_):
        if target not in values:
            raise Missing()
        del values[target]
    monkeypatch.setattr(gcal.sys, 'platform', 'win32')
    monkeypatch.setitem(gcal.sys.modules, 'win32cred', SimpleNamespace(CredRead=read, CredWrite=write,
        CredDelete=delete, CRED_TYPE_GENERIC=1, CRED_PERSIST_LOCAL_MACHINE=2))
    monkeypatch.setitem(gcal.sys.modules, 'pywintypes', SimpleNamespace(error=Missing))
    store = gcal.CredentialStore(tmp_path)
    assert store.get() is None
    store.set('refresh-private')
    assert store.get() == 'refresh-private'
    store.clear()
    assert store.get() is None
    store.clear()  # already absent is safe


def test_missing_desktop_secret_explains_local_configuration(client):
    client.http.responses = [Response({'error': 'invalid_request',
        'error_description': 'client_secret is missing. private-response-content'}, 400)]
    with pytest.raises(BlackboardSyncError, match='BBSYNC_GOOGLE_CLIENT_SECRET') as error:
        client._request('POST', gcal.TOKEN, data={})
    assert not isinstance(error.value, CalendarAuthExpired)
    assert 'private-response-content' not in str(error.value)


def test_desktop_secret_is_used_only_at_token_endpoint(client, monkeypatch):
    monkeypatch.setenv('BBSYNC_GOOGLE_CLIENT_SECRET', 'private-client-metadata')
    deadlines(client)
    client.sync()
    for _, url, options in client.http.calls:
        if url == gcal.TOKEN:
            assert options['data']['client_secret'] == 'private-client-metadata'
        else:
            assert 'private-client-metadata' not in str(options)
    assert 'private-client-metadata' not in client.path.read_text()


def test_hide_then_reenable_uses_new_id_despite_google_tombstone(client):
    from blackboard_sync.courses import set_enabled
    deadlines(client)
    original_request = client.http.request
    deleted = set()
    def request(method, url, **options):
        event_id = url.rsplit('/', 1)[-1]
        if method == 'DELETE' and '/events/' in url:
            deleted.add(event_id)
        if method == 'POST' and url.endswith('/events') and options['json']['id'] in deleted:
            return Response(status=409)
        if method == 'PATCH' and event_id in deleted:
            return Response(status=410)
        return original_request(method, url, **options)
    client.http.request = request
    assert client.sync() == 1
    old_id, = client.http.events
    set_enabled(client.config, 'course', False)
    assert client.sync() == 1
    assert old_id in deleted
    set_enabled(client.config, 'course', True)
    assert client.sync() == 1
    new_id, = client.http.events
    assert new_id != old_id
    assert client.http.events[new_id]['status'] == 'confirmed'
    assert client.sync() == 0


def test_disconnect_keep_then_reconnect_delete_without_sync(client, monkeypatch):
    deadlines(client)
    client.sync()
    client.disconnect()
    assert not client.path.exists() and not client.mapping_path.exists()
    assert client.credentials.get() is None
    assert json.loads(client.target_path.read_text()) == {'calendar_id': CALENDAR}
    # Same authenticated user reauthorizes; no sync occurs before Disconnect.
    resumed = gcal.CalendarClient(client.config, http=client.http, credentials=Credentials(),
                                  sleep=lambda _: None, now=lambda: NOW)
    assert not resumed.data.get('calendar_id')
    resumed.data['connected'] = True
    resumed._save()
    resumed.disconnect(delete_calendar=True)
    deletes = [(m, u) for m, u, _ in client.http.calls if m == 'DELETE' and '/events' not in u]
    assert deletes == [('DELETE', gcal.API + '/calendars/' + CALENDAR.replace('@', '%40'))]
    assert not resumed.target_path.exists()
    assert not resumed.path.exists()
    assert resumed.credentials.get() is None


def test_delete_unknown_calendar_reports_failure_instead_of_success(client):
    client.data.pop('calendar_id')
    with pytest.raises(BlackboardSyncError, match="saved ID is missing"):
        client.disconnect(delete_calendar=True)
    assert client.credentials.get() == 'refresh-private'
    assert not any(url == gcal.REVOKE for _, url, _ in client.http.calls)


def test_failed_calendar_delete_does_not_revoke_or_forget(client):
    client.target_path.write_text(json.dumps({'calendar_id': CALENDAR}))
    client.access_token, client.expires = 'access-private', float('inf')
    client.http.responses = [Response(status=403)]
    with pytest.raises(ApiError):
        client.disconnect(delete_calendar=True)
    assert client.target_path.exists() and client.credentials.get()
    assert not any(url == gcal.REVOKE for _, url, _ in client.http.calls)


@pytest.mark.parametrize('status', [404, 410])
def test_delete_already_missing_calendar_clears_reference(client, status):
    client.target_path.write_text(json.dumps({'calendar_id': CALENDAR}))
    client.access_token, client.expires = 'access-private', float('inf')
    client.http.responses = [Response(status=status)]
    client.disconnect(delete_calendar=True)
    assert not client.target_path.exists()
    assert not client.credentials.get()
