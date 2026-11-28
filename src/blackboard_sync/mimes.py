"""File types by name and extensions by type, without the system's ``mime.types`` files.

The standard library's ``mimetypes`` reads ``/etc/apache2/mime.types`` and the like the first
time anything asks it. App Sandbox (the Mac App Store build) denies those reads, and the
``PermissionError`` escaped into every Gemini Notebook upload. So the app answers the types it
needs from its own table, and ``sandbox_safe`` makes the library's tables built-in only, for
this app and any library in the process, before anything initialises them from the system.
"""

from __future__ import annotations

import mimetypes
import threading

# What Gemini Notebook takes (``notebooklm.planner``), and what Blackboard courses carry most.
TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xls": "application/vnd.ms-excel",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".epub": "application/epub+zip",
    ".html": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".rtf": "application/rtf",
    ".zip": "application/zip",
    ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed",
}  # beyond this, the library's built-in table only (outside the sandbox it also had the system's)
OCTET_STREAM = "application/octet-stream"

_lock = threading.Lock()


def sandbox_safe() -> None:
    """Give ``mimetypes`` its built-in tables only, so nothing in the process reads system files.

    Harmless when ``mimetypes`` already started (outside the sandbox it could read them).
    """
    with _lock:
        if not mimetypes.inited:
            mimetypes.knownfiles = []  # init() would read each of these that exists
            mimetypes.init()


def guess_type(name: str) -> str:
    """The type to upload a file under, by its name; ``application/octet-stream`` when unknown."""
    dot = name.rfind(".")
    ext = name[dot:].lower() if dot > 0 else ""
    if ext in TYPES:
        return TYPES[ext]
    sandbox_safe()
    return mimetypes.guess_type(name, strict=False)[0] or OCTET_STREAM


def guess_extension(mime: str) -> str:
    """An extension (with its dot) for a type; empty when there is none."""
    for ext, known in TYPES.items():
        if known == mime:
            return ext
    sandbox_safe()
    return mimetypes.guess_extension(mime, strict=False) or ""
