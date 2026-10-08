import json
from pathlib import Path

import pytest

from blackboard_sync.deleted import DeletedSelection, dismiss_missing, missing_outputs
from blackboard_sync.errors import AlreadyRunning
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock
from tests.test_sync import sync, SYLLABUS, SLIDES, SYLLABUS_DL, CSE, _touch_syllabus

SYLLABUS_KEY = 'attachment:_13004_1:_a11_1'


def test_missing_outputs_grouped_and_only_inside_destination(config, client, tmp_path):
    sync(config, client)
    state = State.load(config.state_file)
    assert missing_outputs(state, config.dest) == []
    (config.dest / SYLLABUS).unlink()
    state.record_output('outside', '../outside.pdf', 'sha', 1)
    state.record_output('absolute', str(tmp_path / 'outside.pdf'), 'sha', 1)
    rows = missing_outputs(state, config.dest)
    assert len(rows) == 1
    row = rows[0]
    assert row.key == SYLLABUS_KEY
    assert (row.term, row.course) == ('2026-2027 Güz', 'CSE303 Algorithm Analysis')
    assert row.name == Path(SYLLABUS).name
    assert row.folder == f'{CSE}/Syllabus'


def test_selective_refetch_downloads_only_selected_output(config, client, fake_bb):
    sync(config, client)
    state = State.load(config.state_file)
    for entry in state.outputs.values():
        (config.dest / entry['path']).unlink()
    fake_bb.calls.clear()
    report = sync(config, client, refetch_missing=True, refetch_keys={SYLLABUS_KEY})
    assert fake_bb.downloads() == [SYLLABUS_DL]
    assert (config.dest / SYLLABUS).exists()
    assert len(missing_outputs(State.load(config.state_file), config.dest)) == len(state.outputs) - 1
    assert sum(report.totals().values()) == 1
    sync(config, client)
    assert not (config.dest / SLIDES).exists()


def test_selective_refetch_does_not_download_new_or_changed_unselected_files(config, client, fake_bb):
    sync(config, client)
    (config.dest / SLIDES).unlink()
    state = State.load(config.state_file)
    selected = next(key for key, entry in state.outputs.items() if entry['path'] == SLIDES)
    _touch_syllabus(fake_bb, b'new unselected syllabus')
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True, refetch_keys={selected})
    assert SYLLABUS_DL not in fake_bb.downloads()
    assert len(fake_bb.downloads()) == 1
    assert (config.dest / SLIDES).exists()
    assert (config.dest / SYLLABUS).read_bytes() == b'%PDF syllabus v1'
    sync(config, client)
    assert (config.dest / SYLLABUS).read_bytes() == b'new unselected syllabus'


def test_dismiss_persists_and_excludes_from_list_select_all_and_all_refetch(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    (config.dest / SLIDES).unlink()
    dismiss_missing(config, config.dest, [SYLLABUS_KEY])
    state = State.load(config.state_file)
    assert state.outputs[SYLLABUS_KEY]['dismissed'] is True
    selection = DeletedSelection()
    selection.refresh(missing_outputs(state, config.dest))
    selection.select_all()
    assert SYLLABUS_KEY not in selection.keys()
    assert len(selection.keys()) == 1
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True)
    assert SYLLABUS_DL not in fake_bb.downloads()
    assert not (config.dest / SYLLABUS).exists()
    assert (config.dest / SLIDES).exists()
    sync(config, client, refetch_missing=True, refetch_keys={SYLLABUS_KEY})
    assert not (config.dest / SYLLABUS).exists()
    # Even an upstream change must not resurrect a dismissed output.
    _touch_syllabus(fake_bb, b'changed dismissed syllabus')
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True)
    assert SYLLABUS_DL not in fake_bb.downloads()
    assert not (config.dest / SYLLABUS).exists()


def test_dismiss_uses_run_lock_and_only_missing_entries(config, client):
    sync(config, client)
    dismiss_missing(config, config.dest, [SYLLABUS_KEY, 'unknown'])
    assert 'dismissed' not in State.load(config.state_file).outputs[SYLLABUS_KEY]
    (config.dest / SYLLABUS).unlink()
    with run_lock(config.lock_file):
        with pytest.raises(AlreadyRunning):
            dismiss_missing(config, config.dest, [SYLLABUS_KEY])
    assert 'dismissed' not in State.load(config.state_file).outputs[SYLLABUS_KEY]


def test_version_one_state_backward_compatible_and_flags_survive_updates(tmp_path):
    path = tmp_path / 'state.json'
    old = {'version': 1, 'items': {}, 'outputs': {'key': {'path': 'term/course/file.pdf', 'sha256': 'sha', 'size': 3}}}
    path.write_text(json.dumps(old))
    state = State.load(path)
    assert state.recovery is None
    assert len(missing_outputs(state, tmp_path / 'dest')) == 1
    state.dismiss_outputs(['key'])
    state.save()
    new = json.loads(path.read_text())
    assert new['version'] == old['version']
    assert new['outputs']['key']['dismissed'] is True
    assert new['items'] == old['items']
    restored = State.load(path)
    assert restored.recovery is None
    assert missing_outputs(restored, tmp_path / 'dest') == []
    restored.record_output('key', 'term/course/new.pdf', 'new-sha', 4)
    assert restored.output('key')['dismissed'] is True


def test_selection_retained_only_while_still_missing(config, client):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    selection = DeletedSelection()
    selection.refresh(missing_outputs(State.load(config.state_file), config.dest))
    selection.select(SYLLABUS_KEY, True)
    selection.select('unknown', True)
    assert selection.keys() == [SYLLABUS_KEY]
    selection.select(SYLLABUS_KEY, False)
    assert selection.keys() == []
    selection.select_all()
    sync(config, client, refetch_missing=True)
    selection.refresh(missing_outputs(State.load(config.state_file), config.dest))
    assert selection.keys() == []


def test_selective_refetch_preserves_unselected_attachment_in_same_item(config, client, fake_bb):
    route = '/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments'
    other_dl = '/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments/_other_1/download'
    fake_bb.routes[route]['results'].append({'id': '_other_1', 'fileName': 'other.pdf'})
    fake_bb.files[other_dl] = b'other attachment'
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    (config.dest / CSE / 'Syllabus/other.pdf').unlink()
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True, refetch_keys={SYLLABUS_KEY})
    assert fake_bb.downloads() == [SYLLABUS_DL]
    assert not (config.dest / CSE / 'Syllabus/other.pdf').exists()


def test_selective_refetch_notes_without_downloading_sibling_files(config, client, fake_bb):
    sync(config, client)
    state = State.load(config.state_file)
    notes = {k for k in state.outputs if k.startswith(('note:', 'announcement-note:'))}
    for output in state.outputs.values():
        (config.dest / output['path']).unlink()
    fake_bb.calls.clear()
    report = sync(config, client, refetch_missing=True, refetch_keys=notes)
    assert fake_bb.downloads() == []
    assert all((config.dest / state.outputs[key]['path']).exists() for key in notes)
    assert not (config.dest / SLIDES).exists()
    assert report.message == f'{len(notes)} dosya indirildi.'


def test_empty_selection_never_fetches_any_content(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True, refetch_keys=set())
    assert fake_bb.calls == []
    assert not (config.dest / SYLLABUS).exists()


def test_selected_missing_file_does_not_send_old_http_validator(config, client, fake_bb):
    fake_bb.etags[SYLLABUS_DL] = 'syllabus-v1'
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True, refetch_keys={SYLLABUS_KEY})
    assert fake_bb.downloads() == [SYLLABUS_DL]
    assert fake_bb.conditional_requests == []
    assert (config.dest / SYLLABUS).exists()


def test_missing_file_no_longer_on_blackboard_stays_listed_and_result_explains(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    fake_bb.routes['/learn/api/public/v1/courses/_13004_1/contents/_c1_1/children']['results'] = []
    report = sync(config, client, refetch_missing=True, refetch_keys={SYLLABUS_KEY})
    assert report.message == '0 dosya indirildi. 1 dosya indirilemedi; listede tutuldu.'
    assert [row.key for row in missing_outputs(State.load(config.state_file), config.dest)] == [SYLLABUS_KEY]


def test_selected_outputs_in_past_terms_can_be_restored(config, client, fake_bb):
    content = '/learn/api/public/v1/courses/_12001_1/contents'
    fake_bb.routes[content] = {'results': [{
        'id': '_past_item', 'title': 'Past lecture', 'modified': '2026-02-10T10:00:00Z',
        'contentHandler': {'id': 'resource/x-bb-file'},
    }]}
    fake_bb.routes[f'{content}/_past_item/attachments'] = {
        'results': [{'id': '_past_attachment', 'fileName': 'lecture.pdf'}]}
    fake_bb.routes['/learn/api/public/v1/courses/_12001_1/announcements'] = {'results': []}
    download = f'{content}/_past_item/attachments/_past_attachment/download'
    fake_bb.files[download] = b'past lecture'
    sync(config, client, all_terms=True)
    key = 'attachment:_12001_1:_past_attachment'
    path = config.dest / State.load(config.state_file).outputs[key]['path']
    path.unlink()
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True, refetch_keys={key})
    assert fake_bb.downloads() == [download]
    assert path.read_bytes() == b'past lecture'


def test_cli_selection_file_restores_only_requested_key(config, client, fake_bb, monkeypatch, capsys, tmp_path):
    from blackboard_sync import cli
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    (config.dest / SLIDES).unlink()
    selection = tmp_path / 'selection.json'
    selection.write_text(json.dumps([SYLLABUS_KEY]))
    monkeypatch.setattr(cli, 'open_client', lambda cfg: (client, {'user': {'id': '_900_1'}}))
    monkeypatch.setattr(cli, 'refresh_saved_cookies', lambda *a: None)
    fake_bb.calls.clear()
    args = ['--data-dir', str(config.data_dir), '--base-url', config.base_url,
            'sync', '--json', '--dest', str(config.dest), '--refetch-missing',
            '--refetch-selection', str(selection)]
    assert cli.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['message'] == '1 dosya indirildi.'
    assert fake_bb.downloads() == [SYLLABUS_DL]
    assert not (config.dest / SLIDES).exists()
    # The same CLI lock prevents races with another sync or a dismissal.
    with run_lock(config.lock_file):
        assert cli.main(args) == 4
    assert json.loads(capsys.readouterr().out)['status'] == 'locked'


def test_selection_does_not_record_unfetched_new_attachments(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    route = '/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments'
    other_dl = '/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments/_new_1/download'
    fake_bb.routes[route]['results'].append({'id': '_new_1', 'fileName': 'new.pdf'})
    fake_bb.files[other_dl] = b'new attachment'
    _touch_syllabus(fake_bb, b'%PDF syllabus v1')
    fake_bb.calls.clear()
    sync(config, client, refetch_missing=True, refetch_keys={SYLLABUS_KEY})
    assert fake_bb.downloads() == [SYLLABUS_DL]
    state = State.load(config.state_file)
    assert 'attachment:_13004_1:_new_1' not in state.outputs
    fake_bb.calls.clear()
    sync(config, client)
    assert other_dl in fake_bb.downloads()
    assert (config.dest / CSE / 'Syllabus/new.pdf').exists()
