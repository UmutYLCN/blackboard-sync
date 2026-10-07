"""File-name sanitizing and local path building."""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path, PurePosixPath

from blackboard_sync.system import is_windows

# APFS limits a single path component to 255 UTF-8 bytes.
MAX_NAME_BYTES = 255
# Windows: whole paths are limited to MAX_PATH (260, including the final NUL)
# unless long paths are enabled, so single names are kept shorter there.
WINDOWS_MAX_PATH = 259
WINDOWS_MAX_NAME_CHARS = 120
# Room left for a " (12)" that ``numbered_variant`` may add later.
NUMBER_SUFFIX_ROOM = 6
# A file name stem is never shortened below this to fit the path limit.
MIN_STEM_CHARS = 8
# Room kept below every folder for "\" plus a file name, so files keep readable
# names and the ".bbsync-*.partial" temp file (24 characters) of a download fits.
WINDOWS_FILE_ROOM = 40
# A folder name is never shortened below this, and keeps up to this much of its end.
MIN_FOLDER_CHARS = 16
FOLDER_TAIL_CHARS = 10
# Marks where a folder name was shortened: "Week 05 - Normalizati…Part 2".
ELLIPSIS = "\u2026"

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
# "CSE303", "MTH 101", "COE309A", "İNG101" ... optionally followed by a section like "-1".
# ``[^\W\d_]`` is any Unicode letter, so Turkish codes such as "BİL101" are recognized.
_COURSE_CODE = re.compile(r"\b([^\W\d_]{2,6})\s?(\d{3,4}[^\W\d_]?)(?:[-_.]\d{1,3})?\b")
# What versions before Turkish code support recognized; only used to find their folders.
_LEGACY_COURSE_CODE = re.compile(r"\b([A-Za-z]{2,6})\s?(\d{3,4}[A-Za-z]?)(?:[-_.]\d{1,3})?\b")
# Turkish dotted/dotless i, which plain ``upper()``/``casefold()`` get wrong.
_TURKISH_UPPER = str.maketrans({"i": "İ", "ı": "I"})
_TURKISH_FOLD = str.maketrans({"ı": "i"})
# Characters Windows does not allow in names (":" and "/" are handled for both).
_WINDOWS_REPLACEMENTS = str.maketrans({"\\": "-", "|": "-", '"': "'", "<": "(", ">": ")", "?": "", "*": ""})
# Device names Windows reserves in any case, with or without an extension.
_WINDOWS_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³])(\.|$)", re.IGNORECASE
)


def sanitize_name(name: str, fallback: str = "untitled", *, windows: bool | None = None) -> str:
    """Turn arbitrary Blackboard text into a single safe path component.

    Keeps the original name wherever possible: only characters that the file
    system cannot store or that would change the meaning of the path are
    replaced. On Windows (``windows`` defaults to the running system) its extra
    rules apply too: no ``\\ | " < > ? *``, no reserved device names such as
    ``CON`` or ``NUL.txt``, and shorter names. macOS names are unchanged by them.
    """
    windows = is_windows() if windows is None else windows
    name = html.unescape(name or "")
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL.sub(" ", name)
    # "/" separates paths; ":" is shown as "/" by Finder and rejected by some APIs.
    name = name.replace(": ", " - ").replace("/", "-").replace(":", "-")
    if windows:
        name = name.translate(_WINDOWS_REPLACEMENTS)
    name = _WHITESPACE.sub(" ", name).strip()
    # A leading dot would hide the file; trailing dots/spaces confuse other tools
    # (and Windows silently drops them).
    name = name.lstrip(".").rstrip(". ")
    if name in ("", ".", ".."):
        name = fallback
    if windows:
        name = _WINDOWS_RESERVED.sub(lambda m: m.group(1) + "_" + m.group(2), name, count=1)
    return truncate_name(name, max_chars=WINDOWS_MAX_NAME_CHARS if windows else None)


def split_ext(name: str) -> tuple[str, str]:
    """Split "report.final.pdf" into ("report.final", ".pdf")."""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or " " in ext or len(ext) > 10:
        return name, ""
    return stem, "." + ext


def truncate_name(name: str, limit: int = MAX_NAME_BYTES, max_chars: int | None = None) -> str:
    """Shorten a name to ``limit`` UTF-8 bytes (and ``max_chars``), keeping the extension."""
    if len(name.encode("utf-8")) <= limit and (max_chars is None or len(name) <= max_chars):
        return name
    stem, ext = split_ext(name)
    budget = limit - len(ext.encode("utf-8"))
    char_budget = None if max_chars is None else max_chars - len(ext)
    if budget <= 0 or (char_budget is not None and char_budget <= 0):
        stem, ext, budget, char_budget = name, "", limit, max_chars
    encoded = stem.encode("utf-8")[:budget]
    stem = encoded.decode("utf-8", errors="ignore")
    if char_budget is not None:
        stem = stem[:char_budget]
    return stem.rstrip(". ") + ext


def numbered_variant(rel_path: str, n: int, *, windows: bool | None = None) -> str:
    """"Week 1/notes.pdf", 2 -> "Week 1/notes (2).pdf"."""
    windows = is_windows() if windows is None else windows
    path = PurePosixPath(rel_path)
    stem, ext = split_ext(path.name)
    suffix = f" ({n})"
    name = truncate_name(
        stem,
        MAX_NAME_BYTES - len((suffix + ext).encode("utf-8")),
        WINDOWS_MAX_NAME_CHARS - len(suffix + ext) if windows else None,
    )
    return str(path.with_name(name + suffix + ext))


def note_name(title: str, *, windows: bool | None = None) -> str:
    """File name for a Markdown note about an item titled ``title``."""
    windows = is_windows() if windows is None else windows
    base = sanitize_name(title, windows=windows)
    base = truncate_name(
        base, MAX_NAME_BYTES - len(".md"), WINDOWS_MAX_NAME_CHARS - len(".md") if windows else None
    )
    return base + ".md"


def fit_windows_path(base: Path, rel_path: str, limit: int = WINDOWS_MAX_PATH - NUMBER_SUFFIX_ROOM) -> str:
    """Shorten the file name in ``rel_path`` so ``base / rel_path`` fits Windows' path limit.

    Only the last component is shortened (keeping its extension and at least
    ``MIN_STEM_CHARS`` characters); folders were already fitted when they were
    created (``fit_windows_folder``). A path that still does not fit is returned
    as short as it can be.
    """
    full = len(str(base).rstrip("/\\")) + 1 + len(rel_path)
    over = full - limit
    if over <= 0:
        return rel_path
    path = PurePosixPath(rel_path)
    stem, ext = split_ext(path.name)
    keep = max(len(stem) - over, min(MIN_STEM_CHARS, len(stem)))
    short = stem[:keep].rstrip(". ") or stem[:keep]
    return str(path.with_name(short + ext))


def fit_windows_folder(base: Path, parent_rel: str, name: str) -> str:
    """Shorten folder ``name`` so a deep tree under ``base / parent_rel`` fits Windows' path limit.

    Without long-path support Windows, and with it Explorer, Office and Acrobat,
    cannot open a path over ``WINDOWS_MAX_PATH`` characters. Each folder may use
    at most half of the room still left for folders (never less than
    ``MIN_FOLDER_CHARS``), so the folders below it get the other half and every
    file keeps ``WINDOWS_FILE_ROOM`` for its name. The result depends only on the
    parent path and the name, so every run and every file of a folder picks the
    same folder. A shortened name keeps its start and its end ("... Part 2").
    """
    used = len(str(base).rstrip("/\\")) + 1 + (len(parent_rel) + 1 if parent_rel else 0)
    cap = max(MIN_FOLDER_CHARS, (WINDOWS_MAX_PATH - WINDOWS_FILE_ROOM - used) // 2)
    if len(name) <= cap:
        return name
    tail = name[len(name) - min(FOLDER_TAIL_CHARS, cap // 3):].lstrip(" .")
    if " " in tail:
        tail = tail.split(" ", 1)[1].lstrip(" .")  # start at a word: "…Part 2", not "…rt 2"
    head = name[: cap - len(ELLIPSIS) - len(tail)].rstrip(" ")
    return head + ELLIPSIS + tail


def course_code_and_title(course_id: str, name: str) -> tuple[str, str]:
    """Derive ("CSE303", "Algorithm Analysis") from a course's id and name.

    Blackboard names look like "CSE303-1 Algorithm Analysis" or just
    "Algorithm Analysis" with the code in the course id ("CSE303-1"). The
    section suffix ("-1") is dropped so the folder reads like the course code.
    Codes may use any letters, so "İNG101-1" gives "İNG101".
    """
    # Decomposed letters ("I" + combining dot) would split a code in two.
    nfc = unicodedata.normalize
    return _code_and_title(nfc("NFC", course_id or ""), nfc("NFC", name or ""), _COURSE_CODE, _upper_code)


def course_folder_name(course_id: str, name: str, *, windows: bool | None = None) -> str:
    return _folder_name(course_code_and_title(course_id, name), windows)


def legacy_course_folder_name(course_id: str, name: str, *, windows: bool | None = None) -> str:
    """The folder older versions (ASCII-only course codes) gave this course.

    Only differs from ``course_folder_name`` for codes with non-ASCII letters,
    e.g. "İNG101-1 İNG101 İngilizce I" instead of "İNG101 İngilizce I".
    """
    return _folder_name(_code_and_title(course_id, name, _LEGACY_COURSE_CODE, str.upper), windows)


def fold_course_key(text: str) -> str:
    """Case- and accent-insensitive form of a course code or id for ``--course``.

    "BİL101", "bil101", "BIL101" and "bıl101" all fold to "bil101"; plain
    ``casefold()`` turns "İ" into "i" plus a combining dot, which never matches.
    """
    text = unicodedata.normalize("NFKD", text.translate(_TURKISH_FOLD))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _upper_code(code: str) -> str:
    # ASCII codes keep plain upper-casing (so existing folders keep their names);
    # a code with Turkish letters is upper-cased the Turkish way ("işl" -> "İŞL").
    return code.upper() if code.isascii() else code.translate(_TURKISH_UPPER).upper()


def _code_and_title(course_id: str, name: str, pattern: re.Pattern, upper) -> tuple[str, str]:
    name = _WHITESPACE.sub(" ", html.unescape(name or "")).strip()
    course_id = (course_id or "").strip()

    match = pattern.match(name)
    if match:
        code = upper(match.group(1) + match.group(2))
        title = name[match.end():].strip(" -_:|")
        return code, title or name

    match = pattern.search(course_id)
    if match:
        code = upper(match.group(1) + match.group(2))
        return code, name or course_id
    return course_id or "Course", name or course_id


def _folder_name(code_and_title: tuple[str, str], windows: bool | None) -> str:
    code, title = code_and_title
    if title and title.upper() != code:
        return sanitize_name(f"{code} {title}", windows=windows)
    return sanitize_name(code, windows=windows)


def join_rel(*parts: str) -> str:
    """Join already-sanitized components into a relative POSIX path."""
    return str(PurePosixPath(*[p for p in parts if p]))
