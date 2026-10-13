"""Notes are saved as PDFs with clickable links, beside a hidden Markdown copy."""

import os
import re
import stat
import subprocess
import sys
import zlib

import pytest

from blackboard_sync import relocate
from blackboard_sync.deleted import missing_outputs
from blackboard_sync.notepdf import MONO, inline, render_pdf
from blackboard_sync.notes import render_announcement_note, render_item_note
from blackboard_sync.state import State
from blackboard_sync.system import sync_root
from blackboard_sync.uninstall import trash_course_files

from .conftest import note_markdown, note_text, visible_files
from .test_sync import NOTE, NOTE_MD, _edit_note_on_blackboard, sync

PDF_KEY = "note:_13004_1:_c211_1"
MD_KEY = "note-md:_13004_1:_c211_1"
ITEM_KEY = "content:_13004_1:_c211_1"
LEGACY = NOTE.replace(".pdf", ".md")  # where versions before PDF notes saved it
URL = "https://blackboard.example.edu/ultra/courses/_1_1/outline"
# Typical content: Turkish text, nested lists, code, links and a list of saved files.
ASSIGNMENT = {
    "title": "Ödev 3: İkili Arama Ağaçları",
    "contentHandler": {"id": "resource/x-bb-assignment", "instructions": {"rawText": (
        "<h2>Yönergeler</h2><p>Bu ödevde <strong>ikili arama ağacı</strong> yapısını <em>Python</em> ile "
        "yazacaksınız: <code>ekle(değer)</code>, <code>sil(değer)</code> ve <code>ara(değer)</code>.</p>"
        "<ol><li>Düğüm sınıfı<ul><li>sol ve sağ çocuk</li><li>değer alanı</li></ul></li>"
        "<li>Ağaç sınıfı<ol><li>ekleme</li><li>silme (üç durum)</li></ol></li><li>Testler</li></ol>"
        "<pre>class Dugum:\n    def __init__(self, deger):\n        self.deger = deger\n</pre>"
        "<p>Kaynak: <a href=\"https://en.wikipedia.org/wiki/Binary_search_tree\">BST</a> ve "
        "https://docs.python.org/3/tutorial/classes.html sayfası.</p>"
        "<blockquote>Geç teslim: günlük %10 kesinti. ÇĞİÖŞÜ çğıöşü</blockquote>"
    )}},
    "grading": {"due": "2026-10-16T13:00:00.000Z"}, "score": {"possible": 100},
    "modified": "2026-10-01T10:00:00.000Z",
}
SIZE_CEILING = 100 * 1024


def _note() -> str:
    return render_item_note(ASSIGNMENT, "CSE303 Algorithm Analysis", URL, ["odev3_sablon.py", "veri_seti.csv"])


def _streams(pdf: bytes) -> str:
    """Every stream of ``pdf``, inflated where compressed, as text."""
    out = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            out.append(zlib.decompressobj().decompress(raw).decode("latin-1"))
        except zlib.error:
            out.append(raw.decode("latin-1"))
    return "\n".join(out)


# -- rendering -------------------------------------------------------------------

def test_pdf_has_clickable_links_for_every_kind_of_link():
    pdf = render_pdf(_note())
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    uris = re.findall(rb"/URI \((.*?)\)", pdf)
    assert uris == [
        b"https://en.wikipedia.org/wiki/Binary_search_tree",  # [text](url)
        b"https://docs.python.org/3/tutorial/classes.html",  # a bare web address
        URL.encode(),  # Open in Blackboard: <url>
    ]
    assert pdf.count(b"/Subtype /Link") == 3


def test_pdf_draws_turkish_letters_with_the_bundled_font():
    pdf = render_pdf(_note())
    assert b"/FontFile2" in pdf  # the subsetted TrueType font is embedded
    streams = _streams(pdf)
    for ch in "çğıİöşüÇĞÖŞÜ":
        # ToUnicode maps of the embedded fonts: the letter was drawn, not dropped.
        assert f"<{ord(ch):04X}>" in streams, ch
    assert "<FFFD>" not in streams


def test_same_note_gives_the_same_bytes_in_another_process():
    note = _note()
    first = render_pdf(note)
    assert render_pdf(note) == first
    assert b"/CreationDate (D:20000101000000+00'00')" in first
    code = ("import sys; from blackboard_sync.notepdf import render_pdf; "
            "sys.stdout.buffer.write(render_pdf(sys.stdin.read()))")
    env = {**os.environ, "PYTHONHASHSEED": "12345", "PYTHONIOENCODING": "utf-8"}
    other = subprocess.run([sys.executable, "-c", code], input=note.encode("utf-8"),
                           capture_output=True, check=True, env=env).stdout
    assert other == first


def test_drawing_a_note_needs_no_reportlab_graphics():
    # The packaged apps leave reportlab.graphics out (packaging/*.spec).
    code = ("import sys; sys.modules['reportlab.graphics'] = None; "
            "from blackboard_sync.notepdf import render_pdf; "
            "sys.stdout.buffer.write(render_pdf(sys.stdin.read()))")
    note = _note()
    out = subprocess.run([sys.executable, "-c", code], input=note.encode("utf-8"),
                         capture_output=True, check=True).stdout
    assert out == render_pdf(note)


def test_typical_notes_stay_small():
    assignment = render_pdf(_note())
    announcement = render_pdf(render_announcement_note(
        {"title": "Sınav salonları", "body": "<p>" + "Vize sınavı A-101 ve B-204 salonlarında. " * 60 + "</p>",
         "availability": {"duration": {"start": "2026-10-01T09:00:00Z"}}},
        "CSE303 Algorithm Analysis", URL,
    ))
    for pdf in (assignment, announcement):
        assert len(pdf) < SIZE_CEILING, len(pdf)


def test_characters_the_text_font_lacks_are_never_dropped():
    markup = inline("n ≤ 10 → x²≠∞ 😀")
    assert f'<font face="{MONO}">≤</font>' in markup and f'<font face="{MONO}">→</font>' in markup
    assert f'x²<font face="{MONO}">≠∞</font>' in markup
    assert "�" in markup and "😀" not in markup


def test_inline_markdown():
    assert inline("**bold** and _it_ and `x<y`") == f'<b>bold</b> and <i>it</i> and <font face="{MONO}">x&lt;y</font>'
    assert inline("my_file_name.pdf & co") == "my_file_name.pdf &amp; co"  # no italics inside words
    assert inline("[a *b*](https://x.org/p_(q))") == '<a href="https://x.org/p_(q)" color="#1a5fb4">a *b*</a>'
    # Only links a PDF viewer can open are made clickable.
    assert inline("[home](/webapps/portal) [js](javascript:alert(1))") == "home js"


# -- syncing ---------------------------------------------------------------------

def test_note_folder_shows_only_the_pdf_and_keeps_markdown_hidden(config, client):
    sync(config, client)
    assert NOTE in visible_files(config.dest)
    assert not any(f.endswith(".md") for f in visible_files(config.dest))
    pdf, markdown = config.dest / NOTE, config.dest / NOTE_MD
    assert markdown == note_markdown(pdf) and markdown.is_file()
    assert markdown.read_text(encoding="utf-8").startswith("# Intro: Asymptotic Notation\n")
    assert pdf.read_bytes() == render_pdf(markdown.read_text(encoding="utf-8"))
    state = State.load(config.state_file)
    assert state.output(PDF_KEY)["path"] == NOTE and state.output(MD_KEY)["path"] == NOTE_MD
    assert state.items[ITEM_KEY]["outputs"][-2:] == [PDF_KEY, MD_KEY]


def test_changed_note_rewrites_both_files_in_place(config, client, fake_bb):
    sync(config, client)
    before = visible_files(config.dest)
    _edit_note_on_blackboard(fake_bb, "<p>Read chapter 4 instead.</p>")
    report = sync(config, client)
    assert visible_files(config.dest) == before
    assert "Read chapter 4 instead." in note_text(config.dest / NOTE)
    assert (config.dest / NOTE).read_bytes() == render_pdf(note_text(config.dest / NOTE))
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.updated_notes == [NOTE] and cse.new_notes == []
    assert not list(config.dest.rglob("*(2)*"))


def test_unchanged_note_is_not_rewritten(config, client):
    sync(config, client)
    stamps = {p: (config.dest / p).stat().st_mtime_ns for p in (NOTE, NOTE_MD)}
    state = State.load(config.state_file)
    del state.items[ITEM_KEY]  # look at the item again: identical bytes write nothing
    state.dirty = True
    state.save()
    report = sync(config, client)
    assert report.totals()["updated_notes"] == report.totals()["new_notes"] == 0
    assert {p: (config.dest / p).stat().st_mtime_ns for p in (NOTE, NOTE_MD)} == stamps


@pytest.mark.skipif(sys.platform != "win32", reason="the hidden attribute exists on Windows only")
def test_markdown_copy_has_the_hidden_attribute_on_windows(config, client, fake_bb):
    def hidden(rel):
        return bool(os.stat(config.dest / rel).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)

    sync(config, client)
    assert hidden(NOTE_MD) and not hidden(NOTE)
    _edit_note_on_blackboard(fake_bb, "<p>Read chapter 4 instead.</p>")
    sync(config, client)  # replacing the hidden file in place keeps it hidden
    assert hidden(NOTE_MD) and not hidden(NOTE)
    assert "Read chapter 4 instead." in note_text(config.dest / NOTE)


def _as_older_version(config):
    """Turn the note into what versions before PDF notes saved: a visible "Name.md"."""
    state = State.load(config.state_file)
    markdown = state.outputs.pop(MD_KEY)
    pdf = state.outputs.pop(PDF_KEY)
    (config.dest / pdf["path"]).unlink()
    (config.dest / markdown["path"]).rename(config.dest / LEGACY)
    state.outputs[PDF_KEY] = {**markdown, "path": LEGACY}
    state.items[ITEM_KEY]["outputs"].remove(MD_KEY)
    state.dirty = True
    state.save()


def test_older_visible_markdown_note_is_hidden_when_the_note_is_written_again(config, client, fake_bb):
    sync(config, client)
    _as_older_version(config)
    sync(config, client)  # unchanged on Blackboard: older notes are left as they are
    assert LEGACY in visible_files(config.dest) and NOTE not in visible_files(config.dest)

    _edit_note_on_blackboard(fake_bb, "<p>Read chapter 4 instead.</p>")
    report = sync(config, client)

    assert NOTE in visible_files(config.dest) and LEGACY not in visible_files(config.dest)
    assert "Read chapter 4 instead." in note_text(config.dest / NOTE)
    state = State.load(config.state_file)
    assert state.output(PDF_KEY)["path"] == NOTE and state.output(MD_KEY)["path"] == NOTE_MD
    assert state.owner_of(NOTE_MD) == MD_KEY and state.owner_of(LEGACY) is None
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.new_notes == [NOTE] and cse.updated_notes == []
    assert not list(config.dest.rglob("*(2)*"))


def test_older_note_keeps_an_unrelated_hidden_file_of_the_same_name(config, client, fake_bb):
    sync(config, client)
    _as_older_version(config)
    (config.dest / NOTE_MD).write_text("not ours", encoding="utf-8")
    _edit_note_on_blackboard(fake_bb, "<p>Read chapter 4 instead.</p>")
    sync(config, client)
    assert (config.dest / NOTE_MD).read_text(encoding="utf-8") == "not ours"
    copy = State.load(config.state_file).output(MD_KEY)["path"]
    assert copy.endswith("/.Intro - Asymptotic Notation (2).md")
    assert "Read chapter 4 instead." in (config.dest / copy).read_text(encoding="utf-8")
    assert not (config.dest / LEGACY).exists()


def test_restoring_a_deleted_note_brings_back_both_files(config, client):
    sync(config, client)
    (config.dest / NOTE).unlink()
    (config.dest / NOTE_MD).unlink()
    rows = missing_outputs(State.load(config.state_file), config.dest)
    assert [row.key for row in rows] == [PDF_KEY]  # the hidden copy is not listed
    report = sync(config, client, refetch_missing=True, refetch_keys={PDF_KEY})
    assert report.message == "1 dosya indirildi."
    assert "Read chapter 3 before class." in note_text(config.dest / NOTE)


def test_restoring_a_deleted_older_note_saves_it_as_pdf(config, client):
    sync(config, client)
    _as_older_version(config)
    (config.dest / LEGACY).unlink()
    assert [row.key for row in missing_outputs(State.load(config.state_file), config.dest)] == [PDF_KEY]
    report = sync(config, client, refetch_missing=True, refetch_keys={PDF_KEY})
    assert report.message == "1 dosya indirildi."
    assert "Read chapter 3 before class." in note_text(config.dest / NOTE)
    assert not (config.dest / LEGACY).exists()


def test_restoring_another_file_leaves_an_older_note_alone(config, client, fake_bb):
    sync(config, client)
    _as_older_version(config)
    slides = next(k for k, o in State.load(config.state_file).outputs.items() if o["path"].endswith("week1-slides.pdf"))
    (config.dest / State.load(config.state_file).output(slides)["path"]).unlink()
    sync(config, client, refetch_missing=True, refetch_keys={slides})
    assert LEGACY in visible_files(config.dest) and NOTE not in visible_files(config.dest)


def test_dry_run_reports_an_older_note_as_its_pdf(config, client, fake_bb):
    sync(config, client)
    _as_older_version(config)
    _edit_note_on_blackboard(fake_bb, "<p>Read chapter 4 instead.</p>")
    report = sync(config, client, dry_run=True)
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.new_notes == [NOTE]
    assert (config.dest / LEGACY).exists() and not (config.dest / NOTE).exists()


def test_moving_between_drives_keeps_the_markdown_copy_hidden(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(relocate, "set_hidden", lambda path, hidden: calls.append(hidden))
    for name in ("Note.pdf", ".Note.md"):
        src, dst = tmp_path / "a" / name, tmp_path / "b" / name
        src.parent.mkdir(exist_ok=True)
        dst.parent.mkdir(exist_ok=True)
        src.write_bytes(b"x")
        calls.clear()
        relocate._copy_then_remove(src, dst)
        assert calls[-1] is name.startswith(".") and dst.read_bytes() == b"x" and not src.exists()


def test_moves_count_only_visible_files_and_carry_the_markdown_copy(config, client, tmp_path):
    sync(config, client)
    shown = len(visible_files(config.root))
    assert relocate.count_synced_files(config.state_file, config.dest) == shown
    new = tmp_path / "Okul"
    result = relocate.move_destination(config.state_file, config.lock_file, config.dest, new)
    assert result.status == "ok" and result.moved == shown and result.kept == []
    assert (sync_root(new) / NOTE_MD).is_file() and not (config.root / NOTE_MD).exists()


def test_uninstall_trashes_the_markdown_copies_too(config, client):
    sync(config, client)
    trashed = []

    def trash(path):
        trashed.append(path)
        path.unlink() if path.is_file() else path.rmdir()

    assert trash_course_files(config, send_to_trash=trash) == []
    assert config.root / NOTE_MD in trashed
    assert not [p for p in config.root.rglob("*") if p.is_file()]
