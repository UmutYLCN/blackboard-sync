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

T_TAB = "Takvim"
T_HINT = "Son teslim tarihleri senkron sırasında güncellenir. Saatler bu bilgisayarın yerel saatine göredir."
T_UPCOMING = "Yaklaşan tarihler"
T_PAST = "Tarihi geçenler"
T_PAST_HINT = "Teslim durumu kontrol edilmez; tamamladığınız çalışmalar da burada görünebilir."
T_EMPTY = "Kayıtlı son teslim tarihi yok."
T_NOT_SYNCED = "Tarihleri görmek için senkronize edin."
T_INCOMPLETE = "Bazı derslerin tarihleri güncellenemedi. Varsa önceki kayıtlar gösteriliyor."
MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


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
    return {"id": column["id"], "title": column.get("displayName") or column.get("name") or "İsimsiz çalışma",
            "due": due.isoformat(), "content_id": content_id, "url": url}


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
    prefix = "Bugün" if day == today else "Yarın" if day == today + timedelta(days=1) else WEEKDAYS[day.weekday()]
    return f"{prefix} · {day.day} {MONTHS[day.month - 1]} {day.year}"


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


def calendar_page(state: State, root: Path, now: datetime, zone: tzinfo | None = None) -> DeadlinePage:
    """Upcoming first, ascending by instant; elapsed dates in a separate section.

    Convert each instant individually using the system zone (including DST).
    ``zone`` makes timezone boundaries deterministic in tests.
    """
    local_now = now.astimezone(zone)
    grouped: dict[tuple[bool, date], list[DeadlineRow]] = {}
    for course_id, course in state.deadline_courses.items():
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
    if any(c.get("unavailable") for c in state.deadline_courses.values()):
        message = T_INCOMPLETE
    return DeadlinePage(days, message)


def load_calendar(config: Config, dest: Path) -> DeadlinePage:
    return calendar_page(State.load(config.state_file, backup=False), sync_root(dest), datetime.now(timezone.utc))
