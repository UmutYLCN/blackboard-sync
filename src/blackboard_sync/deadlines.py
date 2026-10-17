"""Grade-column due dates cached during sync; calendar presentation needs no HTTP.

Only the documented ``grading.due`` timestamp is used. Availability windows,
text descriptions and calendar event starts are not deadlines.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from blackboard_sync.config import Config
from blackboard_sync.state import State
from blackboard_sync.system import sync_root

T_TAB = "Calendar"
T_HINT = "Due dates are updated during a sync. Times are in this computer's local time."
T_UPCOMING = "Upcoming"
T_PAST = "Past due"
T_PAST_HINT = "Submissions are not checked; work you already handed in may show here too."
T_EMPTY = "No due dates saved."
T_NOT_SYNCED = "Sync to see due dates."
T_INCOMPLETE = "Some courses' due dates could not be updated. Earlier ones are shown where there are any."
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def parse_due(value: object) -> datetime | None:
    """Require an explicit timezone; never guess an offset for ambiguous data."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def column_deadline(column: dict, course_id: str, base_url: str,
                    content_ids: dict[str, str] | None = None) -> dict | None:
    due = parse_due((column.get("grading") or {}).get("due"))
    if due is None or not column.get("id") or (column.get("availability") or {}).get("available") == "No":
        return None
    content_id = column.get("contentId") or (content_ids or {}).get(column["id"])
    url = f"{base_url.rstrip('/')}/ultra/courses/{course_id}/grades"
    if content_id:
        url = f"{base_url.rstrip('/')}/ultra/redirect?" + urlencode({
            "redirectType": "nautilus", "courseId": course_id, "contentId": content_id,
        })
    return {"id": column["id"], "title": column.get("displayName") or column.get("name") or "Untitled work",
            "due": due.isoformat(), "content_id": content_id, "url": url}


# How long before a due date the student is reminded, least urgent first.
REMINDER_STAGES = (("24h", timedelta(hours=24)), ("1h", timedelta(hours=1)))
# A reminder record is dropped this long after its due date has passed.
REMINDER_KEEP = timedelta(days=1)


@dataclass(frozen=True)
class Reminder:
    key: str  # "<course id>:<column id>", what ``sent`` is keyed by
    stage: str  # "24h" | "1h"
    due: datetime
    title: str
    course: str
    target: str  # as ``DeadlineRow.target``


def due_reminders(state: State, root: Path, now: datetime, sent: dict,
                  hidden: frozenset[str] | set[str] = frozenset()) -> tuple[list[Reminder], dict]:
    """The reminders to show now, and ``sent`` updated with them.

    Each due date is announced once per stage (24 hours and 1 hour before). A date reached
    late, say after the computer slept, gets only the most urgent stage that applies, never
    two notifications at once. A changed due date starts over. ``sent`` maps a key to
    ``{"due": ISO time, "stages": [...]}``; records of finished or removed items are dropped.
    """
    reminders: list[Reminder] = []
    updated: dict[str, dict] = {}
    for course_id, course in state.deadline_courses.items():
        if course_id in hidden:
            continue
        for item in course.get("items", []):
            due = parse_due(item.get("due"))
            if due is None or not item.get("id"):
                continue
            key = f"{course_id}:{item['id']}"
            record = sent.get(key) if isinstance(sent.get(key), dict) else {}
            done = set(record.get("stages", [])) if record.get("due") == due.isoformat() else set()
            if now - due > REMINDER_KEEP:
                continue  # long past: no record needed any more
            left = due - now
            reached = {name for name, span in REMINDER_STAGES if left <= span} if left > timedelta(0) else set()
            fresh = reached - done
            if fresh:
                stage = next(name for name, _ in reversed(REMINDER_STAGES) if name in fresh)
                reminders.append(Reminder(key, stage, due, item.get("title") or "Untitled work",
                                          course.get("name") or "", note_target(state, root, course_id, item)))
            if done | reached or record:
                updated[key] = {"due": due.isoformat(), "stages": sorted(done | reached)}
    reminders.sort(key=lambda r: (r.due, r.course, r.title))
    return reminders, updated


def reminder_text(reminder: Reminder, now: datetime, zone: tzinfo | None = None) -> tuple[str, str]:
    """(title, message) of a reminder's notification."""
    local = reminder.due.astimezone(zone)
    when = local.strftime("%H:%M") if local.date() == now.astimezone(zone).date() else (
        f"{MONTHS[local.month - 1]} {local.day} {local.strftime('%H:%M')}")
    if reminder.stage == "1h":
        title = "Due in 1 hour"
    else:
        title = "Deadline coming up"
    return title, f"{reminder.course}: {reminder.title}\nDue: {when}"


@dataclass(frozen=True)
class DeadlineRow:
    title: str
    course: str
    due: datetime
    target: str  # existing note path relative to University, otherwise a Blackboard URL

    @property
    def time(self) -> str:
        return self.due.strftime("%H:%M")


@dataclass(frozen=True)
class DeadlineDay:
    day: date
    title: str
    past: bool
    rows: tuple[DeadlineRow, ...]


@dataclass(frozen=True)
class DeadlinePage:
    days: tuple[DeadlineDay, ...] = ()
    message: str = T_NOT_SYNCED


def day_title(day: date, today: date) -> str:
    prefix = "Today" if day == today else "Tomorrow" if day == today + timedelta(days=1) else WEEKDAYS[day.weekday()]
    return f"{prefix} · {MONTHS[day.month - 1]} {day.day}, {day.year}"


def note_target(state: State, root: Path, course_id: str, item: dict) -> str:
    output = state.output(f"note:{course_id}:{item.get('content_id')}")
    if output:
        rel = PurePosixPath(output["path"])
        if not rel.is_absolute() and ".." not in rel.parts:
            target = root / rel
            try:
                target.resolve().relative_to(root.resolve())
                if target.is_file():
                    return str(rel)
            except (ValueError, OSError):
                pass
    return item["url"]


def calendar_page(state: State, root: Path, now: datetime, zone: tzinfo | None = None,
                  hidden: frozenset[str] | set[str] = frozenset()) -> DeadlinePage:
    """Upcoming first, ascending by instant; elapsed dates in a separate section.

    Courses in ``hidden`` (unticked in Dersler) are left out.

    Convert each instant individually using the system zone (including DST).
    ``zone`` makes timezone boundaries deterministic in tests.
    """
    local_now = now.astimezone(zone)
    grouped: dict[tuple[bool, date], list[DeadlineRow]] = {}
    shown = {course_id: course for course_id, course in state.deadline_courses.items() if course_id not in hidden}
    for course_id, course in shown.items():
        for item in course.get("items", []):
            due = parse_due(item.get("due"))
            if due is None:
                continue
            local = due.astimezone(zone)
            grouped.setdefault((due < now, local.date()), []).append(
                DeadlineRow(item["title"], course["name"], local, note_target(state, root, course_id, item)))
    days = tuple(DeadlineDay(day, day_title(day, local_now.date()), past,
                            tuple(sorted(rows, key=lambda r: (r.due.astimezone(timezone.utc), r.course, r.title))))
                 for (past, day), rows in sorted(grouped.items(), key=lambda entry: (
                     entry[0][0], -entry[0][1].toordinal() if entry[0][0] else entry[0][1].toordinal())))
    message = T_NOT_SYNCED if not state.deadline_courses else ""
    if any(c.get("unavailable") for c in shown.values()):
        message = T_INCOMPLETE
    return DeadlinePage(days, message)


def load_calendar(config: Config, dest: Path) -> DeadlinePage:
    from blackboard_sync.courses import load_disabled  # it imports this module's State too

    return calendar_page(State.load(config.state_file, backup=False), sync_root(dest), datetime.now(timezone.utc),
                         hidden=load_disabled(config))



def upcoming_rows(page: DeadlinePage, limit: int) -> tuple[DeadlineRow, ...]:
    """The next ``limit`` due dates that have not passed, soonest first (Home's small calendar)."""
    rows = [row for day in page.days if not day.past for row in day.rows]
    rows.sort(key=lambda row: (row.due.astimezone(timezone.utc), row.course, row.title))
    return tuple(rows[:limit])


def when_text(row: DeadlineRow, today: date) -> str:
    """"today 14:30", "tomorrow 09:00" or "October 15 09:00": when a due date is, for a small row."""
    day = row.due.date()
    if day == today:
        return f"today {row.time}"
    if day == today + timedelta(days=1):
        return f"tomorrow {row.time}"
    return f"{MONTHS[day.month - 1]} {day.day} {row.time}"
