import json
from datetime import datetime, timezone

from blackboard_sync import sync as sync_mod
from blackboard_sync.state import State
from blackboard_sync.sync import Term, choose_current_terms, parse_time, run_sync

from .conftest import assert_owner_only

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
CSE = "2026-2027 Güz/CSE303 Algorithm Analysis"
SYLLABUS = f"{CSE}/Syllabus/CSE303_Algorithm_Analysis_for_Computer_Engineering_Syllabus_v1.pdf"
SLIDES = f"{CSE}/Lecture Notes/Week 1/week1-slides.pdf"
SYLLABUS_DL = "/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments/_a11_1/download"


def sync(config, client, **kwargs):
    return run_sync(config, client, now=NOW, **kwargs)


def files_under(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_first_sync_mirrors_the_course_tree(config, client):
    report = sync(config, client)

    assert report.status == "ok"
    assert report.terms == ["2026-2027 Güz"]
    assert files_under(config.dest) == sorted(
        [
            SYLLABUS,
            SLIDES,
            f"{CSE}/Lecture Notes/Week 1/Intro - Asymptotic Notation.md",
            f"{CSE}/Course Website - Visualizations.md",
            f"{CSE}/Homework 1.md",
            f"{CSE}/hw1.pdf",
            f"{CSE}/Duyurular/2026-09-20 Welcome to CSE303.md",
        ]
    )
    # Empty folders on Blackboard exist locally too, so the structure matches.
    assert (config.dest / CSE / "Lecture Notes" / "Week 2").is_dir()
    # Every current-term course gets a folder; past terms and private courses do not.
    assert sorted(p.name for p in (config.dest / "2026-2027 Güz").iterdir()) == [
        "COE305 Software Project Management",
        "CSE303 Algorithm Analysis",
        "MTH201 Linear Algebra",
    ]
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"

    cse = next(c for c in report.courses if c.code == "CSE303")
    assert sorted(cse.new_files) == sorted([SYLLABUS, SLIDES, f"{CSE}/hw1.pdf"])
    assert cse.new_announcements == [f"{CSE}/Duyurular/2026-09-20 Welcome to CSE303.md"]
    assert cse.summary_line() == "CSE303: 3 new files, 3 new notes, 1 new announcement"
    note = (config.dest / CSE / "Lecture Notes/Week 1/Intro - Asymptotic Notation.md").read_text(encoding="utf-8")
    assert "Read chapter 3 before class." in note
    assert "- week1-slides.pdf" in note


def test_second_run_downloads_nothing(config, client, fake_bb):
    sync(config, client)
    downloads_after_first = len(fake_bb.downloads())
    before = {p: (config.dest / p).stat().st_mtime_ns for p in files_under(config.dest)}

    report = sync(config, client)

    assert len(fake_bb.downloads()) == downloads_after_first
    assert report.totals() == {k: 0 for k in report.totals()}
    assert report.render_text().endswith("Nothing new.")
    assert {p: (config.dest / p).stat().st_mtime_ns for p in files_under(config.dest)} == before


def test_only_new_items_are_fetched(config, client, fake_bb):
    sync(config, client)
    week2 = "/learn/api/public/v1/courses/_13004_1/contents/_c22_1/children"
    fake_bb.routes[week2]["results"].append(
        {
            "id": "_c221_1", "title": "Week 2 slides", "position": 0,
            "modified": "2026-10-02T09:00:00.000Z",
            "contentHandler": {"id": "resource/x-bb-file"},
        }
    )
    fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c221_1/attachments"] = {
        "results": [{"id": "_a221_1", "fileName": "week2.pdf"}]
    }
    new_dl = "/learn/api/public/v1/courses/_13004_1/contents/_c221_1/attachments/_a221_1/download"
    fake_bb.files[new_dl] = b"%PDF week 2"
    fake_bb.calls.clear()

    report = sync(config, client)

    assert fake_bb.downloads() == [new_dl]
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.new_files == [f"{CSE}/Lecture Notes/Week 2/week2.pdf"]
    assert cse.summary_line() == "CSE303: 1 new file"
    summary = report.to_dict()
    assert summary["changed_courses"] == [
        {"code": "CSE303", "name": "Algorithm Analysis", "summary": "CSE303: 1 new file", "changes": 1}
    ]


def _touch_syllabus(fake_bb, content):
    children = fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c1_1/children"]
    children["results"][0]["modified"] = "2026-10-01T00:00:00.000Z"
    fake_bb.files[SYLLABUS_DL] = content


def test_changed_item_with_same_bytes_is_not_reported(config, client, fake_bb):
    sync(config, client)
    _touch_syllabus(fake_bb, b"%PDF syllabus v1")
    report = sync(config, client)
    assert report.totals()["updated_files"] == 0
    assert files_under(config.dest).count(SYLLABUS) == 1


def test_changed_file_replaces_untouched_local_copy(config, client, fake_bb):
    sync(config, client)
    _touch_syllabus(fake_bb, b"%PDF syllabus v2")
    report = sync(config, client)
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.updated_files == [SYLLABUS]
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v2"


def test_changed_file_never_overwrites_local_edits(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).write_bytes(b"%PDF syllabus v1 + my highlights")
    _touch_syllabus(fake_bb, b"%PDF syllabus v2")
    sync(config, client)
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1 + my highlights"
    updated = SYLLABUS.replace("_v1.pdf", "_v1 (2).pdf")
    assert (config.dest / updated).read_bytes() == b"%PDF syllabus v2"


def test_items_removed_on_blackboard_stay_local(config, client, fake_bb):
    sync(config, client)
    fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c1_1/children"]["results"] = []
    sync(config, client)
    assert (config.dest / SYLLABUS).exists()


def test_locally_deleted_files_are_respected_unless_asked(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    sync(config, client)
    assert not (config.dest / SYLLABUS).exists()
    sync(config, client, refetch_missing=True)
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"


def test_name_collisions_get_numbered(config, client, fake_bb):
    root = fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents"]["results"]
    root.append(
        {
            "id": "_c5_1", "title": "Homework 1", "position": 4,
            "modified": "2026-09-06T10:00:00.000Z",
            "contentHandler": {"id": "resource/x-bb-externallink", "url": "https://example.org/hw"},
        }
    )
    sync(config, client)
    assert (config.dest / CSE / "Homework 1.md").exists()
    assert (config.dest / CSE / "Homework 1 (2).md").exists()


def test_existing_identical_file_is_adopted(config, client, fake_bb):
    (config.dest / CSE / "Syllabus").mkdir(parents=True)
    (config.dest / SYLLABUS).write_bytes(b"%PDF syllabus v1")
    report = sync(config, client)
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert SYLLABUS not in cse.new_files
    assert not (config.dest / SYLLABUS.replace(".pdf", " (2).pdf")).exists()


def test_state_file_is_private_and_keyed_by_blackboard_ids(config, client):
    sync(config, client)
    assert_owner_only(config.state_file)
    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["items"]["content:_13004_1:_c11_1"]["modified"] == "2026-09-01T10:05:00.000Z"
    assert state["outputs"]["attachment:_13004_1:_a11_1"]["path"] == SYLLABUS
    assert "xid:_13004_1:_c211_1:777_1" in state["outputs"]


def test_dry_run_writes_nothing(config, client, fake_bb):
    report = sync(config, client, dry_run=True)
    assert not config.dest.exists()
    assert not config.state_file.exists()
    assert fake_bb.downloads() == []
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert SYLLABUS in cse.new_files


def test_course_filter_and_explicit_term(config, client):
    report = sync(config, client, course_filters=["cse303"])
    assert [c.code for c in report.courses] == ["CSE303"]
    report = sync(config, client, term_name="2025-2026 Bahar")
    assert [c.folder for c in report.courses] == ["2025-2026 Bahar/CSE201 Data Structures"]


def test_failed_announcements_are_a_warning_not_a_failure(config, client, fake_bb):
    del fake_bb.routes["/learn/api/public/v1/courses/_13010_1/announcements"]
    report = sync(config, client)
    mth = next(c for c in report.courses if c.code == "MTH201")
    assert report.status == "ok"
    assert mth.warnings and "announcements" in mth.warnings[0]
    # The private-API fallback was tried before giving up.
    assert "/learn/api/v1/courses/_13010_1/announcements" in fake_bb.calls


def _term(tid, start, end, created=None):
    from blackboard_sync.sync import Course

    term = Term(tid, tid, parse_time(start), parse_time(end))
    if created:
        term.courses.append(Course("_1", "X1", "X", tid, tid, "", "X1", created))
    return term


def test_choose_current_terms_by_date_range():
    fall = _term("fall", "2026-09-21T00:00:00Z", "2027-01-31T00:00:00Z")
    spring = _term("spring", "2026-02-09T00:00:00Z", "2026-06-30T00:00:00Z")
    assert choose_current_terms([spring, fall], NOW) == [fall]
    # A month before the term starts, its courses already count as current.
    early = datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert choose_current_terms([spring, fall], early) == [fall]
    # In the summer gap, the most recently started term wins.
    summer = datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert choose_current_terms([spring, fall], summer) == [spring]


def test_choose_current_terms_without_dates_uses_newest_course():
    old = _term("old", None, None, created="2025-09-01T00:00:00Z")
    new = _term("new", None, None, created="2026-09-01T00:00:00Z")
    assert choose_current_terms([old, new], NOW) == [new]
    assert choose_current_terms([], NOW) == []


def test_state_reload_round_trip(tmp_path):
    state = State(tmp_path / "state.json")
    state.record_output("attachment:c:a", "T/C/x.pdf", "abc", 3)
    state.record_item("content:c:i", "2026-01-01", ["attachment:c:a"], "x")
    state.save()
    again = State.load(tmp_path / "state.json")
    assert again.owner_of("T/C/x.pdf") == "attachment:c:a"
    assert again.item_unchanged("content:c:i", "2026-01-01", tmp_path, check_missing=False)
    assert not again.item_unchanged("content:c:i", "2026-02-01", tmp_path, check_missing=False)


def _route_item(fake_bb, item_id):
    for body in fake_bb.routes.values():
        for item in (body.get("results") or []) if isinstance(body, dict) else []:
            if item.get("id") == item_id:
                return item
    raise KeyError(item_id)


def test_windows_names_are_valid_and_paths_fit(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: True)
    _route_item(fake_bb, "_c4_1")["title"] = 'Homework "1": done?'
    _route_item(fake_bb, "_a41_1")["fileName"] = "CON.pdf"
    _route_item(fake_bb, "_c3_1")["title"] = "Course Website: " + "v" * 300
    report = sync(config, client)
    assert report.status == "ok"
    files = files_under(config.dest)
    assert f"{CSE}/Homework '1' - done.md" in files
    assert f"{CSE}/CON_.pdf" in files
    website = next(f for f in files if f.startswith(f"{CSE}/Course Website - vvv"))
    assert len(website.rsplit("/", 1)[-1]) <= 120
    assert all(len(str(config.dest)) + 1 + len(f) <= 259 for f in files)


# -- Ultra documents: files embedded in the hidden "ultraDocumentBody" child -----------
COURSE = "/learn/api/public/v1/courses/_13004_1/contents"
WEEK = f"{CSE}/WEEK 01 - FUNDAMENTALS"


def ultra_body(rid, name, text=""):
    meta = json.dumps(
        {
            "linkName": name,
            "displayName": name,
            "mimeType": "application/octet-stream",
            "resourceUrl": f"https://blackboard.example.edu/bbcswebdav/pid-9-dt-content-rid-{rid}/xid-{rid}?t=TOKEN&e=EXPIRY&s=SIG",
        }
    )
    href = f"https://blackboard.example.edu/bbcswebdav/pid-9-dt-content-rid-{rid}/xid-{rid}?t=TOKEN&e=EXPIRY&s=SIG"
    link = (
        f'<a data-bbid="bbml-editor-id_0" data-bbfile="{meta.replace(chr(34), "&quot;")}" href="{href}"></a>'
    )
    return (
        '<div data-layout-row="r"><div data-layout-column="c" data-layout-column-width="12">'
        f"{text}{link}</div></div>"
    )


def add_ultra_doc(fake_bb, doc_id, title, body, rid, position=5):
    root = fake_bb.routes[COURSE]["results"]
    root.append(
        {
            "id": doc_id, "title": title, "position": position, "hasChildren": True,
            "modified": "2026-09-30T10:00:00.000Z",
            "contentHandler": {"id": "resource/x-bb-folder"},
        }
    )
    child = f"{doc_id}_body"
    fake_bb.routes[f"{COURSE}/{doc_id}/children"] = {
        "results": [
            {
                "id": child, "title": "ultraDocumentBody", "position": 0,
                "modified": "2026-09-30T10:00:00.000Z",
                "contentHandler": {"id": "resource/x-bb-document"},
                "body": body,
            }
        ]
    }
    # Real Blackboard answers 400 for these; the sync must not even ask.
    fake_bb.routes.pop(f"{COURSE}/{child}/attachments", None)
    return child


def ultra_course(fake_bb):
    add_ultra_doc(
        fake_bb, "_w1_1", "WEEK 01 - FUNDAMENTALS",
        ultra_body("4023455_1", "CSE301 - WEEK 01 - FUNDAMENTALS.pptx"), "4023455_1",
    )
    add_ultra_doc(
        fake_bb, "_w0_1", "COURSE SYLLABUS",
        ultra_body("4023400_1", "CSE301 - Ders İzlencesi ENG (Syllabus).docx"), "4023400_1", 6,
    )
    fake_bb.files["/bbcswebdav/pid-9-dt-content-rid-4023455_1/xid-4023455_1"] = b"PPTX v1"
    fake_bb.files["/bbcswebdav/pid-9-dt-content-rid-4023400_1/xid-4023400_1"] = b"DOCX v1"


def test_ultra_document_files_land_in_the_parent_folder(config, client, fake_bb):
    ultra_course(fake_bb)

    report = sync(config, client)

    files = files_under(config.dest)
    pptx = f"{WEEK}/CSE301 - WEEK 01 - FUNDAMENTALS.pptx"
    docx = f"{CSE}/COURSE SYLLABUS/CSE301 - Ders İzlencesi ENG (Syllabus).docx"
    assert pptx in files and docx in files
    assert (config.dest / pptx).read_bytes() == b"PPTX v1"
    # No hidden-child folder, and an empty layout wrapper produces no note.
    assert not any("ultraDocumentBody" in f for f in files)
    assert not any(f.startswith(WEEK) and f.endswith(".md") for f in files)
    assert not [w for c in report.courses for w in c.warnings]
    # Neither the attachment collection nor anything signed is stored.
    assert not any("_body/attachments" in c for c in fake_bb.calls)
    state = (config.data_dir / "state.json").read_text(encoding="utf-8")
    assert "TOKEN" not in state and "xid:_13004_1:_w1_1_body:4023455_1" in state


def test_ultra_body_text_becomes_the_documents_note(config, client, fake_bb):
    add_ultra_doc(
        fake_bb, "_w2_1", "WEEK 02 - E R MODEL I",
        ultra_body("4023500_1", "week2.pptx", "<p>Read chapter 2.</p>"), "4023500_1",
    )
    fake_bb.files["/bbcswebdav/pid-9-dt-content-rid-4023500_1/xid-4023500_1"] = b"PPTX w2"

    sync(config, client)

    folder = config.dest / CSE / "WEEK 02 - E R MODEL I"
    note = (folder / "WEEK 02 - E R MODEL I.md").read_text(encoding="utf-8")
    assert "Read chapter 2." in note and "- week2.pptx" in note
    assert "ultraDocumentBody" not in note and "TOKEN" not in note
    assert (folder / "week2.pptx").read_bytes() == b"PPTX w2"


def test_no_attachments_answer_is_silent(config, client, fake_bb):
    item = {
        "id": "_d1_1", "title": "Plain doc", "position": 7, "modified": "2026-09-30T10:00:00.000Z",
        "contentHandler": {"id": "resource/x-bb-document"}, "body": "<p>Hello</p>",
    }
    fake_bb.routes[COURSE]["results"].append(item)
    real_get = fake_bb.get

    def get(url, **kwargs):
        if url.endswith("/_d1_1/attachments"):
            from .conftest import FakeResponse

            return FakeResponse(
                400, url, {"status": 400, "message": "The Content Item does not support file attachments"}
            )
        return real_get(url, **kwargs)

    fake_bb.get = get
    report = sync(config, client)

    assert not [w for c in report.courses for w in c.warnings]
    assert (config.dest / CSE / "Plain doc.md").exists()


def test_other_400s_still_warn(config, client, fake_bb):
    fake_bb.routes[COURSE]["results"].append(
        {"id": "_d2_1", "title": "Odd", "position": 8, "modified": "x",
         "contentHandler": {"id": "resource/x-bb-document"}, "body": "<p>x</p>"}
    )
    real_get = fake_bb.get

    def get(url, **kwargs):
        if url.endswith("/_d2_1/attachments"):
            from .conftest import FakeResponse

            return FakeResponse(400, url, {"status": 400, "message": "Bad request"})
        return real_get(url, **kwargs)

    fake_bb.get = get
    report = sync(config, client)
    assert any("Skipped 'Odd'" in w for c in report.courses for w in c.warnings)


def test_ultra_second_run_downloads_nothing(config, client, fake_bb):
    ultra_course(fake_bb)
    sync(config, client)
    fake_bb.calls.clear()

    report = sync(config, client)

    assert fake_bb.downloads() == []
    assert report.totals() == {k: 0 for k in report.totals()}


def test_ultra_replaced_file_is_downloaded_again_in_place(config, client, fake_bb):
    ultra_course(fake_bb)
    sync(config, client)
    name = "CSE301 - WEEK 01 - FUNDAMENTALS.pptx"
    body = ultra_body("4023999_1", name)
    fake_bb.routes[f"{COURSE}/_w1_1/children"]["results"][0]["body"] = body  # "modified" unchanged
    fake_bb.files["/bbcswebdav/pid-9-dt-content-rid-4023999_1/xid-4023999_1"] = b"PPTX v2"
    fake_bb.calls.clear()

    report = sync(config, client)

    assert fake_bb.downloads() == ["/bbcswebdav/pid-9-dt-content-rid-4023999_1/xid-4023999_1"]
    assert (config.dest / WEEK / name).read_bytes() == b"PPTX v2"
    assert not (config.dest / WEEK / "CSE301 - WEEK 01 - FUNDAMENTALS (2).pptx").exists()
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.updated_files == [f"{WEEK}/{name}"]


def test_empty_folders_from_the_failed_runs_get_filled(config, client, fake_bb):
    ultra_course(fake_bb)
    (config.dest / WEEK).mkdir(parents=True)  # what the old version left behind

    sync(config, client)

    assert (config.dest / WEEK / "CSE301 - WEEK 01 - FUNDAMENTALS.pptx").exists()


def _corrupt_backups(config):
    return sorted(config.state_file.parent.glob("state.json.corrupt-*"))


def test_corrupt_state_is_backed_up_and_sync_continues(config, client):
    sync(config, client)
    files_before = files_under(config.dest)
    config.state_file.write_text("{ truncated", encoding="utf-8")

    report = sync(config, client)

    assert report.status in ("ok", "warnings")
    backups = _corrupt_backups(config)
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{ truncated"
    assert any("state.json" in w and backups[0].name in w for w in report.warnings)
    # the state healed: it is valid again and the next run is clean
    assert json.loads(config.state_file.read_text(encoding="utf-8"))["version"] == 1
    again = sync(config, client)
    assert not any("state.json" in w for w in again.warnings)
    assert len(_corrupt_backups(config)) == 1
    # existing files were adopted, not duplicated
    assert not any("(2)" in p for p in files_under(config.dest))
    assert files_under(config.dest) == files_before


def test_newer_state_version_is_kept_as_backup(config, client):
    sync(config, client)
    original = json.loads(config.state_file.read_text(encoding="utf-8"))
    original["version"] = 99
    config.state_file.write_text(json.dumps(original), encoding="utf-8")

    report = sync(config, client)

    backups = _corrupt_backups(config)
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["version"] == 99
    assert any("version" in w for w in report.warnings)


def test_state_with_wrong_shape_is_recovered(config, client):
    config.ensure_data_dir()
    config.state_file.write_text("[1, 2]", encoding="utf-8")
    report = sync(config, client)
    assert len(_corrupt_backups(config)) == 1
    assert any("state.json" in w for w in report.warnings)


def test_dry_run_leaves_corrupt_state_untouched(config, client):
    config.ensure_data_dir()
    config.state_file.write_text("{ truncated", encoding="utf-8")
    report = sync(config, client, dry_run=True)
    assert config.state_file.read_text(encoding="utf-8") == "{ truncated"
    assert _corrupt_backups(config) == []
    assert any("state.json" in w for w in report.warnings)
