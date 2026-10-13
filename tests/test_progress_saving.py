"""A sync that is killed midway keeps what it finished, and leaves no temp files behind."""

from __future__ import annotations

import json
import os
import shutil
from datetime import timedelta

import pytest

from blackboard_sync import cli
from blackboard_sync import state as state_mod
from blackboard_sync import sync as sync_mod
from blackboard_sync.state import State
from blackboard_sync.sync import Syncer, remove_stale_partials, run_lock

from .test_sync import CSE, SYLLABUS, SYLLABUS_DL, files_under, sync

SYLLABUS_ITEM_DL = "/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments/_a2_1/download"
ATTACHMENTS = "/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments"


class Killed(BaseException):
    """The process dies: nothing after this point runs, and nothing more reaches the disk."""


@pytest.fixture
def writes(monkeypatch):
    """Count the writes of state.json; ``writes.dead = True`` makes every later one fail."""
    real = state_mod.write_private_json

    class Writes(list):
        dead = False

    log = Writes()

    def tracking(path, data):
        if log.dead:
            raise OSError("the process is gone")
        log.append(json.loads(json.dumps(data)))
        real(path, data)

    monkeypatch.setattr(state_mod, "write_private_json", tracking)
    return log


def kill_on_item(monkeypatch, writes, n):
    """Kill the run when its n-th item is about to be processed."""
    real = Syncer.process_item
    seen = []

    def process_item(self, *args, **kwargs):
        if len(seen) == n - 1:
            writes.dead = True
            raise Killed
        seen.append(args[1]["id"])
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Syncer, "process_item", process_item)
    return seen


def test_killed_run_keeps_the_items_it_finished_and_the_next_run_fetches_only_the_rest(
    config, client, fake_bb, monkeypatch, writes
):
    monkeypatch.setattr(State, "save_interval", 0)
    sync(config, client)
    everything = sorted(fake_bb.downloads())
    assert len(everything) >= 2
    config.state_file.unlink()
    shutil.rmtree(config.dest)

    with monkeypatch.context() as patch:
        seen = kill_on_item(patch, writes, 3)
        fake_bb.calls.clear()
        with pytest.raises(Killed):
            sync(config, client)
        first = sorted(fake_bb.downloads())
    recorded = State.load(config.state_file)
    assert len(seen) == 2 and first
    assert set(recorded.items) == {f"content:_13004_1:{i}" for i in seen}

    writes.dead = False
    fake_bb.calls.clear()
    sync(config, client)
    rest = sorted(fake_bb.downloads())
    assert sorted(first + rest) == everything
    assert not set(first) & set(rest)


def test_killed_run_without_any_checkpoint_loses_its_progress(config, client, fake_bb, monkeypatch, writes):
    """The reproduction of the bug: with one write per course the first run records nothing."""
    monkeypatch.setattr(State, "checkpoint", lambda self, force=False: True)
    kill_on_item(monkeypatch, writes, 3)
    with pytest.raises(Killed):
        sync(config, client)
    assert not config.state_file.exists()


def test_file_downloaded_before_the_kill_in_the_same_item_is_not_fetched_again(
    config, client, fake_bb, monkeypatch, writes
):
    monkeypatch.setattr(State, "save_interval", 0)
    fake_bb.routes[ATTACHMENTS]["results"].append({"id": "_a2_1", "fileName": "extra.pdf"})
    fake_bb.files[SYLLABUS_ITEM_DL] = b"%PDF extra"
    real = type(client).download
    calls = []

    def download(self, url, *args, **kwargs):
        calls.append(url)
        if url == SYLLABUS_ITEM_DL and writes.dead is False and len(calls) == 2:
            writes.dead = True
            raise Killed
        return real(self, url, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(client), "download", download)
        with pytest.raises(Killed):
            sync(config, client)
    state = State.load(config.state_file)
    assert "content:_13004_1:_c11_1" not in state.items
    assert "attachment:_13004_1:_a11_1" in state.outputs

    writes.dead = False
    fake_bb.calls.clear()
    sync(config, client)
    assert SYLLABUS_DL not in fake_bb.downloads()
    assert SYLLABUS_ITEM_DL in fake_bb.downloads()
    assert State.load(config.state_file).items["content:_13004_1:_c11_1"]["outputs"][:2] == [
        "attachment:_13004_1:_a11_1", "attachment:_13004_1:_a2_1",
    ]


def test_changed_item_is_not_treated_as_interrupted(config, client, fake_bb):
    sync(config, client)
    from .test_sync import _route_item
    _route_item(fake_bb, "_c11_1")["modified"] = "2026-10-01T00:00:00.000Z"
    fake_bb.files[SYLLABUS_DL] = b"%PDF syllabus v2"
    fake_bb.calls.clear()
    sync(config, client)
    assert SYLLABUS_DL in fake_bb.downloads()
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v2"


# -- throttling ---------------------------------------------------------
class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(state_mod, "_monotonic", clock)
    return clock


def test_checkpoints_are_at_most_one_write_per_interval(tmp_path, writes, clock):
    state = State(tmp_path / "state.json")
    for i in range(50):
        state.record_item(f"content:c:{i}", "m", [], "t")
        assert state.checkpoint()
        clock.now += 0.05  # 50 items in 2.5 seconds
    assert len(writes) == 1
    clock.now += 5
    state.checkpoint()
    assert len(writes) == 2
    assert len(writes[-1]["items"]) == 50


def test_checkpoint_writes_only_when_something_changed(tmp_path, writes, clock):
    state = State(tmp_path / "state.json")
    state.checkpoint(force=True)
    assert writes == []
    state.record_item("content:c:1", "m", [], "t")
    state.checkpoint()
    clock.now += 60
    state.checkpoint(force=True)
    assert len(writes) == 1


def test_force_ignores_the_interval(tmp_path, writes, clock):
    state = State(tmp_path / "state.json")
    state.record_item("content:c:1", "m", [], "t")
    state.checkpoint()
    state.record_item("content:c:2", "m", [], "t")
    state.checkpoint()
    assert len(writes) == 1
    state.checkpoint(force=True)
    assert len(writes) == 2 and not state.dirty


def test_a_run_writes_far_less_often_than_it_has_items(config, client, monkeypatch, writes, clock):
    sync(config, client)
    throttled = len(writes)
    items = len(State.load(config.state_file).items)
    assert items > 3
    # first change at once, then one per course plus the end of the run
    assert throttled < items


def test_complete_run_ends_with_the_same_state_however_often_it_saved(config, client, tmp_path, monkeypatch):
    from blackboard_sync.config import Config

    # Both runs stamp due dates with the same time, even when they straddle a second.
    monkeypatch.setattr(sync_mod, "_now_iso", lambda: "2026-10-03T12:00:00+00:00")
    monkeypatch.setattr(State, "save_interval", 0)
    sync(config, client)
    eager = json.loads(config.state_file.read_text(encoding="utf-8"))
    other = Config(base_url=config.base_url, dest=tmp_path / "other", data_dir=tmp_path / "other-data")
    monkeypatch.setattr(State, "save_interval", 10**9)
    sync(other, client)
    lazy = json.loads(other.state_file.read_text(encoding="utf-8"))
    assert eager == lazy
    assert eager["items"] and eager["outputs"]


# -- failing writes -----------------------------------------------------
def test_failed_write_never_aborts_the_sync(config, client, writes):
    writes.dead = True
    report = sync(config, client)
    assert report.status == "ok" and report.totals()["new_files"] >= 3
    assert SYLLABUS in files_under(config.dest)
    assert any("Could not save progress" in w for w in report.warnings)
    assert not config.state_file.exists()


def test_a_later_write_recovers_after_a_failed_one(tmp_path, writes, clock):
    state = State(tmp_path / "state.json")
    state.record_item("content:c:1", "m", [], "t")
    writes.dead = True
    assert state.checkpoint() is False
    assert state.dirty and "OSError" in state.save_error
    writes.dead = False
    clock.now += 6
    assert state.checkpoint() is True
    assert not state.dirty and state.save_error is None
    assert "content:c:1" in State.load(state.path).items


def test_state_file_stays_private_and_atomic(config, client, monkeypatch):
    from .conftest import assert_owner_only

    monkeypatch.setattr(State, "save_interval", 0)
    sync(config, client)
    assert_owner_only(config.state_file)
    assert not [p for p in config.data_dir.iterdir() if p.name.startswith(".tmp-")]
    assert State.load(config.state_file).items


# -- leftover temp files ------------------------------------------------
def _partial(config, name=".bbsync-deadbeef.partial", age=0):
    path = config.dest / CSE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 1024)
    if age:
        old = path.stat().st_mtime - age
        os.utime(path, (old, old))
    return path


def test_under_the_run_lock_every_leftover_partial_goes_whatever_its_age(config, client):
    fresh = _partial(config)
    other = _partial(config, ".bbsync-notes.txt")
    sync(config, client, lock_held=True)
    assert not fresh.exists() and other.exists()


def test_without_the_lock_a_recent_partial_is_left_to_a_possible_live_run(config, client):
    live = _partial(config, age=60)
    old = _partial(config, ".bbsync-old.partial", age=11 * 60)
    sync(config, client)
    assert live.exists() and not old.exists()


def test_dry_run_keeps_every_partial_even_under_the_lock(config, client):
    sync(config, client)
    partial = _partial(config)
    sync(config, client, dry_run=True, lock_held=True)
    assert partial.exists()


def test_remove_stale_partials_age_zero_removes_all(config):
    paths = [_partial(config), _partial(config, ".bbsync-b.partial")]
    assert remove_stale_partials(config.dest, max_age=timedelta(0)) == 2
    assert not any(p.exists() for p in paths)


def test_cli_sync_holds_the_lock_and_cleans_leftover_partials(config, client, fake_bb, monkeypatch, capsys):
    leftover = _partial(config)
    seen = []
    real_run_sync = cli.run_sync

    def run_sync(*args, **kwargs):
        seen.append(kwargs.get("lock_held"))
        with pytest.raises(sync_mod.AlreadyRunning):
            with run_lock(config.lock_file):  # the CLI really holds it here
                pass
        return real_run_sync(*args, **kwargs)

    monkeypatch.setattr(cli, "run_sync", run_sync)
    monkeypatch.setattr(cli, "open_client", lambda cfg: (client, {"user": {"id": "_900_1"}}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *a: None)
    args = ["--data-dir", str(config.data_dir), "--base-url", config.base_url,
            "sync", "--json", "--dest", str(config.dest)]
    assert cli.main(args) == 0
    assert seen == [True]
    assert not leftover.exists()
