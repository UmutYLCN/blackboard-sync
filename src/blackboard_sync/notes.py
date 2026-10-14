"""Markdown notes for things that are not files: links, pages, announcements."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from blackboard_sync.htmltext import body_text, html_to_markdown

# contentHandler ids -> how the note labels the item.
HANDLER_LABELS = {
    "resource/x-bb-externallink": "Link",
    "resource/x-bb-document": "Document",
    "resource/x-bb-blankpage": "Page",
    "resource/x-bb-assignment": "Assignment",
    "resource/x-bb-asmt-test-link": "Assignment / test",
    "resource/x-bb-forumlink": "Discussion",
    "resource/x-bb-courselink": "Course link",
    "resource/x-bb-toollink": "Tool link",
    "resource/x-bb-blti-link": "External tool",
    "resource/x-bb-lti-link": "External tool",
    "resource/x-bb-syllabus": "Syllabus",
    "resource/x-bb-file": "File",
}


def handler_id(item: dict) -> str:
    return ((item.get("contentHandler") or {}).get("id")) or ""


def handler_label(item: dict) -> str:
    hid = handler_id(item)
    if hid in HANDLER_LABELS:
        return HANDLER_LABELS[hid]
    if "lti" in hid or "blti" in hid:
        return "External tool"
    return "Item"


def _date(value: str | None) -> str:
    return (value or "")[:10]


def _due_text(value: object) -> str:
    """Due date as "2026-10-16 16:00 UTC"; text we cannot read is kept as received."""
    if not isinstance(value, str) or not value.strip():
        return ""
    text = value.strip()
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if when.tzinfo is None:
        return text
    return when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _points_text(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return ""
    if value in (float("inf"), float("-inf")):
        return ""
    return f"{value:g}"


def _deadline_line(item: dict) -> str:
    """"Due: ... · Points: ..." from the item's own grading fields, if it has them."""
    grading = item.get("grading")
    score = item.get("score")
    due = _due_text(grading.get("due") if isinstance(grading, dict) else None)
    points = _points_text(score.get("possible") if isinstance(score, dict) else None)
    parts = [f"Due: {due}" if due else "", f"Points: {points}" if points else ""]
    return " · ".join(p for p in parts if p)


def _media_lines(media: list[tuple[str, str]] | None) -> list[str]:
    """Videos and audio are not downloaded: the note links to them in Blackboard instead."""
    if not media:
        return []
    lines = ["Video ve ses dosyaları (Blackboard'da aç):"]
    lines += [f"- {' '.join(name.split()) or 'Recording'}: <{url}>" for name, url in media]
    return lines + [""]


def _footer(source_url: str, modified: str | None) -> list[str]:
    lines = ["---", f"Open in Blackboard: <{source_url}>"]
    if modified:
        lines.append(f"Last changed on Blackboard: {modified}")
    return lines


def render_item_note(
    item: dict,
    course_label: str,
    source_url: str,
    saved_files: list[str] | None = None,
    media: list[tuple[str, str]] | None = None,
) -> str:
    """Note for a content item: a link, a text page, or anything not a plain file."""
    title = html.unescape(item.get("title") or "Untitled")
    handler = item.get("contentHandler") or {}
    lines = [f"# {title}", "", f"_{handler_label(item)} · {course_label}_", ""]

    deadline = _deadline_line(item)
    if deadline:
        lines += [deadline, ""]

    url = handler.get("url")
    if url:
        lines += [f"Link: <{url}>", ""]

    # Ultra assignments and tests keep the text students see under "View
    # instructions" in the handler, not in body. Some items repeat it in body.
    sources = (item.get("description"), item.get("body"), handler.get("instructions"))
    blocks: list[str] = []
    for source in sources:
        block = html_to_markdown(body_text(source))
        if block and block not in blocks:
            blocks.append(block)
    for block in blocks:
        lines += [block, ""]

    if saved_files:
        lines.append("Files saved next to this note:")
        lines += [f"- {name}" for name in saved_files]
        lines.append("")
    lines += _media_lines(media)

    lines += _footer(source_url, item.get("modified"))
    return "\n".join(lines).rstrip() + "\n"


def announcement_date(ann: dict) -> str:
    duration = (ann.get("availability") or {}).get("duration") or {}
    return _date(duration.get("start") or ann.get("created") or ann.get("modified"))


def render_announcement_note(
    ann: dict,
    course_label: str,
    source_url: str,
    saved_files: list[str] | None = None,
    media: list[tuple[str, str]] | None = None,
) -> str:
    title = html.unescape(ann.get("title") or "Announcement")
    date = announcement_date(ann)
    meta = " · ".join(p for p in ("Announcement", course_label, date) if p)
    lines = [f"# {title}", "", f"_{meta}_", ""]
    body = html_to_markdown(body_text(ann.get("body")))
    if body:
        lines += [body, ""]
    if saved_files:
        lines.append("Files saved next to this note:")
        lines += [f"- {name}" for name in saved_files]
        lines.append("")
    lines += _media_lines(media)
    lines += _footer(source_url, ann.get("modified"))
    return "\n".join(lines).rstrip() + "\n"


def needs_note(item: dict, has_media: bool = False) -> bool:
    """Whether an item deserves a Markdown note in addition to its files.

    ``has_media``: a video or audio file was not downloaded, so the note is the only
    place that still points to it.
    """
    hid = handler_id(item)
    if hid == "resource/x-bb-file":
        return has_media
    if hid == "resource/x-bb-document":
        # A document that is only a wrapper around attachments needs no note.
        return has_media or bool(html_to_markdown(body_text(item.get("body"))).strip())
    return True
