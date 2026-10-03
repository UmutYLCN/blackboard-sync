from blackboard_sync.htmltext import body_text, find_embedded_files, html_to_markdown
from blackboard_sync.notes import needs_note, render_announcement_note, render_item_note

URL = "https://blackboard.example.edu/ultra/courses/_1_1/outline"


def test_html_to_markdown_basic_formatting():
    html = (
        "<h2>Exam</h2><p>The exam is on <strong>Friday</strong> in <em>room 101</em>.</p>"
        "<ul><li>Bring ID</li><li>No phones</li></ul>"
        '<p>Details: <a href="https://example.org/exam">exam page</a></p>'
        '<p><a href="https://example.org/raw">https://example.org/raw</a></p>'
    )
    assert html_to_markdown(html) == (
        "## Exam\n\n"
        "The exam is on **Friday** in _room 101_.\n\n"
        "- Bring ID\n- No phones\n\n"
        "Details: [exam page](https://example.org/exam)\n\n"
        "<https://example.org/raw>"
    )


def test_html_to_markdown_ordered_list_breaks_and_entities():
    html = "<ol><li>One</li><li>Two &amp; three</li></ol><p>a<br>b</p><p><strong></strong></p>"
    assert html_to_markdown(html) == "1. One\n2. Two & three\n\na\nb"


def test_html_to_markdown_plain_text_passthrough():
    assert html_to_markdown("just text") == "just text"
    assert html_to_markdown("") == ""


def test_body_text_accepts_rich_text_objects():
    assert body_text({"rawText": "<p>x</p>", "displayText": "<p>y</p>"}) == "<p>x</p>"
    assert body_text(None) == ""


def test_find_embedded_files_reads_bbfile_metadata():
    html = (
        '<a href="https://bb.example.edu/bbcswebdav/xid-12_1" '
        'data-bbfile="{&quot;linkName&quot;:&quot;slides.pdf&quot;}">click</a>'
        '<img src="https://bb.example.edu/bbcswebdav/xid-13_1" alt="diagram.png">'
        '<a href="https://bb.example.edu/bbcswebdav/xid-12_1">dup</a>'
    )
    files = find_embedded_files(html)
    assert [(f.xid, f.name) for f in files] == [("12_1", "slides.pdf"), ("13_1", "diagram.png")]


def test_link_note():
    item = {
        "title": "Course Website: Visualizations",
        "description": "Interactive sorting visualizations.",
        "modified": "2026-09-02T10:00:00.000Z",
        "contentHandler": {"id": "resource/x-bb-externallink", "url": "https://example.org/visualgo"},
    }
    note = render_item_note(item, "CSE303 Algorithm Analysis", URL)
    assert note == (
        "# Course Website: Visualizations\n\n"
        "_Link · CSE303 Algorithm Analysis_\n\n"
        "Link: <https://example.org/visualgo>\n\n"
        "Interactive sorting visualizations.\n\n"
        "---\n"
        f"Open in Blackboard: <{URL}>\n"
        "Last changed on Blackboard: 2026-09-02T10:00:00.000Z\n"
    )


def test_document_note_lists_saved_files():
    item = {
        "title": "Intro",
        "body": "<p>Read chapter 3.</p>",
        "contentHandler": {"id": "resource/x-bb-document"},
    }
    note = render_item_note(item, "CSE303 Algorithm Analysis", URL, ["week1-slides.pdf"])
    assert "_Document · CSE303 Algorithm Analysis_" in note
    assert "Read chapter 3." in note
    assert "Files saved next to this note:\n- week1-slides.pdf" in note


def test_announcement_note():
    ann = {
        "title": "Welcome to CSE303",
        "body": "<p>Welcome! Office hours are on <em>Tuesdays</em>.</p>",
        "created": "2026-09-20T08:00:00.000Z",
        "modified": "2026-09-20T08:00:00.000Z",
    }
    note = render_announcement_note(ann, "CSE303 Algorithm Analysis", URL)
    assert note.startswith(
        "# Welcome to CSE303\n\n"
        "_Announcement · CSE303 Algorithm Analysis · 2026-09-20_\n\n"
        "Welcome! Office hours are on _Tuesdays_.\n"
    )


def test_needs_note():
    assert not needs_note({"contentHandler": {"id": "resource/x-bb-file"}})
    assert not needs_note({"contentHandler": {"id": "resource/x-bb-document"}, "body": "<p></p>"})
    assert needs_note({"contentHandler": {"id": "resource/x-bb-document"}, "body": "<p>Hi</p>"})
    assert needs_note({"contentHandler": {"id": "resource/x-bb-externallink", "url": "u"}})
    assert needs_note({"contentHandler": {"id": "resource/x-bb-asmt-test-link"}})
