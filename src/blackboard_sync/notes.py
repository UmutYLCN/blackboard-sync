"""Markdown notes for things that are not files: links, pages, announcements."""

from __future__ import annotations

import html

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
) -> str:
    """Note for a content item: a link, a text page, or anything not a plain file."""
    title = html.unescape(item.get("title") or "Untitled")
    handler = item.get("contentHandler") or {}
    lines = [f"# {title}", "", f"_{handler_label(item)} · {course_label}_", ""]

    url = handler.get("url")
    if url:
        lines += [f"Link: <{url}>", ""]

    body = html_to_markdown(body_text(item.get("body")))
    description = html_to_markdown(body_text(item.get("description")))
    for block in (description, body):
        if block:
            lines += [block, ""]

    if saved_files:
        lines.append("Files saved next to this note:")
        lines += [f"- {name}" for name in saved_files]
        lines.append("")

    lines += _footer(source_url, item.get("modified"))
    return "\n".join(lines).rstrip() + "\n"


def announcement_date(ann: dict) -> str:
    duration = (ann.get("availability") or {}).get("duration") or {}
    return _date(duration.get("start") or ann.get("created") or ann.get("modified"))


def render_announcement_note(ann: dict, course_label: str, source_url: str) -> str:
    title = html.unescape(ann.get("title") or "Announcement")
    date = announcement_date(ann)
    meta = " · ".join(p for p in ("Announcement", course_label, date) if p)
    lines = [f"# {title}", "", f"_{meta}_", ""]
    body = html_to_markdown(body_text(ann.get("body")))
    if body:
        lines += [body, ""]
    lines += _footer(source_url, ann.get("modified"))
    return "\n".join(lines).rstrip() + "\n"


def needs_note(item: dict) -> bool:
    """Whether an item deserves a Markdown note in addition to its files."""
    hid = handler_id(item)
    if hid == "resource/x-bb-file":
        return False
    if hid == "resource/x-bb-document":
        # A document that is only a wrapper around attachments needs no note.
        return bool(html_to_markdown(body_text(item.get("body"))).strip())
    return True
