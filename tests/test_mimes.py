"""File types without the system's mime.types files, which App Sandbox denies.

The captain's Mac App Store retest failed every Gemini Notebook upload with
``[Errno 1] Operation not permitted: '/etc/apache2/mime.types'``: ``mimetypes`` read the
system's files the first time anything asked it for a type.
"""

from __future__ import annotations

import mimetypes

import pytest

from blackboard_sync import mimes, paths


@pytest.fixture
def sandboxed(monkeypatch, tmp_path):
    """A fresh ``mimetypes`` whose system file exists but may not be read, as in App Sandbox."""
    system_file = tmp_path / "mime.types"
    system_file.write_text("application/x-system-only    sysonly\n", encoding="utf-8")
    reads = []

    def denied(self, filename, strict=True):
        reads.append(filename)
        raise PermissionError(1, "Operation not permitted", filename)

    for name in ("inited", "_db", "knownfiles", "types_map", "common_types", "suffix_map", "encodings_map"):
        monkeypatch.setattr(mimetypes, name, getattr(mimetypes, name))  # restored after the test
    monkeypatch.setattr(mimetypes, "inited", False)
    monkeypatch.setattr(mimetypes, "_db", None)
    monkeypatch.setattr(mimetypes, "knownfiles", [str(system_file)])
    monkeypatch.setattr(mimetypes.MimeTypes, "read", denied)
    return reads


def test_the_plain_library_trips_over_the_sandbox(sandboxed):
    with pytest.raises(PermissionError):
        mimetypes.guess_type("Week 1.pdf")
    assert sandboxed


def test_upload_types_never_read_system_files(sandboxed):
    assert mimes.guess_type("Week 1.pdf") == "application/pdf"
    assert mimes.guess_type("Slides.PPTX") == mimes.TYPES[".pptx"]
    assert mimes.guess_type("REPORT 6 .docx") == mimes.TYPES[".docx"]
    assert mimes.guess_type("notes.odt") == "application/vnd.oasis.opendocument.text"  # built-in table
    assert mimes.guess_type("no-extension") == mimes.OCTET_STREAM
    assert mimes.guess_type(".hidden") == mimes.OCTET_STREAM
    assert sandboxed == []


def test_once_made_safe_no_library_in_the_process_reads_them(sandboxed):
    mimes.sandbox_safe()
    assert mimetypes.guess_type("a.html")[0] == "text/html"  # a library asking mimetypes directly
    assert mimetypes.guess_extension("application/x-system-only") is None
    assert sandboxed == []


def test_download_extensions_never_read_system_files(sandboxed):
    assert paths.guess_extension("application/vnd.oasis.opendocument.presentation") == ".odp"
    assert paths.guess_extension("application/pdf") == ".pdf"
    assert mimes.guess_extension(mimes.TYPES[".xlsx"]) == ".xlsx"
    assert mimes.guess_extension("application/x-unheard-of") == ""
    assert sandboxed == []


def test_the_safari_upload_asks_for_its_type_the_safe_way():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "src" / "blackboard_sync" / "notebooklm" / "safari.py")
    text = source.read_text(encoding="utf-8")
    assert "mimes.guess_type(path.name)" in text and "import mimetypes" not in text
