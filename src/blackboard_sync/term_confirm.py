"""Asking before the first download at a school when the current term is not clear.

The first sync at a school (no state for it yet) downloads at once when the term
choice is clear: dated terms, one running group, names that give a year and a
season. When it is not (``ambiguity``: a term without dates or with dates left from
an earlier year, terms that started on different days, a name that gives no year
and season), the desktop apps run the sync with ``--confirm-first``: it downloads
nothing and returns the terms and courses it found (status ``confirm``). The app
shows them as a card with every course ticked; Confirm saves the unticked ones as
unticked in Dersler (``courses.json``) and the school as confirmed here
(``term-confirm.json``), and syncs. Cancel saves nothing, so the next sync asks again.

A school with state (every school before this existed, such as the first school
with its files) is never asked, and the terminal's ``sync`` never asks.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable

from blackboard_sync import courses
from blackboard_sync.config import Config
from blackboard_sync.i18n import tr
from blackboard_sync.paths import course_code_and_title
from blackboard_sync.session import host_of, write_private_json
from blackboard_sync.state import State
from blackboard_sync.sync import Course, Term, academic_order, has_stale_dates

log = logging.getLogger(__name__)

# Why the current term is not clear (``ambiguity``).
UNDATED = "undated"  # a term without dates
STALE_DATES = "stale_dates"  # a term whose dates ended before its courses were made
SEVERAL_STARTS = "several_starts"  # terms that started on different days
UNKNOWN_NAME = "unknown_name"  # a term whose name gives no year and season

T_TITLE = tr("Check your courses before the first download")
T_MESSAGE = tr("Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
               "Untick any course you do not want, then confirm. Nothing is downloaded until you do.")
T_CONFIRM = tr("Confirm")
T_NOT_NOW = tr("Not now")
T_WAITING = tr("Waiting for you to confirm the courses to download.")


def school_of(base_url: str) -> str:
    return host_of(base_url).casefold()


def has_school_state(state: State, base_url: str) -> bool:
    """The state holds something of the school at ``base_url``; call it before ``State.use_school``.

    A state written before the school was recorded belongs to the school in use, and so does
    one that could not be read (``recovery``): both count as that school's.
    """
    if state.recovery:
        return True
    school = school_of(base_url)
    if state.school is None:
        return bool(state.outputs or state.items or state.courses)
    if state.school == school:
        return True
    return any(entry.get("school") == school for entry in state.outputs.values())


def ambiguity(terms: list[Term]) -> list[str]:
    """Why the term choice of the first sync is not clear (``UNDATED`` …); empty when it is.

    ``terms`` are the chosen terms (``choose_current_terms``); courses without a term
    always come along and say nothing about the term.
    """
    dated = [t for t in terms if t.id]
    if not any(t.courses for t in terms):
        return []
    reasons = []
    if any(not t.start for t in dated):
        reasons.append(UNDATED)
    if any(has_stale_dates(t) for t in dated):
        reasons.append(STALE_DATES)
    if len({t.start for t in dated if t.start and not has_stale_dates(t)}) > 1:
        reasons.append(SEVERAL_STARTS)
    if any(all(academic_order(name) is None for name in t.names) for t in dated):
        reasons.append(UNKNOWN_NAME)
    return reasons


def proposal(base_url: str, terms: list[Term], found: list[Course]) -> dict | None:
    """What the card shows: the school, the terms and their courses; None when nothing needs asking."""
    reasons = ambiguity(terms)
    if not reasons or not found:
        return None
    return {
        "school": school_of(base_url),
        "reasons": reasons,
        "terms": [t.name for t in terms if t.courses],
        "courses": [{"id": c.id, "code": c.code, "title": course_code_and_title(c.course_id, c.name)[1],
                     "term": c.term_name} for c in found],
    }


def load_confirmed(config: Config) -> set[str]:
    """The schools whose first courses were confirmed; an unreadable file counts as none."""
    try:
        data = json.loads(config.term_confirm_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as exc:
        log.warning("Could not read %s: %s", config.term_confirm_file.name, exc)
        return set()
    schools = data.get("confirmed") if isinstance(data, dict) else None
    return {s for s in schools if isinstance(s, str)} if isinstance(schools, list) else set()


def confirm(config: Config, card: dict, ticked: Iterable[str]) -> None:
    """Save the choice on the card: the courses not ticked are unticked in Dersler, the school asked."""
    shown = {c["id"] for c in card.get("courses") or []}
    unticked = shown - set(ticked)
    if unticked:
        courses.save_disabled(config, courses.load_disabled(config) | unticked)
    config.ensure_data_dir()
    write_private_json(config.term_confirm_file,
                       {"version": 1, "confirmed": sorted(load_confirmed(config) | {card["school"]})})
    log.info("Confirmed the first courses at %s; unticked %d", card["school"], len(unticked))


def course_label(course: dict, several_terms: bool) -> str:
    """One course on the card: "CSE303 Algorithm Analysis", with its term when the card shows more than one."""
    label = " ".join(part for part in (course.get("code"), course.get("title")) if part) or course.get("id", "")
    return f"{label} · {course['term']}" if several_terms and course.get("term") else label


def card_rows(card: dict) -> list[tuple[str, str]]:
    """(course id, label) for every course on the card, in the order found."""
    several = len(card.get("terms") or []) > 1
    return [(c["id"], course_label(c, several)) for c in card.get("courses") or []]


def card_message(card: dict) -> str:
    return T_MESSAGE.format(terms=", ".join(card.get("terms") or []) or "?")
