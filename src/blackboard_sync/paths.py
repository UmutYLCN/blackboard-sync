"""File-name sanitizing and local path building."""

from __future__ import annotations

import html
import mimetypes
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
# Characters cleaned on every platform so names stay valid across macOS, Windows and cloud drives.
_UNSAFE_CHARS = str.maketrans({"\\": "-", "|": "-", '"': "'", "<": "(", ">": ")", "?": "", "*": ""})
# Device names Windows reserves in any case, with or without an extension.
_WINDOWS_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³])(\.|$)", re.IGNORECASE
)
_REAL_EXT = re.compile(r"^\.[A-Za-z0-9+_-]{1,10}$")
_GENERIC_MIMES = frozenset({
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "application/unknown",
    "application/x-unknown",
})
# Common academic file types mapped deterministically (Python's mimetypes varies by OS).
_MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/gzip": ".gz",
    "application/x-gzip": ".gz",
    "application/x-tar": ".tar",
    "application/x-rar-compressed": ".rar",
    "application/vnd.rar": ".rar",
    "application/x-7z-compressed": ".7z",
    "application/json": ".json",
    "application/rtf": ".rtf",
    "application/epub+zip": ".epub",
    "application/xml": ".xml",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "text/html": ".html",
    "text/xml": ".xml",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


def sanitize_name(name: str, fallback: str = "untitled", *, windows: bool | None = None) -> str:
    """Turn arbitrary Blackboard text into a single safe path component.

    Uses the same character-cleaning and reserved-name rules on every platform,
    and caps every segment at ``MAX_NAME_BYTES`` UTF-8 bytes while keeping the
    file extension. On Windows (``windows`` defaults to the running system),
    single names are also kept within ``WINDOWS_MAX_NAME_CHARS`` so deep paths
    fit within MAX_PATH.
    """
    windows = is_windows() if windows is None else windows
    max_chars = WINDOWS_MAX_NAME_CHARS if windows else None
    name = html.unescape(name or "")
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL.sub(" ", name)
    # "/" separates paths; ":" is shown as "/" by Finder and rejected by some APIs.
    name = name.replace(": ", " - ").replace("/", "-").replace(":", "-")
    name = name.translate(_UNSAFE_CHARS)
    name = _WHITESPACE.sub(" ", name).strip()
    # A leading dot would hide the file; trailing dots/spaces confuse other tools
    # (and Windows silently drops them).
    name = name.lstrip(".").rstrip(". ")
    if name in ("", ".", ".."):
        name = fallback
    name = _WINDOWS_RESERVED.sub(lambda m: m.group(1) + "_" + m.group(2), name, count=1)
    name = truncate_name(name, MAX_NAME_BYTES, max_chars=max_chars)
    # Guard against truncation producing a reserved device name.
    name = _WINDOWS_RESERVED.sub(lambda m: m.group(1) + "_" + m.group(2), name, count=1)
    return truncate_name(name, MAX_NAME_BYTES, max_chars=max_chars)


def legacy_macos_name(name: str, fallback: str = "untitled") -> str:
    """The folder name older macOS versions used before cross-platform cleaning.

    Used only to keep writing into a folder that already exists on disk, so
    existing users never see mass renames or duplicate folders.
    """
    name = html.unescape(name or "")
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL.sub(" ", name)
    name = name.replace(": ", " - ").replace("/", "-").replace(":", "-")
    name = _WHITESPACE.sub(" ", name).strip()
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


def has_real_extension(name: str) -> bool:
    """True when ``name`` already carries a real file extension (e.g. ``.ipynb``, ``.m``, ``.pdf``)."""
    _, ext = split_ext(name)
    return bool(ext and _REAL_EXT.match(ext) and any(c.isalpha() for c in ext))


def guess_extension(mime_type: str | None) -> str:
    """Guess a file extension (with leading dot) from a specific MIME type; empty for generic/unknown."""
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if mime in _GENERIC_MIMES or mime.startswith(("video/", "audio/")):
        return ""
    ext = _MIME_EXTENSIONS.get(mime)
    if not ext:
        ext = mimetypes.guess_extension(mime, strict=False) or ""
    if ext and _REAL_EXT.match(ext) and any(c.isalpha() for c in ext):
        return ext.lower()
    return ""


def ensure_extension(
    name: str,
    *mime_types: str | None,
    fallback_name: str | None = None,
    windows: bool | None = None,
) -> str:
    """Keep ``name``'s own extension; add one from ``fallback_name`` or MIME only when it has none.

    The result never exceeds ``MAX_NAME_BYTES`` UTF-8 bytes (or ``WINDOWS_MAX_NAME_CHARS`` on Windows).
    """
    if not name or has_real_extension(name):
        return name
    ext = ""
    if fallback_name:
        clean_fallback = sanitize_name(fallback_name, windows=windows)
        if has_real_extension(clean_fallback):
            _, ext = split_ext(clean_fallback)
    if not ext:
        for mime in mime_types:
            ext = guess_extension(mime)
            if ext:
                break
    if not ext:
        return name
    windows = is_windows() if windows is None else windows
    max_chars = WINDOWS_MAX_NAME_CHARS if windows else None
    return truncate_name(name + ext, MAX_NAME_BYTES, max_chars=max_chars)


def append_suffix(name: str, suffix: str, *, windows: bool | None = None) -> str:
    """Append a disambiguating suffix (e.g. ``" (CSE303)"``) while staying within the byte cap."""
    windows = is_windows() if windows is None else windows
    clean_suffix = sanitize_name(suffix, fallback="", windows=windows) if suffix.strip() else ""
    if not clean_suffix:
        return sanitize_name(name, windows=windows)
    suffix_part = f" ({clean_suffix})"
    max_chars = WINDOWS_MAX_NAME_CHARS if windows else None
    base = sanitize_name(name, windows=windows)
    byte_budget = MAX_NAME_BYTES - len(suffix_part.encode("utf-8"))
    char_budget = None if max_chars is None else max_chars - len(suffix_part)
    if byte_budget <= 0 or (char_budget is not None and char_budget <= 0):
        return sanitize_name(f"{base}{suffix_part}", windows=windows)
    short = truncate_name(base, byte_budget, char_budget)
    return sanitize_name(f"{short}{suffix_part}", windows=windows)


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
    stem = stem.rstrip(". ")
    if not stem:
        stem = "untitled".encode("utf-8")[: max(budget, 1)].decode("utf-8", errors="ignore")
        if char_budget is not None:
            stem = stem[: max(char_budget, 1)]
    return stem + ext


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
    """File name for the PDF note about an item titled ``title``."""
    windows = is_windows() if windows is None else windows
    base = sanitize_name(title, windows=windows)
    base = truncate_name(
        base, MAX_NAME_BYTES - len(".pdf"), WINDOWS_MAX_NAME_CHARS - len(".pdf") if windows else None
    )
    return base + ".pdf"


def markdown_twin(rel_path: str) -> str:
    """Where the hidden Markdown copy of the note at ``rel_path`` lives.

    "Week 1/Intro.pdf" -> "Week 1/.Intro.md": the leading dot hides it in Finder,
    and the sync sets the hidden attribute for Windows Explorer, so the folder
    shows only the PDF. One name on both systems, exactly as long as the PDF's,
    so it fits wherever the PDF fits. Also hides an older version's "Intro.md".
    """
    path = PurePosixPath(rel_path)
    stem, _ = split_ext(path.name)
    stem = truncate_name(stem, MAX_NAME_BYTES - len("..md"))
    return str(path.with_name(f".{stem}.md"))


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
    return str(path.with_name(truncate_name(short + ext, MAX_NAME_BYTES)))


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
    if len(name) <= cap and len(name.encode("utf-8")) <= MAX_NAME_BYTES:
        return name
    if len(name) <= cap:
        return truncate_name(name, MAX_NAME_BYTES)
    tail = name[len(name) - min(FOLDER_TAIL_CHARS, cap // 3):].lstrip(" .")
    if " " in tail:
        tail = tail.split(" ", 1)[1].lstrip(" .")  # start at a word: "…Part 2", not "…rt 2"
    head = name[: cap - len(ELLIPSIS) - len(tail)].rstrip(" ")
    return truncate_name(head + ELLIPSIS + tail, MAX_NAME_BYTES)


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
