"""The announcements page's local index and actions, shared by both windows."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from blackboard_sync.config import Config
from blackboard_sync.htmltext import body_text, feed_html
from blackboard_sync.state import State

T_TAB = "Announcements"
T_HINT = "Every announcement synced from your current-term courses."
T_EMPTY = "No announcements yet. They show up here once they are synced."
T_NO_DATE = "No date given"
T_OPEN = "Open announcement"
PREVIEW_LIMIT = 240


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li", "tr"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li", "tr"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def metadata(ann: dict, course_id: str, course_name: str, source_path: str, output_key: str) -> dict:
    parser = feed_html(_PlainText, body_text(ann.get("body")))
    preview = " ".join("".join(parser.parts).split())
    if len(preview) > PREVIEW_LIMIT:
        preview = preview[:PREVIEW_LIMIT - 1].rstrip() + "…"
    duration = (ann.get("availability") or {}).get("duration") or {}
    return {
        "course_id": course_id, "course": course_name,
        "title": html.unescape(ann.get("title") or "Announcement"),
        "date": duration.get("start") or ann.get("created") or ann.get("modified") or "",
        "preview": preview, "source_path": source_path, "output_key": output_key,
    }


@dataclass(frozen=True)
class AnnouncementRow:
    key: str
    course: str
    title: str
    date: str
    preview: str
    path: str
    url: str

    @property
    def detail(self) -> str:
        return f"{self.course} · {self.date}"


def _date(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def rows(state: State, base_url: str, hidden: frozenset[str] | set[str] = frozenset()) -> tuple[AnnouncementRow, ...]:
    """Newest first; courses in ``hidden`` (unticked in Dersler) are left out."""
    current = set(state.current_courses) - set(hidden)
    result = []
    floor = datetime.min.replace(tzinfo=timezone.utc)
    for key, entry in state.announcements.items():
        if entry["course_id"] not in current:
            continue
        when = _date(entry["date"])
        output = state.output(entry["output_key"]) or {}
        row = AnnouncementRow(key, entry["course"], entry["title"],
                              when.astimezone().strftime("%d.%m.%Y %H:%M") if when else T_NO_DATE,
                              entry["preview"], output.get("path", ""),
                              base_url.rstrip("/") + entry["source_path"])
        result.append((when or floor, row))
    result.sort(key=lambda pair: (pair[0], pair[1].key), reverse=True)
    return tuple(row for _, row in result)


def load_rows(config: Config) -> tuple[AnnouncementRow, ...]:
    from blackboard_sync.courses import load_disabled  # it imports this module's State too

    return rows(State.load(config.state_file, backup=False), config.base_url, hidden=load_disabled(config))


def open_target(row: AnnouncementRow, root: Path) -> Path | str | None:
    """Prefer the saved note, following state output moves; fall back to Blackboard."""
    rel = PurePosixPath(row.path)
    if row.path and not rel.is_absolute() and ".." not in rel.parts:
        target = root / rel
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError:
            pass
        else:
            if target.is_file():
                return target
    url = urlsplit(row.url)
    return row.url if url.scheme in ("https", "http") and url.netloc else None
