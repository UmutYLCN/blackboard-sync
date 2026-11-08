"""The card before the first download at a school whose current term is not clear (``term_confirm``).

Only a first sync at a school (no state for it) with an unclear term choice asks; it downloads
and saves nothing until the student confirms. Confirm keeps the ticked courses and asks once;
Not now saves nothing, so the next sync asks again. A school with state, such as the first
school with its files, and the terminal's sync never ask.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from blackboard_sync import cli, courses, term_confirm
from blackboard_sync.menubar.model import AppModel, RunOutcome, parse_sync_output, sync_arguments
from blackboard_sync.settings import Settings
from blackboard_sync.state import State

from .test_latest_term import FALL, FALL_END, term
from .test_old_terms import TERMS, archive  # noqa: F401
from .test_sync import NOW, sync

SCHOOL = "blackboard.example.edu"


def undated(bb):
    """The fixture school's terms lose their dates: the first sync cannot be sure of the term."""
    for tid in ("_50_1", "_40_1"):
        bb.routes[f"{TERMS}/{tid}"].pop("availability")


def first_sync(config, client, **kwargs):
    return sync(config, client, confirm_first=True, **kwargs)


# -- when the card is needed ---------------------------------------------------------

def test_a_dated_term_with_a_season_name_is_clear():
    fall = term("_fall", "2026-2027 Güz", FALL, FALL_END, courses=["_c1"])
    assert term_confirm.ambiguity([fall]) == []
    # Turkish and English records of one semester, merged, are still one clear term.
    both = term("_fall", "2026-2027 Güz", FALL, FALL_END, courses=["_c1"])
    both.names.append("2026-2027 Fall")
    assert term_confirm.ambiguity([both]) == []


def test_unclear_terms_are_named():
    fall = term("_fall", "2026-2027 Güz", FALL, FALL_END, courses=["_c1"])
    assert term_confirm.ambiguity([term("_u", "2026-2027 Güz", courses=["_c2"])]) == [term_confirm.UNDATED]
    stale = term("_s", "2026-2027 Güz", "2020-09-01T00:00:00Z", "2021-01-31T00:00:00Z",
                 created=["2026-08-01T00:00:00Z"])
    assert term_confirm.ambiguity([stale]) == [term_confirm.STALE_DATES]
    block = term("_b", "2026-2027 Güz", "2026-11-01T00:00:00Z", FALL_END, courses=["_c3"])
    assert term_confirm.ambiguity([fall, block]) == [term_confirm.SEVERAL_STARTS]
    odd = term("_o", "Term 1 (Sept)", FALL, FALL_END, courses=["_c4"])
    assert term_confirm.ambiguity([odd]) == [term_confirm.UNKNOWN_NAME]


def test_courses_without_a_term_or_no_courses_need_no_card():
    no_term = term(None, "No term", courses=["_c1"])
    assert term_confirm.ambiguity([no_term]) == []
    assert term_confirm.ambiguity([term("_u", "Term")]) == []  # nothing to download
    assert term_confirm.proposal("https://bb.example.edu", [term("_u", "Term")], []) is None


def test_school_state_is_any_record_of_that_school(tmp_path):
    url = f"https://{SCHOOL}"
    empty = State(tmp_path / "state.json")
    assert not term_confirm.has_school_state(empty, url)
    # A state from before schools were recorded is the school in use: the first school's users.
    legacy = State(tmp_path / "state.json", {"outputs": {"k": {"path": "T/C/a.pdf"}}})
    assert term_confirm.has_school_state(legacy, url)
    same = State(tmp_path / "state.json", {"school": SCHOOL})
    assert term_confirm.has_school_state(same, url)
    other = State(tmp_path / "state.json", {"school": "bb.other.edu", "outputs": {"k": {"path": "T/C/a.pdf"}}})
    assert not term_confirm.has_school_state(other, url)
    back = State(tmp_path / "state.json", {"school": "bb.other.edu",
                                           "outputs": {"k": {"path": "T/C/a.pdf", "school": SCHOOL}}})
    assert term_confirm.has_school_state(back, url)
    unreadable = State(tmp_path / "state.json")
    unreadable.recovery = "Could not read state.json"
    assert term_confirm.has_school_state(unreadable, url)


# -- whole syncs --------------------------------------------------------------------

def test_clear_first_sync_downloads_as_before(config, client, archive):
    report = first_sync(config, client)
    assert report.status == "ok" and report.confirm is None
    assert archive.downloads()


def test_unclear_first_sync_downloads_and_saves_nothing_and_lists_the_courses(config, client, archive):
    undated(archive)
    report = first_sync(config, client)
    assert report.status == "confirm"
    assert archive.downloads() == []
    assert not config.state_file.exists() and not config.last_run_file.exists()
    assert not config.root.exists() or not any(config.root.rglob("*.pdf"))
    card = report.confirm
    assert card["school"] == SCHOOL and card["reasons"] == [term_confirm.UNDATED]
    assert card["terms"] == ["2026-2027 Güz"]
    assert [c["code"] for c in card["courses"]] == ["COE305", "CSE303", "MTH201"]
    assert all(c["id"] and c["term"] == "2026-2027 Güz" for c in card["courses"])
    assert report.to_dict()["confirm"] == card
    # Not now: nothing was saved, so the next sync asks again.
    again = first_sync(config, client)
    assert again.status == "confirm" and archive.downloads() == []


def test_confirm_downloads_only_the_ticked_courses_and_asks_once(config, client, archive):
    undated(archive)
    card = first_sync(config, client).confirm
    ids = {c["code"]: c["id"] for c in card["courses"]}
    keep, drop = ids["CSE303"], ids["MTH201"]
    term_confirm.confirm(config, card, [c["id"] for c in card["courses"] if c["id"] != drop])
    assert term_confirm.load_confirmed(config) == {SCHOOL}
    assert courses.load_disabled(config) == {drop}

    archive.calls.clear()
    report = first_sync(config, client)
    assert report.status == "ok"
    assert any(f"/courses/{keep}/" in call for call in archive.downloads())
    assert not any(f"/courses/{drop}/" in call for call in archive.calls)
    assert first_sync(config, client).status == "ok"  # asked once


def test_an_existing_school_with_its_state_never_sees_the_card(config, client, archive):
    """The first school's users: state.json holds its files, so nothing changes for them."""
    sync(config, client)
    undated(archive)
    assert first_sync(config, client).status == "ok"
    data = json.loads(config.state_file.read_text(encoding="utf-8"))
    data.pop("school")  # a state file from before schools were recorded
    config.state_file.write_text(json.dumps(data), encoding="utf-8")
    assert first_sync(config, client).status == "ok"


def test_the_terminal_sync_and_dry_runs_never_ask(config, client, archive):
    undated(archive)
    assert first_sync(config, client, dry_run=True).status == "ok"
    assert sync(config, client).status == "ok" and archive.downloads()


def test_cli_reports_the_card_as_json_without_a_last_run(config, client, archive, monkeypatch, capsys):
    undated(archive)
    real_run_sync = cli.run_sync
    monkeypatch.setattr(cli, "open_client", lambda _config: (client, {"user": {"id": "_900_1"}}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *args: None)
    monkeypatch.setattr(cli, "run_sync", lambda *args, **kwargs: real_run_sync(*args, now=NOW, **kwargs))
    args = cli.build_parser().parse_args(["sync", "--json", "--confirm-first"])
    assert cli.cmd_sync(args, config) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "confirm" and printed["confirm"]["courses"]
    assert not config.last_run_file.exists()


# -- the apps ---------------------------------------------------------------------

def test_apps_sync_with_confirm_first():
    assert "--confirm-first" in sync_arguments("sync", Settings(base_url=f"https://{SCHOOL}", dest=Path("/tmp/University")))


def test_the_app_keeps_the_card_and_waits_without_counting_a_sync():
    card = {"school": SCHOOL, "terms": ["T"], "reasons": ["undated"],
            "courses": [{"id": "_1_1", "code": "CSE303", "title": "Algorithms", "term": "T"}]}
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    outcome = parse_sync_output(json.dumps({"status": "confirm", "confirm": card, "message": "m"}), 0, "", now)
    assert outcome.status == "confirm" and outcome.confirm == card
    model = AppModel(dest=None, now=now)
    model.busy = "sync"
    assert model.finish_sync(outcome, now) == []
    assert model.busy is None and model.last is None and model.note == term_confirm.T_WAITING
    assert model.next_run_at and model.next_run_at > now
    assert RunOutcome(status="ok").confirm is None


def test_card_rows_name_the_term_only_when_there_are_several():
    one = {"terms": ["T"], "courses": [{"id": "_1", "code": "CSE303", "title": "Algorithms", "term": "T"}]}
    assert term_confirm.card_rows(one) == [("_1", "CSE303 Algorithms")]
    two = {"terms": ["A", "B"], "courses": [{"id": "_1", "code": "CSE303", "title": "Algorithms", "term": "A"},
                                            {"id": "_2", "code": "", "title": "Seminar", "term": "B"}]}
    assert term_confirm.card_rows(two) == [("_1", "CSE303 Algorithms · A"), ("_2", "Seminar · B")]
    assert "A, B" in term_confirm.card_message(two)


def test_confirm_keeps_courses_unticked_before_and_other_schools(config):
    courses.save_disabled(config, {"_old_1"})
    config.term_confirm_file.parent.mkdir(parents=True, exist_ok=True)
    config.term_confirm_file.write_text(json.dumps({"version": 1, "confirmed": ["bb.other.edu"]}), encoding="utf-8")
    card = {"school": SCHOOL, "courses": [{"id": "_1"}, {"id": "_2"}]}
    term_confirm.confirm(config, card, {"_1", "_9"})
    assert courses.load_disabled(config) == {"_old_1", "_2"}
    assert term_confirm.load_confirmed(config) == {"bb.other.edu", SCHOOL}


@pytest.mark.parametrize("content", ["not json", "[]", '{"confirmed": "x"}'])
def test_an_unreadable_confirm_file_counts_as_none(config, content):
    config.term_confirm_file.parent.mkdir(parents=True, exist_ok=True)
    config.term_confirm_file.write_text(content, encoding="utf-8")
    assert term_confirm.load_confirmed(config) == set()
