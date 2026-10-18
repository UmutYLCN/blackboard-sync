"""Release defaults and OAuth metadata delivery, independent of native GUI/network."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blackboard_sync import gcal
from blackboard_sync.config import Config
from blackboard_sync.menubar.model import AppModel
from blackboard_sync.menubar.settings_form import row_states, window_status

CLIENT = 'test-desktop.apps.googleusercontent.com'
METADATA = {'installed': {'client_id': CLIENT, 'client_secret': 'test-only-metadata'}}


def bundler():
    path = Path(__file__).resolve().parents[1] / 'packaging/google_oauth_bundle.py'
    spec = importlib.util.spec_from_file_location('test_oauth_bundle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('configured', [False, True])
def test_past_terms_coming_soon_cannot_start_jobs(tmp_path, configured):
    model = AppModel(tmp_path, datetime.now(timezone.utc), configured=configured,
                     session={'user': {'displayName': 'Student'}})
    model.past_terms = ['An old cached term']
    model.past_terms_loaded = True
    status = window_status(model)
    assert status.past_terms == ('Coming soon',)
    assert 'redesigned' in status.past_message
    assert not status.past_enabled and not status.past_running
    rows = row_states(status)
    assert not rows['past_term'].enabled
    assert rows['past_download'].button == 'Coming soon'
    assert not rows['past_download'].enabled
    assert not model.select_past_term('An old cached term')
    assert not model.past_terms_due()
    assert not model.begin('past_terms') and not model.begin('past_term')
    assert model.busy is None
    assert model.begin('sync')  # normal Blackboard sync remains available


def test_bundle_to_runtime_roundtrip_without_terminal_secret(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    root.mkdir()
    # The build consumes an Actions secret. Only Desktop client metadata is emitted.
    source = {**METADATA, 'refresh_token': 'must-not-be-bundled'}
    entries = bundler().oauth_datas(root, {'BBSYNC_GOOGLE_OAUTH_CLIENT_JSON': json.dumps(source)})
    source_path, destination = entries[0]
    assert destination == 'assets'
    assert json.loads(Path(source_path).read_text()) == METADATA
    if gcal.sys.platform != 'win32':
        assert Path(source_path).stat().st_mode & 0o777 == 0o600
    assets = tmp_path / 'frozen' / 'assets'
    assets.mkdir(parents=True)
    (assets / Path(source_path).name).write_bytes(Path(source_path).read_bytes())
    monkeypatch.setattr(gcal.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(gcal.sys, '_MEIPASS', str(assets.parent), raising=False)
    for key in ('BBSYNC_GOOGLE_OAUTH_CLIENT_FILE', 'BBSYNC_GOOGLE_CLIENT_ID', 'BBSYNC_GOOGLE_CLIENT_SECRET'):
        monkeypatch.delenv(key, raising=False)
    client = gcal.CalendarClient(Config(data_dir=tmp_path), http=object(), credentials=object())
    assert client._client_fields() == METADATA['installed']
    monkeypatch.setenv('BBSYNC_GOOGLE_CLIENT_SECRET', 'local-override')
    assert client._client_fields()['client_secret'] == 'local-override'


def test_local_json_works_without_exporting_secret(tmp_path, monkeypatch):
    metadata_file = tmp_path / 'desktop.json'
    metadata_file.write_text(json.dumps(METADATA))
    monkeypatch.setenv('BBSYNC_GOOGLE_OAUTH_CLIENT_FILE', str(metadata_file))
    monkeypatch.delenv('BBSYNC_GOOGLE_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('BBSYNC_GOOGLE_CLIENT_ID', raising=False)
    client = gcal.CalendarClient(Config(data_dir=tmp_path), http=object(), credentials=object())
    assert client._client_fields() == METADATA['installed']


def test_local_build_uses_ignored_json(tmp_path):
    directory = tmp_path / '.bbsync'
    directory.mkdir()
    (directory / 'google-oauth-client.json').write_text(json.dumps(METADATA))
    entries = bundler().oauth_datas(tmp_path, {})
    assert json.loads(Path(entries[0][0]).read_text()) == METADATA


def test_release_build_cannot_silently_omit_credentials(tmp_path):
    module = bundler()
    assert module.oauth_datas(tmp_path, {}) == []
    with pytest.raises(ValueError, match='required'):
        module.oauth_datas(tmp_path, {'BBSYNC_REQUIRE_GOOGLE_OAUTH': '1'})
    with pytest.raises(ValueError) as error:
        module.oauth_datas(tmp_path, {'BBSYNC_GOOGLE_OAUTH_CLIENT_JSON': 'private-invalid-input'})
    assert 'private-invalid-input' not in str(error.value)


def test_packaged_metadata_self_check_never_prints_secret(tmp_path, monkeypatch, capsys):
    import sys
    entry_path = Path(__file__).resolve().parents[1] / 'packaging/app_entry.py'
    spec = importlib.util.spec_from_file_location('test_release_entry', entry_path)
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    metadata_file = tmp_path / 'desktop.json'
    metadata_file.write_text(json.dumps(METADATA))
    monkeypatch.setenv('BBSYNC_GOOGLE_OAUTH_CLIENT_FILE', str(metadata_file))
    monkeypatch.setattr(sys, 'argv', ['Blackboard Sync', '--check-google-calendar'])
    assert entry.main() == 0
    assert capsys.readouterr().out == 'Google Calendar client configuration OK.\n'
    metadata_file.unlink()
    assert entry.main() == 1
    assert 'missing' in capsys.readouterr().err
