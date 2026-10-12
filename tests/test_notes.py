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


def test_embedded_file_prefers_permanent_link_over_session_resource():
    import html
    import json

    resource = "https://bb.example.edu/sessions/AA/SESSION/abcdef0123456789abcdef0123456789/guide.pdf?token=FIRST"
    permanent = "https://bb.example.edu/bbcswebdav/pid-700-dt-asiobject-rid-14_1/xid-14_1?token=SECOND"
    meta = html.escape(json.dumps({"resourceUrl": resource, "displayName": "guide.pdf"}), quote=True)
    files = find_embedded_files(f'<a data-bbfile="{meta}" href="{permanent}">Guide</a>')
    assert [(f.xid, f.name, f.url) for f in files] == [("14_1", "guide.pdf", permanent)]


def test_session_links_without_file_metadata_are_not_downloads():
    url = "/sessions/AA/SESSION/abcdef0123456789abcdef0123456789/guide.pdf"
    assert find_embedded_files(f'<a href="{url}">Ordinary link</a>') == []


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


INSTRUCTIONS = (
    "<h3>Lab 2: Sorting</h3><p>Write a short report on your results.</p>"
    "<h4>Requirements</h4>"
    "<ol><li>Implement merge sort<ul><li>Use Python</li><li>No sorting libraries</li></ul></li>"
    "<li>Measure the run time</li></ol>"
    "<h4>Questions</h4>"
    "<ol><li>Why is merge sort O(n log n)?</li><li>When is insertion sort faster?</li></ol>"
)


def assignment(**fields):
    handler = {"id": "resource/x-bb-asmt-test-link", "instructions": fields.pop("instructions", None)}
    return {"title": "Lab 2", "modified": "2026-10-01T09:00:00.000Z", "contentHandler": handler, **fields}


def test_assignment_note_includes_instructions():
    note = render_item_note(assignment(instructions={"rawText": INSTRUCTIONS}), "CSE303", URL, ["data.csv"])
    assert note == (
        "# Lab 2\n\n"
        "_Assignment / test · CSE303_\n\n"
        "### Lab 2: Sorting\n\n"
        "Write a short report on your results.\n\n"
        "#### Requirements\n\n"
        "1. Implement merge sort\n"
        "   - Use Python\n"
        "   - No sorting libraries\n"
        "2. Measure the run time\n\n"
        "#### Questions\n\n"
        "1. Why is merge sort O(n log n)?\n"
        "2. When is insertion sort faster?\n\n"
        "Files saved next to this note:\n- data.csv\n\n"
        "---\n"
        f"Open in Blackboard: <{URL}>\n"
        "Last changed on Blackboard: 2026-10-01T09:00:00.000Z\n"
    )


def test_html_to_markdown_nests_lists_under_their_parent_item_text():
    html = (
        "<ul><li>Part A<ol><li>Read</li><li>Write<ul><li>Short</li></ul></li></ol></li></ul>"
        "<ol>" + "<li>x</li>" * 9 + "<li>Ten<ul><li>Nested</li></ul></li></ol>"
    )
    assert html_to_markdown(html) == (
        "- Part A\n  1. Read\n  2. Write\n     - Short\n\n"
        + "".join(f"{n}. x\n" for n in range(1, 10))
        + "10. Ten\n    - Nested"
    )


def test_assignment_note_without_instructions_is_unchanged():
    expected = (
        "# Lab 2\n\n"
        "_Assignment / test · CSE303_\n\n"
        "---\n"
        f"Open in Blackboard: <{URL}>\n"
        "Last changed on Blackboard: 2026-10-01T09:00:00.000Z\n"
    )
    assert render_item_note(assignment(), "CSE303", URL) == expected
    assert render_item_note(assignment(instructions=""), "CSE303", URL) == expected
    # Instructions that only link files show the files, not an empty block.
    file_link = '<a href="https://bb.example.edu/bbcswebdav/xid-1_1" data-bbfile="{}">guide.pdf</a>'
    assert render_item_note(assignment(instructions=f"<p>{file_link}</p>"), "CSE303", URL) == expected


def test_instructions_repeated_in_body_appear_once():
    note = render_item_note(
        assignment(body=INSTRUCTIONS, instructions={"rawText": INSTRUCTIONS}), "CSE303", URL
    )
    assert note.count("Write a short report on your results.") == 1
    assert note.count("#### Questions") == 1


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


def deadline_note(**fields):
    return render_item_note(assignment(**fields), "CSE303", URL)


def test_assignment_note_shows_due_date_and_points():
    note = deadline_note(grading={"due": "2026-10-16T16:00:00.000Z"}, score={"possible": 100.0})
    assert note.startswith("# Lab 2\n\n_Assignment / test · CSE303_\n\nDue: 2026-10-16 16:00 UTC · Points: 100\n\n---\n")


def test_assignment_note_shows_only_the_deadline_field_it_has():
    assert "\nDue: 2026-10-16 16:00 UTC\n" in deadline_note(grading={"due": "2026-10-16T16:00:00Z"})
    assert "Points" not in deadline_note(grading={"due": "2026-10-16T16:00:00Z"})
    note = deadline_note(score={"possible": 12.5})
    assert "\nPoints: 12.5\n" in note and "Due" not in note


def test_due_date_with_an_offset_is_shown_in_utc_and_unclear_values_are_kept():
    assert "Due: 2026-10-16 13:00 UTC" in deadline_note(grading={"due": "2026-10-16T16:00:00+03:00"})
    # No timezone given: show it as received instead of guessing one.
    assert "Due: 2026-10-16T16:00:00" in deadline_note(grading={"due": "2026-10-16T16:00:00"})
    assert "Due: next Friday" in deadline_note(grading={"due": "next Friday"})


def test_item_without_deadline_fields_is_unchanged():
    expected = deadline_note()
    assert deadline_note(grading=None, score=None) == expected
    assert "Due" not in expected and "Points" not in expected


def test_malformed_or_empty_deadline_values_do_not_break_the_note():
    expected = deadline_note()
    for fields in (
        {"grading": {"due": ""}, "score": {"possible": None}},
        {"grading": {"due": "  "}, "score": {"possible": ""}},
        {"grading": "soon", "score": [1, 2]},
        {"grading": {"due": 12345}, "score": {"possible": True}},
        {"grading": {"due": None}, "score": {"possible": float("nan")}},
        {"grading": {}, "score": {"possible": float("inf")}},
    ):
        assert deadline_note(**fields) == expected
