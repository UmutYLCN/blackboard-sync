"""File-name sanitizing and local path building."""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import PurePosixPath

# APFS limits a single path component to 255 UTF-8 bytes.
MAX_NAME_BYTES = 255

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
# "CSE303", "MTH 101", "COE309A" ... optionally followed by a section like "-1".
_COURSE_CODE = re.compile(r"\b([A-Za-z]{2,6})\s?(\d{3,4}[A-Za-z]?)(?:[-_.]\d{1,3})?\b")


def sanitize_name(name: str, fallback: str = "untitled") -> str:
    """Turn arbitrary Blackboard text into a single safe macOS path component.

    Keeps the original name wherever possible: only characters that macOS cannot
    store or that would change the meaning of the path are replaced.
    """
    name = html.unescape(name or "")
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL.sub(" ", name)
    # "/" separates paths; ":" is shown as "/" by Finder and rejected by some APIs.
    name = name.replace(": ", " - ").replace("/", "-").replace(":", "-")
    name = _WHITESPACE.sub(" ", name).strip()
    # A leading dot would hide the file; trailing dots/spaces confuse other tools.
    name = name.lstrip(".").rstrip(". ")
    if name in ("", ".", ".."):
        name = fallback
    return truncate_name(name)


def split_ext(name: str) -> tuple[str, str]:
    """Split "report.final.pdf" into ("report.final", ".pdf")."""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or " " in ext or len(ext) > 10:
        return name, ""
    return stem, "." + ext


def truncate_name(name: str, limit: int = MAX_NAME_BYTES) -> str:
    """Shorten a name to ``limit`` UTF-8 bytes, keeping the extension."""
    if len(name.encode("utf-8")) <= limit:
        return name
    stem, ext = split_ext(name)
    budget = limit - len(ext.encode("utf-8"))
    if budget <= 0:
        stem, ext, budget = name, "", limit
    encoded = stem.encode("utf-8")[:budget]
    stem = encoded.decode("utf-8", errors="ignore").rstrip(". ")
    return stem + ext


def numbered_variant(rel_path: str, n: int) -> str:
    """"Week 1/notes.pdf", 2 -> "Week 1/notes (2).pdf"."""
    path = PurePosixPath(rel_path)
    stem, ext = split_ext(path.name)
    suffix = f" ({n})"
    name = truncate_name(stem, MAX_NAME_BYTES - len((suffix + ext).encode("utf-8")))
    return str(path.with_name(name + suffix + ext))


def note_name(title: str) -> str:
    """File name for a Markdown note about an item titled ``title``."""
    base = sanitize_name(title)
    base = truncate_name(base, MAX_NAME_BYTES - len(".md"))
    return base + ".md"


def course_code_and_title(course_id: str, name: str) -> tuple[str, str]:
    """Derive ("CSE303", "Algorithm Analysis") from a course's id and name.

    Blackboard names look like "CSE303-1 Algorithm Analysis" or just
    "Algorithm Analysis" with the code in the course id ("CSE303-1"). The
    section suffix ("-1") is dropped so the folder reads like the course code.
    """
    name = _WHITESPACE.sub(" ", html.unescape(name or "")).strip()
    course_id = (course_id or "").strip()

    match = _COURSE_CODE.match(name)
    if match:
        code = (match.group(1) + match.group(2)).upper()
        title = name[match.end():].strip(" -_:|")
        return code, title or name

    match = _COURSE_CODE.search(course_id)
    if match:
        code = (match.group(1) + match.group(2)).upper()
        return code, name or course_id
    return course_id or "Course", name or course_id


def course_folder_name(course_id: str, name: str) -> str:
    code, title = course_code_and_title(course_id, name)
    if title and title.upper() != code:
        return sanitize_name(f"{code} {title}")
    return sanitize_name(code)


def join_rel(*parts: str) -> str:
    """Join already-sanitized components into a relative POSIX path."""
    return str(PurePosixPath(*[p for p in parts if p]))
