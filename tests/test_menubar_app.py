import pytest

rumps = pytest.importorskip("rumps")
pytest.importorskip("AppKit")

from rumps.rumps import NSApp

from blackboard_sync.menubar.app import forget_menu_items


def build(menu, n_courses=8):
    courses = rumps.MenuItem("Dersler")
    for i in range(n_courses):
        course = rumps.MenuItem(f"CSE{i}", callback=lambda _s: None)
        course.add(rumps.MenuItem("dosya", callback=lambda _s: None))
        courses.add(course)
    menu.update([rumps.MenuItem("durum"), rumps.separator, courses, rumps.MenuItem("Çık", callback=lambda _s: None)])


def test_rebuilding_the_menu_does_not_grow_the_callback_registry():
    menu = rumps.rumps.Menu()
    build(menu)
    baseline = len(NSApp._ns_to_py_and_callback)
    for _ in range(200):
        forget_menu_items(menu)
        menu.clear()
        build(menu)
    assert len(NSApp._ns_to_py_and_callback) == baseline
    forget_menu_items(menu)
    menu.clear()


def test_without_the_helper_the_registry_leaks():
    """Documents the rumps behaviour the helper works around."""
    menu = rumps.rumps.Menu()
    build(menu)
    baseline = len(NSApp._ns_to_py_and_callback)
    menu.clear()
    build(menu)
    assert len(NSApp._ns_to_py_and_callback) > baseline
    forget_menu_items(menu)
    menu.clear()


def test_settings_tabs_selection_dismissal_and_empty_state(tmp_path):
    from datetime import datetime, timezone
    from AppKit import NSApplication
    from blackboard_sync.deleted import MissingOutput
    from blackboard_sync.menubar.model import AppModel
    from blackboard_sync.menubar.settings_form import FormValues, window_status
    from blackboard_sync.menubar.settings_window import SettingsWindow

    NSApplication.sharedApplication()
    model = AppModel(tmp_path, datetime.now(timezone.utc), configured=True)
    rows = [MissingOutput('one', 'term/course/one.pdf', 'term', 'course', 'one.pdf', 'term/course')]
    actions = []
    def action(name, keys):
        actions.append((name, keys))
        if name == 'dismiss':
            rows.clear()
    window = SettingsWindow(FormValues('https://bb.example.edu', str(tmp_path), True),
                            window_status(model), False, lambda v,l: None, lambda a: None,
                            lambda: None, on_missing=lambda: list(rows), on_deleted_action=action)
    try:
        assert [str(tab.label()) for tab in window.tabs.tabViewItems()] == ['Genel', 'Silinenler']
        window.tabs.selectTabViewItemAtIndex_(1)
        assert not window.refetch_button.isEnabled()
        button = window.checks['one']
        button.setState_(1)
        window.target.checked_(button)
        assert window.refetch_button.isEnabled()
        window.target.refetch_(None)
        assert actions == [('refetch', ['one'])]
        model.begin('sync')
        window.update_status(window_status(model))
        assert not window.refetch_button.isEnabled()
        assert not window.dismiss_button.isEnabled()
        model.busy = None
        window.update_status(window_status(model))
        window.target.dismiss_(None)
        assert actions[-1] == ('dismiss', ['one'])
        assert window.selection.rows == []
        assert 'Silinmiş dosya yok.' in [str(control.stringValue())
                                      for control in window.deleted_scroll.documentView().subviews()]
    finally:
        window.window.close()
