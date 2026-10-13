"""The local announcements page uses sync data, never a live Blackboard request."""
import json
from dataclasses import replace

import pytest

from blackboard_sync import announcements
from blackboard_sync.state import State
from .conftest import POSIX
from .test_announcement_files import ANNOUNCEMENTS, add_announcement
from .test_sync import NOW, sync


def test_page_persists_all_announcements_newest_first_and_opens_saved_note(config, client, fake_bb):
    add_announcement(fake_bb, "<p>Exam <strong>rooms</strong> &amp; times.</p><p>Be early.</p>")
    sync(config, client)
    calls = list(fake_bb.calls)
    rows = announcements.load_rows(config)
    assert [r.title for r in rows] == ["Exam rooms", "Welcome to CSE303"]
    assert rows[0].course == "CSE303 Algorithm Analysis"
    assert rows[0].date == announcements._date("2026-10-01T08:00:00Z").astimezone().strftime("%d.%m.%Y %H:%M")
    assert rows[0].preview == "Exam rooms & times. Be early."
    assert announcements.open_target(rows[0], config.root) == config.root / rows[0].path
    assert fake_bb.calls == calls
    state = State.load(config.state_file)
    assert len(state.current_courses) == 3
    assert not any("draft" in r.title.casefold() for r in rows)


def test_old_state_backfills_metadata_without_rewriting_unchanged_notes(config, client, fake_bb):
    sync(config, client)
    before = {r.path: (config.root / r.path).stat().st_mtime_ns for r in announcements.load_rows(config)}
    data = json.loads(config.state_file.read_text())
    data.pop("announcements")
    data.pop("current_courses")
    config.state_file.write_text(json.dumps(data))
    assert announcements.load_rows(config) == ()
    fake_bb.calls.clear()
    report = sync(config, client)
    assert all(value == 0 for value in report.totals().values())
    assert fake_bb.downloads() == []
    rows = announcements.load_rows(config)
    assert len(rows) == 1
    assert {r.path: (config.root / r.path).stat().st_mtime_ns for r in rows} == before


def test_current_terms_filter_archives(config, client, fake_bb):
    # Even --all-terms cannot add old courses to the page.
    sync(config, client, all_terms=True)
    state = State.load(config.state_file)
    state.record_announcement("announcement:old:1", announcements.metadata(
        {"title": "Old announcement"}, "old", "Old course", "/ultra/courses/old/announcements", "old-note"))
    state.save()
    assert all(r.title != "Old announcement" for r in announcements.load_rows(config))
    # An explicitly archived term cannot become current when old courses are the fallback.
    memberships = next(v for k, v in fake_bb.routes.items() if k.endswith("/courses") and "/users/" in k)
    memberships["results"] = [m for m in memberships["results"] if m.get("course", {}).get("termId") != "_50_1"]
    sync(config, client)
    state = State.load(config.state_file)
    old_term = next(v for k, v in fake_bb.routes.items() if k.endswith("/terms/_40_1"))["name"]
    state.record_past_term("_40_1", old_term, state.current_courses)
    state.save()
    sync(config, client)
    assert announcements.load_rows(config) == ()


def test_failed_fetch_keeps_cached_rows_and_dry_run_does_not_write(config, client, fake_bb):
    sync(config, client)
    before = config.state_file.read_bytes()
    add_announcement(fake_bb, "<p>New text</p>")
    sync(config, client, dry_run=True)
    assert config.state_file.read_bytes() == before
    del fake_bb.routes[ANNOUNCEMENTS]
    sync(config, client)
    assert [r.title for r in announcements.load_rows(config)] == ["Welcome to CSE303"]


def test_preview_dates_order_and_safe_targets(config, client, fake_bb):
    ann = add_announcement(fake_bb, {"rawText": "<style>hidden</style><script>hidden</script><p>" + "ş" * 500 + "</p>"})
    ann["title"] = "Sınav &amp; ders"
    ann["created"] = "2026-09-01T09:00:00Z"
    ann["availability"] = {"duration": {"start": "2026-10-01T09:00:00+03:00"}}
    fake_bb.routes[ANNOUNCEMENTS]["results"] += [
        {"id": "later", "title": "Later", "created": "2026-10-01T08:00:00Z"},
        {"id": "unknown", "title": "Undated", "created": "bad"},
        {"id": "draft", "title": "Draft", "draft": True},
    ]
    sync(config, client)
    rows = announcements.load_rows(config)
    assert [r.title for r in rows] == ["Later", "Sınav & ders", "Welcome to CSE303", "Undated"]
    row = rows[1]
    assert row.preview == "ş" * 239 + "…"
    assert rows[-1].date == announcements.T_NO_DATE
    (config.root / row.path).unlink()
    assert announcements.open_target(row, config.root) == row.url
    outside = config.data_dir / "outside.pdf"
    outside.write_bytes(b"pdf")
    for path in (str(outside), "../../data/outside.pdf"):
        assert announcements.open_target(replace(row, path=path), config.root) == row.url
    if POSIX:  # Windows symlink creation needs privileges unavailable on some installs.
        link = config.root / "escaped.pdf"
        link.symlink_to(outside)
        assert announcements.open_target(replace(row, path="escaped.pdf"), config.root) == row.url
    assert announcements.open_target(replace(row, url="file:///private/file"), config.root) is None


def test_output_moves_are_reflected_without_duplicate_metadata(config, client):
    sync(config, client)
    row = announcements.load_rows(config)[0]
    state = State.load(config.state_file)
    state.move_file(row.path, "renamed/note.pdf")
    state.save()
    assert announcements.load_rows(config)[0].path == "renamed/note.pdf"


def test_membership_changes_and_filtered_sync_keep_only_current_course_rows(config, client, fake_bb):
    sync(config, client)
    sync(config, client, course_filters=["MTH201"])
    assert len(announcements.load_rows(config)) == 1
    # When current-term courses disappear, the selector falls back to the
    # older term. Notes stay on disk but leave the current announcements page.
    memberships = next(v for k, v in fake_bb.routes.items() if k.endswith("/courses") and "/users/" in k)
    memberships["results"] = [m for m in memberships["results"] if m.get("course", {}).get("termId") != "_50_1"]
    sync(config, client)
    assert len(State.load(config.state_file).announcements) == 1
    assert announcements.load_rows(config) == ()


def test_windows_page_empty_rows_click_and_refresh_with_fakes(monkeypatch, tmp_path):
    from .test_windows import fake_tk
    from blackboard_sync.menubar.main_window_model import ANNOUNCEMENTS, main_status
    from blackboard_sync.menubar.model import AppModel
    from blackboard_sync.menubar.settings_form import FormValues
    from blackboard_sync.windows.main_window import MainWindow

    widgets = fake_tk(monkeypatch, tmp_path)
    rows, opened = [], []
    model = AppModel(tmp_path, NOW)
    window = MainWindow(None, FormValues("https://bb.example", str(tmp_path), True),
                        main_status(model, NOW), lambda *_: None, lambda *_: None, lambda: None,
                        on_announcements=lambda: tuple(rows), on_open_announcement=opened.append)
    window.select(ANNOUNCEMENTS)
    assert window.visible_page() == ANNOUNCEMENTS
    assert window.nav[ANNOUNCEMENTS].options["text"] == "Duyurular"
    assert any(w.options.get("text") == announcements.T_EMPTY for w in widgets)
    rows.append(announcements.AnnouncementRow("one", "CSE303", "Sınav", "01.10.2026", "Odalar", "note.pdf", "https://bb.example"))
    window.update_status(main_status(model, NOW))
    button = next(w for w in widgets if w.options.get("text") == announcements.T_OPEN)
    button.options["command"]()
    assert opened == rows
    title = next(w for w in widgets if w.options.get("text") == "Sınav")
    title.bindings["<Button-1>"](None)
    assert opened == rows * 2
    window.announcements_canvas.view = (0, 0.5)
    from types import SimpleNamespace
    window.wheel(SimpleNamespace(delta=-120))
    assert window.announcements_canvas.scrolled == [(1, "units")]


def test_macos_page_cards_click_and_empty_state(tmp_path):
    pytest.importorskip("AppKit")
    pytest.importorskip("rumps")
    from .test_menubar_app import make_window, visible_page
    from blackboard_sync.menubar.main_window_model import ANNOUNCEMENTS

    rows, opened = [], []
    window, _, _ = make_window(tmp_path, on_announcements=lambda: tuple(rows), on_open_announcement=opened.append)
    try:
        window.select(ANNOUNCEMENTS)
        assert visible_page(window) == ANNOUNCEMENTS
        assert window.nav_items[ANNOUNCEMENTS][2].stringValue() == "Duyurular"
        document = window.announcements_scroll.documentView()
        assert document.subviews()[0].stringValue() == announcements.T_EMPTY
        rows.append(announcements.AnnouncementRow("one", "CSE303", "Sınav", "01.10.2026", "Odalar", "note.pdf", "https://bb.example"))
        window.refresh_announcements()
        card = window.announcements_scroll.documentView().subviews()[0]
        button = card.contentView().subviews()[-1]
        window.target.openAnnouncement_(button)
        assert opened == rows
    finally:
        window.window.close()


def test_windows_open_action_uses_note_then_blackboard(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from .test_windows import make_app
    from blackboard_sync.windows import app as module

    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(messagebox=SimpleNamespace()))
    app = make_app(tmp_path)
    app.model.root.mkdir(parents=True)
    note = app.model.root / "note.pdf"
    note.write_bytes(b"pdf")
    row = announcements.AnnouncementRow("one", "CSE303", "Sınav", "01.10.2026", "Odalar", "note.pdf", "https://bb.example/announcements")
    opened, browsed = [], []
    monkeypatch.setattr(module.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(module.webbrowser, "open", browsed.append)
    app.dispatch("announcement", row)
    assert opened == [str(note)] and browsed == []
    note.unlink()
    app.dispatch("announcement", row)
    assert browsed == [row.url]
