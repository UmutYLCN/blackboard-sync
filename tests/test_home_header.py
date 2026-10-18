"""Home's greeting and its line about the next due dates (the model, with an injected clock)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from blackboard_sync import deadlines, i18n
from blackboard_sync.deadlines import DeadlineDay, DeadlinePage, DeadlineRow, count_due
from blackboard_sync.menubar.main_window_model import (
    T_NAV_OVERVIEW,
    T_NAV_START,
    deadline_subtitle,
    first_name,
    greeting,
    home_header,
    main_status,
)
from blackboard_sync.menubar.model import AppModel, RunOutcome

UTC = timezone.utc
ISTANBUL = timezone(timedelta(hours=3))
SUNDAY = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)  # a day with room before and after "now"
SESSION = {"saved_at": SUNDAY.timestamp(), "user": {"displayName": "Umut Yalçın"}}


def at(hour, minute=0, day=18):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def due(when, zone=UTC):
    return DeadlineRow("Homework", "CSE303", when.astimezone(zone), "https://bb.example.edu/x")


def page(*instants, zone=UTC):
    """A calendar page holding one row per instant (grouped by day like ``calendar_page``)."""
    days = {}
    for when in instants:
        days.setdefault(when.astimezone(zone).date(), []).append(due(when, zone))
    return DeadlinePage(tuple(DeadlineDay(day, str(day), False, tuple(rows)) for day, rows in sorted(days.items())), "")


@pytest.fixture
def turkish():
    i18n.set_language(i18n.TURKISH)
    yield
    i18n.set_language(i18n.ENGLISH)


# -- the greeting ---------------------------------------------------------------------------------

@pytest.mark.parametrize("hour, minute, expected", [
    (0, 0, "Good morning"), (5, 30, "Good morning"), (11, 59, "Good morning"),
    (12, 0, "Good afternoon"), (17, 59, "Good afternoon"),
    (18, 0, "Good evening"), (23, 59, "Good evening"),
])
def test_greeting_changes_at_noon_and_at_six(hour, minute, expected):
    assert greeting("Umut Yalçın", at(hour, minute), UTC) == f"{expected}, Umut"


def test_greeting_uses_the_local_hour_not_utc():
    now = at(8, 59)  # 11:59 in Istanbul, 08:59 in UTC
    assert greeting("Umut", now, ISTANBUL) == "Good morning, Umut"
    assert greeting("Umut", now + timedelta(minutes=1), ISTANBUL) == "Good afternoon, Umut"
    assert greeting("Umut", now + timedelta(minutes=1), UTC) == "Good morning, Umut"


@pytest.mark.parametrize("name, expected", [
    ("Umut Yalçın", "Umut"),
    ("Madonna", "Madonna"),  # one word
    ("  Ada   Lovelace ", "Ada"),
    ("İsmail Çağrı Öğrenci", "İsmail"),  # Turkish letters stay as they are
    ("UMUT YALÇIN", "UMUT"),
    ("", ""),
    ("   ", ""),
])
def test_first_name_is_the_first_word(name, expected):
    assert first_name(name) == expected


def test_greeting_without_a_name_is_just_the_greeting():
    assert greeting("", at(9), UTC) == "Good morning"
    assert greeting("  ", at(20), UTC) == "Good evening"
    assert greeting("Madonna", at(13), UTC) == "Good afternoon, Madonna"


# -- counting the due dates -----------------------------------------------------------------------

def test_count_due_today_and_in_the_next_seven_days():
    rows = page(at(12), at(23, 59), at(9, 31, day=19), at(9, 29, day=25), at(9, 30, day=25))
    # Sunday 09:30 now: two today, one tomorrow, one just inside the 7 days (till 09:30 next Sunday),
    # and one exactly at the end (not counted).
    assert count_due(rows, SUNDAY, UTC) == (2, 4)


def test_count_due_leaves_out_what_has_passed():
    assert count_due(page(at(9, 29), at(8), at(9, 30, day=17)), SUNDAY, UTC) == (0, 0)
    assert count_due(page(at(9, 30)), SUNDAY, UTC) == (1, 1)  # due right now is still due


def test_a_date_after_local_midnight_is_tomorrow_not_today():
    now = at(20, 30)  # 23:30 in Istanbul
    rows = page(at(21, 30), at(20, 45), zone=ISTANBUL)  # 00:30 tomorrow and 23:45 tonight, in Istanbul
    assert count_due(rows, now, ISTANBUL) == (1, 2)
    assert count_due(rows, now, UTC) == (2, 2)  # both are on the 18th in UTC


def test_count_due_on_an_empty_page():
    assert count_due(DeadlinePage((), ""), SUNDAY, UTC) == (0, 0)


# -- the subtitle ---------------------------------------------------------------------------------

def subtitle(*instants):
    return deadline_subtitle(page(*instants), SUNDAY, UTC)


def test_subtitle_names_today_and_the_week():
    assert subtitle(at(12), at(9, 31, day=19), at(10, day=21)) == "1 deadline today · 3 this week"
    assert subtitle(at(12), at(15), at(9, 31, day=19)) == "2 deadlines today · 3 this week"


def test_subtitle_without_anything_today_shows_the_week_only():
    assert subtitle(at(10, day=19)) == "1 deadline this week"
    assert subtitle(at(10, day=19), at(10, day=22)) == "2 deadlines this week"


def test_subtitle_does_not_repeat_itself_when_everything_is_today():
    assert subtitle(at(12)) == "1 deadline today"
    assert subtitle(at(12), at(18)) == "2 deadlines today"


def test_subtitle_when_nothing_is_due():
    assert subtitle() == "No deadlines this week"
    assert subtitle(at(9, 30, day=25)) == "No deadlines this week"  # exactly 7 days away
    assert subtitle(at(9, 29)) == "No deadlines this week"  # earlier today, passed
    assert deadline_subtitle(DeadlinePage((), ""), SUNDAY, UTC) == "No deadlines this week"


def test_subtitle_is_empty_until_due_dates_were_synced():
    assert deadline_subtitle(DeadlinePage(), SUNDAY, UTC) == ""  # the default page: "Sync to see due dates."
    assert DeadlinePage().message == deadlines.T_NOT_SYNCED


def test_subtitle_from_a_real_calendar_page(tmp_path):
    from blackboard_sync.state import State

    state = State(tmp_path / "state.json")
    state.deadline_courses["_1_1"] = {"name": "CSE303 Algorithms", "items": [
        {"id": f"c{i}", "title": f"Work {i}", "due": when.isoformat(), "content_id": None,
         "url": "https://bb.example.edu/x"}
        for i, when in enumerate([at(12), at(9, 31, day=19), at(9, 0, day=20), at(10, day=30), at(8)])]}
    calendar = deadlines.calendar_page(state, Path(tmp_path), SUNDAY, UTC)
    assert deadline_subtitle(calendar, SUNDAY, UTC) == "1 deadline today · 3 this week"
    state.deadline_courses["_1_1"]["unavailable"] = True  # the school closed the grade columns
    assert deadline_subtitle(deadlines.calendar_page(state, Path(tmp_path), SUNDAY, UTC), SUNDAY, UTC) == (
        "1 deadline today · 3 this week")


def test_hidden_courses_are_not_counted(tmp_path):
    from blackboard_sync.state import State

    state = State(tmp_path / "state.json")
    state.deadline_courses["_1_1"] = {"name": "CSE303", "items": [
        {"id": "a", "title": "A", "due": at(12).isoformat(), "content_id": None, "url": "u"}]}
    state.deadline_courses["_2_1"] = {"name": "MTH201", "items": [
        {"id": "b", "title": "B", "due": at(14).isoformat(), "content_id": None, "url": "u"}]}
    shown = deadlines.calendar_page(state, tmp_path, SUNDAY, UTC, hidden={"_2_1"})
    assert deadline_subtitle(shown, SUNDAY, UTC) == "1 deadline today"


# -- the header: fallbacks and the status ---------------------------------------------------------

def test_header_greets_by_name_with_the_due_dates():
    rows = page(at(12), at(10, day=20))
    assert home_header("Umut Yalçın", T_NAV_OVERVIEW, rows, SUNDAY, UTC) == (
        "Good morning, Umut", "1 deadline today · 2 this week")


@pytest.mark.parametrize("name, calendar", [
    (None, page(at(12))),  # not signed in
    ("Umut", None),  # no page to count
    ("Umut", DeadlinePage()),  # no due dates synced yet
])
def test_header_falls_back_to_the_plain_title(name, calendar):
    assert home_header(name, T_NAV_OVERVIEW, calendar, SUNDAY, UTC) == (T_NAV_OVERVIEW, "")


def test_header_of_nothing_due_still_greets():
    assert home_header("Umut", T_NAV_OVERVIEW, DeadlinePage((), ""), SUNDAY, UTC) == (
        "Good morning, Umut", "No deadlines this week")


def model(tmp_path, signed_in=True, configured=True):
    return AppModel(tmp_path, SUNDAY, configured=configured, session=SESSION if signed_in else None,
                    last=RunOutcome("ok", finished_at=SUNDAY))


def test_main_status_carries_the_header_and_keeps_the_sidebar_title(tmp_path):
    status = main_status(model(tmp_path), SUNDAY, page(at(12), at(10, day=20)), UTC)
    assert (status.home_heading, status.home_subtitle) == ("Good morning, Umut", "1 deadline today · 2 this week")
    assert status.overview_title == T_NAV_OVERVIEW  # the sidebar item stays "Home"


def test_main_status_without_a_page_or_without_signing_in_is_plain(tmp_path):
    status = main_status(model(tmp_path), SUNDAY)
    assert (status.home_heading, status.home_subtitle) == (T_NAV_OVERVIEW, "")
    status = main_status(model(tmp_path, signed_in=False), SUNDAY, page(at(12)), UTC)
    assert (status.home_heading, status.home_subtitle) == (T_NAV_OVERVIEW, "")


def test_first_run_keeps_the_get_started_title(tmp_path):
    status = main_status(AppModel(tmp_path, SUNDAY), SUNDAY, page(at(12)), UTC)
    assert status.first_run and (status.home_heading, status.home_subtitle) == (T_NAV_START, "")


# -- Turkish --------------------------------------------------------------------------------------

def test_turkish_greetings(turkish):
    assert greeting("Umut Yalçın", at(11, 59), UTC) == "Günaydın, Umut"
    assert greeting("Umut Yalçın", at(12, 0), UTC) == "İyi günler, Umut"
    assert greeting("Umut Yalçın", at(17, 59), UTC) == "İyi günler, Umut"
    assert greeting("Umut Yalçın", at(18, 0), UTC) == "İyi akşamlar, Umut"
    assert greeting("İsmail Çağrı", at(7), UTC) == "Günaydın, İsmail"
    assert greeting("", at(7), UTC) == "Günaydın"


def test_turkish_subtitles_keep_the_noun_singular(turkish):
    assert subtitle(at(12), at(9, 31, day=19), at(10, day=21)) == "Bugün 1 teslim tarihi · bu hafta 3"
    assert subtitle(at(12), at(15), at(9, 31, day=19)) == "Bugün 2 teslim tarihi · bu hafta 3"
    assert subtitle(at(10, day=19)) == "Bu hafta 1 teslim tarihi"
    assert subtitle(at(10, day=19), at(10, day=22)) == "Bu hafta 2 teslim tarihi"
    assert subtitle(at(12)) == "Bugün 1 teslim tarihi"
    assert subtitle() == "Bu hafta teslim tarihi yok"
    assert home_header("Umut Yalçın", "Ana sayfa", page(at(12)), SUNDAY, UTC) == (
        "Günaydın, Umut", "Bugün 1 teslim tarihi")
