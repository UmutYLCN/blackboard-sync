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
