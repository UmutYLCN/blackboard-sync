from datetime import datetime, timedelta, timezone

import pytest

from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.main_window_model import main_status
from blackboard_sync.menubar.model import AppModel, RecentItem, RecentSeen

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


class Clock:
    seconds = 0.0

    def __call__(self):
        return self.seconds

    def expose(self, tracker, rows, seconds=3, active=True):
        changed = tracker.observe(rows, active)
        for _ in range(round(seconds * 4)):
            self.seconds += 0.25
            changed |= tracker.observe(rows, active)
        return changed


def row(path="a.pdf", age=timedelta()):
    return RecentItem(path, "CSE303", (NOW - age).isoformat())


def key(item):
    return item.path, item.at


def test_seen_after_three_seconds_keeps_badge_until_next_visit():
    clock, item = Clock(), row()
    tracker = RecentSeen(clock=clock)
    tracker.show()
    assert not clock.expose(tracker, [key(item)], seconds=2.75)
    assert tracker.is_new(*key(item), NOW)
    assert clock.expose(tracker, [key(item)], seconds=0.25)
    assert tracker.seen == {item.path: item.at}
    assert tracker.is_new(*key(item), NOW)  # ordinary refreshes don't remove it
    tracker.show()  # bringing an already open window forward is the same visit
    assert tracker.is_new(*key(item), NOW)
    tracker.hide()
    tracker.show()
    assert not tracker.is_new(*key(item), NOW)


@pytest.mark.parametrize("interruption", ["inactive", "offscreen", "page", "sleep"])
def test_exposure_must_be_continuous_and_in_active_overview(interruption):
    clock, item = Clock(), row()
    tracker = RecentSeen(clock=clock)
    tracker.show()
    clock.expose(tracker, [key(item)], seconds=2)
    if interruption == "inactive":
        clock.expose(tracker, [key(item)], seconds=10, active=False)
    elif interruption == "offscreen":
        clock.expose(tracker, [], seconds=10)
    elif interruption == "page":
        tracker.hide()
        assert not clock.expose(tracker, [key(item)], seconds=10)
        tracker.show()
    else:
        clock.seconds += 30
    assert not clock.expose(tracker, [key(item)], seconds=2.75)
    assert tracker.is_new(*key(item), NOW)
    assert clock.expose(tracker, [key(item)], seconds=0.25)


def test_only_on_screen_rows_become_seen_and_new_arrivals_get_own_timer():
    clock = Clock()
    tracker = RecentSeen(clock=clock)
    first, below_fold = row(), row("b.pdf")
    tracker.show()
    assert clock.expose(tracker, [key(first)])
    arrival = row("c.pdf")
    assert not clock.expose(tracker, [key(first), key(arrival)], seconds=2.75)
    tracker.hide()
    tracker.show()
    assert not tracker.is_new(*key(first), NOW)
    assert tracker.is_new(*key(below_fold), NOW)
    assert tracker.is_new(*key(arrival), NOW)


def test_open_removes_badge_immediately_but_a_new_download_is_unread():
    item = row()
    tracker = RecentSeen()
    tracker.show()
    assert tracker.is_new(*key(item), NOW)
    assert tracker.opened(item)
    assert not tracker.is_new(*key(item), NOW)
    assert not tracker.opened(item)
    newer = row(age=-timedelta(seconds=1))
    assert tracker.is_new(*key(newer), NOW + timedelta(seconds=1))


@pytest.mark.parametrize("age, expected", [
    (timedelta(), True), (timedelta(days=7), True),
    (timedelta(days=7, microseconds=1), False), (timedelta(days=30), False),
    (-timedelta(seconds=1), False),
])
def test_seven_day_expiry_and_future_dates(age, expected):
    item = row(age=age)
    assert RecentSeen().is_new(*key(item), NOW) is expected


def test_expiry_applies_even_during_a_visit():
    item = row(age=timedelta(days=7))
    tracker = RecentSeen()
    tracker.show()
    assert tracker.is_new(*key(item), NOW)
    assert not tracker.is_new(*key(item), NOW + timedelta(seconds=1))


def test_state_survives_restart_and_only_retains_current_download_versions(tmp_path):
    clock = Clock()
    first, unseen = row(), row("b.pdf")
    model = AppModel(tmp_path / "University", NOW, recent=[first, unseen],
                     recent_seen=RecentSeen(clock=clock))
    model.recent_seen.show()
    clock.expose(model.recent_seen, [key(first)])
    config = Config(data_dir=tmp_path / "data", dest=model.dest)
    jobs.save_model(config, model)
    restored = jobs.load_model(config, NOW, autostart=False)
    assert [r.is_new for r in main_status(restored, NOW).recent] == [False, True]
    restored.recent = [row(age=-timedelta(seconds=1))]
    assert restored.saved_state()["recent_seen"] == {}


def test_old_state_and_corrupt_markers_do_not_hide_new_downloads(tmp_path):
    item = row()
    tracker = RecentSeen({"a.pdf": "bad", "b.pdf": None, "c.pdf": 123})
    assert tracker.seen == {}
    assert RecentSeen([]).seen == {}
    assert tracker.is_new(*key(item), NOW)
    assert not tracker.is_new("bad.pdf", "bad", NOW)
    model = AppModel(tmp_path, NOW, recent=[item])
    assert main_status(model, NOW).recent[0].is_new


@pytest.mark.parametrize("move", [True, False])
def test_destination_changes_preserve_seen_only_when_files_move(tmp_path, move):
    from blackboard_sync.menubar.model import DEST_MOVE, DEST_KEEP

    clock, item = Clock(), row()
    tracker = RecentSeen(clock=clock)
    model = AppModel(tmp_path / "old", NOW, recent=[item], recent_seen=tracker)
    tracker.opened(item)
    tracker.show()
    model.apply_settings(tmp_path / "new", school_changed=False, dest_choice=DEST_MOVE if move else DEST_KEEP)
    assert bool(model.saved_state()["recent_seen"]) is move
    if not move:
        assert tracker.snapshot == {}  # continue tracking this visit in the new folder
        model.recent = [item]
        assert tracker.is_new(*key(item), NOW)
        assert clock.expose(tracker, [key(item)])
