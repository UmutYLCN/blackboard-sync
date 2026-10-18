import pytest

rumps = pytest.importorskip("rumps")
pytest.importorskip("AppKit")

from rumps.rumps import NSApp

from blackboard_sync.menubar.app import forget_menu_items


def test_native_calendar_draws_days_and_routes_item_clicks(tmp_path):
    from datetime import datetime, timezone
    from blackboard_sync import deadlines
    from blackboard_sync.menubar.main_window_model import CALENDAR
    from blackboard_sync.state import State
    state = State(tmp_path / "cache.json")
    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    state.deadline_courses["course"] = {"name": "Ders adı", "items": [
        deadlines.column_deadline({"id": "grade", "name": "Ödev", "contentId": "content",
                                   "grading": {"due": "2026-10-14T10:00:00Z"}}, "course", "https://school.edu")]}
    page = [deadlines.calendar_page(state, tmp_path, now)]
    opened = []
    window, _, _ = make_window(tmp_path, on_deadlines=lambda: page[0], on_deadline=opened.append)
    window.select(CALENDAR)
    assert not window.pages[CALENDAR].isHidden()
    assert str(window.nav_items[CALENDAR][2].stringValue()) == "Calendar"
    assert window.deadline_targets == [page[0].days[0].rows[0].target]
    class Click:
        def tag(self):
            return 0
    window.target.openDeadline_(Click())
    assert opened == window.deadline_targets
    page[0] = deadlines.DeadlinePage()
    window.select(CALENDAR)
    assert window.deadline_targets == []
    assert window.calendar_scroll.documentView().frame().size.height > 0
    window.window.close()


@pytest.mark.parametrize("frozen", [False, True])
def test_idle_uses_the_logo_as_an_18_point_template(frozen, tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    import AppKit
    from blackboard_sync.menubar import app
    from blackboard_sync.menubar.model import Icon

    source = Path(app.__file__).resolve().parents[3] / "assets" / "menubar"
    if frozen:
        target = tmp_path / "assets" / "menubar"
        shutil.copytree(source, target)
        monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path), raising=False)
    else:
        monkeypatch.delattr(app.sys, "_MEIPASS", raising=False)

    # A valid logo must not ask for any SF Symbol.
    image_class = AppKit.NSImage
    class Images:
        alloc = image_class.alloc

        @staticmethod
        def imageWithSystemSymbolName_accessibilityDescription_(*args):
            pytest.fail("idle should use the bundled logo")

    monkeypatch.setattr(AppKit, "NSImage", Images)
    image = app.symbol_image(Icon.IDLE)
    assert image.isValid() and image.isTemplate()
    assert (image.size().width, image.size().height) == (18, 18)
    assert image.accessibilityDescription() == "Blackboard Sync"
    assert {(rep.pixelsWide(), rep.pixelsHigh()) for rep in image.representations()} == {(18, 18), (36, 36)}
    assert all((rep.size().width, rep.size().height) == (18, 18) for rep in image.representations())


@pytest.mark.parametrize("corrupt", [False, True])
def test_unloadable_logo_falls_back_to_graduationcap(corrupt, tmp_path, monkeypatch):
    import AppKit
    from blackboard_sync.menubar import app
    from blackboard_sync.menubar.model import Icon

    if corrupt:
        target = tmp_path / "assets" / "menubar" / "idle.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"not a PNG")
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path), raising=False)
    image_class = AppKit.NSImage
    calls = []
    class Images:
        alloc = image_class.alloc

        @staticmethod
        def imageWithSystemSymbolName_accessibilityDescription_(name, description):
            calls.append((name, description))
            return image_class.imageWithSystemSymbolName_accessibilityDescription_(name, description)

    monkeypatch.setattr(AppKit, "NSImage", Images)
    image = app.symbol_image(Icon.IDLE)
    assert calls == [("graduationcap", "Blackboard Sync")]
    assert image.isValid() and image.isTemplate()


@pytest.mark.parametrize("corrupt", [False, True])
def test_idle_still_uses_the_logo_if_the_retina_asset_cannot_load(corrupt, tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    from blackboard_sync.menubar import app
    from blackboard_sync.menubar.model import Icon

    assets = tmp_path / "assets" / "menubar"
    assets.mkdir(parents=True)
    source = Path(app.__file__).resolve().parents[3] / "assets" / "menubar" / "idle.png"
    shutil.copyfile(source, assets / "idle.png")
    if corrupt:
        (assets / "idle@2x.png").write_bytes(b"not a PNG")
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path), raising=False)
    image = app.symbol_image(Icon.IDLE)
    assert image.isValid() and image.isTemplate()
    assert [(rep.pixelsWide(), rep.pixelsHigh()) for rep in image.representations()] == [(18, 18)]


@pytest.mark.parametrize("icon, name, template", [
    ("SYNCING", "arrow.triangle.2.circlepath", True),
    ("EXPIRED", "person.crop.circle.badge.exclamationmark", False),
    ("ERROR", "exclamationmark.triangle", False),
])
def test_other_states_keep_their_sf_symbols(icon, name, template, monkeypatch):
    import AppKit
    from blackboard_sync.menubar import app
    from blackboard_sync.menubar.model import Icon

    image_class = AppKit.NSImage
    calls = []
    class Images:
        @staticmethod
        def alloc():
            pytest.fail("only idle should load an asset")

        @staticmethod
        def imageWithSystemSymbolName_accessibilityDescription_(name, description):
            calls.append((name, description))
            return image_class.imageWithSystemSymbolName_accessibilityDescription_(name, description)

    monkeypatch.setattr(AppKit, "NSImage", Images)
    state = getattr(Icon, icon)
    image = app.symbol_image(state)
    assert calls == [(name, app.DESCRIPTIONS[state])]
    assert image.isValid() and image.isTemplate() == template


def test_idle_uses_text_when_neither_logo_nor_symbol_can_load(config, tmp_path, monkeypatch):
    from types import SimpleNamespace
    import AppKit
    from blackboard_sync.menubar import app
    from blackboard_sync.menubar.model import Icon

    AppKit.NSApplication.sharedApplication()
    monkeypatch.setattr(rumps.Timer, "start", lambda self: None)
    monkeypatch.setattr(rumps.events.on_notification, "register", lambda callback: None)
    monkeypatch.setattr(rumps.events.on_wake, "register", lambda callback: None)
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path), raising=False)
    image_class = AppKit.NSImage
    class Images:
        alloc = image_class.alloc

        @staticmethod
        def imageWithSystemSymbolName_accessibilityDescription_(*args):
            return None

    monkeypatch.setattr(AppKit, "NSImage", Images)
    menu_app = app.build_app(config)
    images, titles = [], []
    menu_app._nsapp = SimpleNamespace(nsstatusitem=SimpleNamespace(
        setImage_=images.append, setTitle_=titles.append,
    ))
    menu_app._draw_icon(Icon.IDLE)
    assert images == [None]
    assert titles == ["BB"]


def build(menu, n_courses=8):
    courses = rumps.MenuItem("Courses")
    for i in range(n_courses):
        course = rumps.MenuItem(f"CSE{i}", callback=lambda _s: None)
        course.add(rumps.MenuItem("dosya", callback=lambda _s: None))
        courses.add(course)
    menu.update([rumps.MenuItem("durum"), rumps.separator, courses, rumps.MenuItem("Quit", callback=lambda _s: None)])


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


NOW = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)


def make_window(tmp_path, model=None, rows=(), **handlers):
    """A main window on fabricated state; nothing is put on screen."""
    from AppKit import NSApplication
    from blackboard_sync.menubar.main_window import MainWindow
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import AppModel
    from blackboard_sync.menubar.settings_form import FormValues

    NSApplication.sharedApplication()
    model = model or AppModel(tmp_path, NOW, configured=True)
    values = FormValues('https://bb.example.edu', str(tmp_path), True)
    handlers.setdefault('on_submit', lambda v, l: None)
    handlers.setdefault('on_action', lambda a: None)
    handlers.setdefault('on_close', lambda: None)
    handlers.setdefault('on_values', lambda: values)
    rows = list(rows)
    handlers.setdefault('on_courses', lambda: tuple(rows))
    window = MainWindow(values, main_status(model, NOW), **handlers)
    return window, model, rows


def signed_in(model):
    from blackboard_sync.menubar.model import RunOutcome

    model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada Student'}}
    model.last = RunOutcome('ok', finished_at=NOW)
    return model


def visible_page(window):
    return next(name for name, page in window.pages.items() if not page.isHidden())


def test_sidebar_switches_sections_and_baslangic_becomes_home(tmp_path):
    from blackboard_sync.courses import CourseRow
    from blackboard_sync.menubar.main_window_model import (ACTIVITY, ANNOUNCEMENTS, CALENDAR, COURSES, GENERAL, OVERVIEW,
                                                           main_status)
    from blackboard_sync.menubar.model import AppModel

    rows = [CourseRow('_1_1', 'CSE301', 'Algorithms', 'T', True), CourseRow('_2_1', 'MTH201', 'Linear', 'T', False)]
    window, model, _ = make_window(tmp_path, AppModel(tmp_path, NOW, configured=False), rows=rows)
    try:
        titles = [str(window.nav_items[s][2].stringValue()) for s in (OVERVIEW, ACTIVITY, ANNOUNCEMENTS, COURSES)]
        assert titles == ['Get started', 'Sync activity', 'Announcements', 'Courses']
        assert list(window.nav_items) == [OVERVIEW, ACTIVITY, ANNOUNCEMENTS, COURSES, CALENDAR]
        assert GENERAL not in window.nav_items  # Ayarlar is the gear at the top right
        assert str(window.nav_items[COURSES][3].stringValue()) == '1/2'
        assert visible_page(window) == 'start' and window.section == OVERVIEW
        assert str(window.start_button.title()) == 'Sign in'
        assert str(window.start_button.keyEquivalent()) == '\r'  # Return signs in
        assert all(view.isHidden() for view in window.topbar)  # Başlangıç signs in with its own form
        window.target.gear_(None)
        assert visible_page(window) == GENERAL and window.section == GENERAL
        assert str(window.start_button.keyEquivalent()) == ''  # not from a hidden section
        window.target.nav_(window.nav_items[COURSES][4])
        assert visible_page(window) == COURSES

        # Signed in: the first section becomes Home, on its own page.
        model.configured = True
        signed_in(model)
        window.update_status(main_status(model, NOW))
        window.select(OVERVIEW)
        assert visible_page(window) == OVERVIEW
        assert str(window.nav_items[OVERVIEW][2].stringValue()) == 'Home'
        window.target.nav_(window.nav_items[ACTIVITY][4])
        assert visible_page(window) == ACTIVITY
        window.target.nav_(window.nav_items[ANNOUNCEMENTS][4])
        assert visible_page(window) == ANNOUNCEMENTS
        window.select(OVERVIEW)
        # Duraklat / Devam et, Ayarlar and the account sit at the top right, the status in Home's card.
        assert not any(view.isHidden() for view in window.topbar)
        assert str(window.avatar_text.stringValue()) == 'AS'
        assert str(window.state_title.stringValue()) == 'Up to date'
        assert str(window.state_detail.stringValue()).startswith('Last synced: today ')
        assert window.scene_view.isHidden() and not window.state_icon.isHidden()
        # A sync shows its illustration in the card and keeps the time of the last one.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert str(window.state_title.stringValue()) == 'Syncing…'
        assert not window.scene_view.isHidden() and window.state_icon.isHidden()
        assert str(window.sync_button.title()) == 'Syncing…' and not window.sync_button.isEnabled()
    finally:
        window.window.close()


def test_home_buttons_recent_files_and_sign_in(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RecentItem

    actions, opened = [], []
    window, model, _ = make_window(tmp_path, on_action=actions.append, on_open=opened.append)
    try:
        signed_in(model).recent = [RecentItem('T/SWE305/Homework1.docx', 'SWE305', NOW.isoformat()),
                                   RecentItem('T/CSE301/week1.pdf', 'CSE301', NOW.isoformat())]
        window.update_status(main_status(model, NOW))
        assert str(window.recent_count.stringValue()) == '2 files'
        buttons = [v for v in window.recent_scroll.documentView().subviews()
                   if hasattr(v, 'action') and v.action() == 'openRecent:']
        assert [b.toolTip() for b in buttons] == ['Homework1.docx', 'week1.pdf']
        window.target.openRecent_(buttons[1])
        assert opened == ['T/CSE301/week1.pdf']
        window.target.sync_(None)
        window.target.folder_(None)
        assert actions == ['sync', 'folder']
        # "View all" opens Sync activity.
        window.target.showActivity_(None)
        assert window.section == 'activity'
        window.select('overview')
        # Expired: the card says so and offers signing in; Announcements lists it on top too.
        model.session = None
        model.session_expired = True
        window.update_status(main_status(model, NOW))
        assert str(window.state_title.stringValue()) == 'Sign-in needed'
        assert not window.home_action.isHidden() and str(window.home_action.title()) == 'Sign in'
        assert not window.sync_button.isEnabled()
        window.target.homeAction_(None)
        assert actions[-1] == 'login'
        assert [item.title for item in window.status.attention] == ['Session expired']
        window.target.attention_(type('B', (), {'tag': lambda self: 0})())
        assert actions[-1] == 'login'
    finally:
        window.window.close()


def test_pause_button_and_menu(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status

    actions = []
    window, model, _ = make_window(tmp_path, on_action=actions.append)
    try:
        signed_in(model)
        window.update_status(main_status(model, NOW))
        assert window.pause_button.isEnabled() and window.pause_button.toolTip() == 'Pause syncing'
        window.target.pause_(None)
        assert actions == ['pause']
        model.pause()
        window.update_status(main_status(model, NOW))
        assert window.pause_button.toolTip() == 'Resume syncing'
        assert str(window.state_title.stringValue()) == 'Paused'
        # Like Drive, the Paused card has no button of its own; the top bar's play button resumes.
        assert window.home_action.isHidden() and window.sync_button.isHidden()
        window.target.pause_(None)
        assert actions == ['pause', 'pause']
    finally:
        window.window.close()


def test_home_header_greets_and_the_card_buttons_are_pills(tmp_path):
    from datetime import timedelta, timezone

    from blackboard_sync import deadlines
    from blackboard_sync.menubar.main_window import HEADER, HOME_SUBTITLE_SHIFT, PILL_H, _pill_width, _PillButton
    from blackboard_sync.menubar.main_window_model import OVERVIEW, T_NAV_OVERVIEW, greeting, main_status

    window, model, _ = make_window(tmp_path)
    try:
        signed_in(model)
        row = deadlines.DeadlineRow('Homework', 'CSE303', NOW + timedelta(days=2), 'https://bb.example.edu/x')
        page = deadlines.DeadlinePage((deadlines.DeadlineDay(row.due.date(), 'x', False, (row,)),), '')
        window.show(OVERVIEW)

        # With due dates: the greeting and a line under it; the cards move down to make room.
        window.update_status(main_status(model, NOW, page, timezone.utc))
        assert str(window.overview_title.stringValue()) == greeting('Ada Student', NOW, timezone.utc)
        assert str(window.overview_subtitle.stringValue()) == '1 deadline this week'
        assert not window.overview_subtitle.isHidden()
        subtitle = window.overview_subtitle.frame()
        assert window.status_card.frame().origin.y == HEADER + HOME_SUBTITLE_SHIFT
        assert window.notify_card.frame().origin.y == HEADER + HOME_SUBTITLE_SHIFT
        assert subtitle.origin.y + subtitle.size.height <= window.status_card.frame().origin.y  # no overlap
        assert str(window.nav_items[OVERVIEW][2].stringValue()) == T_NAV_OVERVIEW  # the sidebar keeps "Home"

        # Without a page: the plain title, no line, the cards where they were.
        window.update_status(main_status(model, NOW))
        assert str(window.overview_title.stringValue()) == T_NAV_OVERVIEW
        assert window.overview_subtitle.isHidden()
        assert window.status_card.frame().origin.y == HEADER

        # "Sync now", the state's button and "View all" are one kind of pill, 36 pt high; the card's
        # buttons are gray and "View all" carries the accent color.
        for button in (window.sync_button, window.home_action, window.recent_all):
            assert isinstance(button, _PillButton)
        window.update_status(main_status(model, NOW))
        assert not window.sync_button.isHidden() and window.home_action.isHidden()
        assert window.sync_button.frame().size.height == PILL_H == window.recent_all.frame().size.height
        assert window.sync_button.frame().size.width == _pill_width(window.sync_button)
        assert not window.sync_button.fill.isEqual_(window.recent_all.fill)
        assert window.sync_button.fill.isEqual_(window.home_action.fill)
        # It stays inside the card and clear of the title it shares the row with.
        card_width = window.status_card.frame().size.width
        assert window.sync_button.frame().origin.x + window.sync_button.frame().size.width <= card_width
        assert window.state_title.frame().origin.x + window.state_title.frame().size.width <= \
            window.sync_button.frame().origin.x

        # Its title and enabled state follow the model, and the button fades while it is disabled.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert str(window.sync_button.title()) == 'Syncing…' and not window.sync_button.isEnabled()
        assert window.sync_button.alphaValue() < 1
        assert window.sync_button.frame().size.width == _pill_width(window.sync_button)
        model.busy = None
        window.update_status(main_status(model, NOW))
        assert window.sync_button.isEnabled() and window.sync_button.alphaValue() == 1
    finally:
        window.window.close()


def test_sync_activity_lists_files_with_size_and_status(tmp_path):
    from blackboard_sync.menubar.main_window_model import ACTIVITY, main_status
    from blackboard_sync.menubar.model import CourseChange, RunOutcome

    (tmp_path / 'University' / 'CSE301').mkdir(parents=True)
    (tmp_path / 'University' / 'CSE301' / 'week1.pdf').write_bytes(b'x' * 14_000)
    opened = []
    window, model, _ = make_window(tmp_path, on_open=opened.append)
    try:
        signed_in(model)
        model.begin('sync')
        model.finish_sync(RunOutcome('ok', finished_at=NOW, courses=[CourseChange('CSE301', 'CSE301', {}, [])],
                                     entries=[('CSE301', 'CSE301/week1.pdf', 'new_file'),
                                              ('CSE301', 'CSE301/note.md', 'new_note')]), NOW)
        window.update_status(main_status(model, NOW))
        window.select(ACTIVITY)
        rows = window.status.activity
        assert [(r.name, r.status, r.size) for r in rows] == [
            ('week1.pdf', 'Successfully downloaded', '14 KB'), ('note.md', 'Note saved', '—')]
        buttons = [v for v in window.activity_scroll.documentView().subviews()
                   if hasattr(v, 'action') and v.action() == 'openActivity:']
        assert [b.toolTip() for b in buttons] == ['week1.pdf', 'note.md']
        window.target.openActivity_(buttons[0])
        assert opened == ['CSE301/week1.pdf']
    finally:
        window.window.close()


def test_announcements_page_puts_what_needs_attention_above_the_announcements(tmp_path):
    from blackboard_sync.announcements import AnnouncementRow
    from blackboard_sync.menubar.main_window_model import ANNOUNCEMENTS, main_status

    rows = (AnnouncementRow('k1', 'CSE301', 'Sınav tarihi', '17.10.2026 10:00', 'Vize 3 Kasım.', 'C/a.md', 'https://x'),)
    opened = []
    window, model, _ = make_window(tmp_path, on_announcements=lambda: rows, on_open_announcement=opened.append)
    try:
        signed_in(model)
        window.update_status(main_status(model, NOW))
        window.select(ANNOUNCEMENTS)
        assert str(window.nav_items[ANNOUNCEMENTS][3].stringValue()) == ''
        # Home's card lists the newest announcement; a click opens it.
        assert window.home_announcements == rows
        window.target.openHomeAnnouncement_(type('B', (), {'tag': lambda self: 0})())
        assert opened == [rows[0]]
        model.session = None
        window.update_status(main_status(model, NOW))
        assert str(window.nav_items[ANNOUNCEMENTS][3].stringValue()) == '1'
        texts = [str(v.stringValue()) for v in window.announcements_scroll.documentView().subviews()
                 if hasattr(v, 'stringValue')]
        assert texts[0] == 'Needs your attention'
        window.target.showAnnouncements_(None)
        assert window.section == ANNOUNCEMENTS
    finally:
        window.window.close()


def test_recent_badges_and_viewport_seen_tracking(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import AppKit
    from Foundation import NSMakeRect
    from blackboard_sync.menubar import main_window as module
    from blackboard_sync.menubar.main_window_model import GENERAL, OVERVIEW, main_status
    from blackboard_sync.menubar.model import AppModel, RecentItem, RecentSeen
    from .test_recent_seen import Clock

    clock, saved = Clock(), []
    model = signed_in(AppModel(tmp_path, NOW, recent_seen=RecentSeen(clock=clock)))
    model.recent = [RecentItem('a.pdf', 'CSE303', NOW.isoformat()),
                    RecentItem('b.pdf', 'CSE303', NOW.isoformat())]
    window, _, _ = make_window(tmp_path, model=model, recent_seen=model.recent_seen,
                               on_seen=lambda: saved.append(True),
                               on_section=lambda section: window.update_status(main_status(model, NOW)))
    native_window, native_scroll = window.window, window.recent_scroll
    try:
        pills = [v for v in native_scroll.documentView().subviews() if isinstance(v, AppKit.NSBox) and v.contentView() is not None
                 and any(hasattr(label, 'stringValue') and label.stringValue() == 'NEW'
                         for label in v.contentView().subviews())]
        assert len(pills) == 2
        window.state.show()
        window._show_section()
        window.window = SimpleNamespace(isVisible=lambda: True, isMiniaturized=lambda: False,
                                        isKeyWindow=lambda: True)
        window.recent_scroll = SimpleNamespace(documentVisibleRect=lambda: NSMakeRect(0, 0, 500, module.ROW_HEIGHT))
        monkeypatch.setattr(module, 'NSApp', SimpleNamespace(isActive=lambda: True))
        for _ in range(13):
            window.observe_recent()
            clock.seconds += 0.25
        assert saved == [True]
        assert model.recent_seen.seen == {'a.pdf': model.recent[0].at}
        window.window, window.recent_scroll = native_window, native_scroll
        window.update_status(main_status(model, NOW))
        assert all(r.is_new for r in window.status.recent)
        window.select(GENERAL)
        window.select(OVERVIEW)
        assert [r.is_new for r in window.status.recent] == [False, True]
        window.target.windowDidMiniaturize_(None)
        assert model.recent_seen.snapshot is None
        window.target.windowDidDeminiaturize_(None)
        assert [r.is_new for r in window.status.recent] == [False, True]
    finally:
        window.window, window.recent_scroll = native_window, native_scroll
        native_window.close()


@pytest.mark.parametrize('appearance', ['NSAppearanceNameAqua', 'NSAppearanceNameDarkAqua'])
def test_home_update_banner_visibility_action_and_layout(tmp_path, appearance):
    import AppKit
    from blackboard_sync.menubar.main_window_model import GENERAL, OVERVIEW, main_status
    from blackboard_sync.menubar.main_window import GAP, HEADER, PAD, UPDATE_BANNER_HEIGHT
    from blackboard_sync.menubar.model import RecentItem
    from blackboard_sync.updater import Release

    actions = []
    window, model, _ = make_window(tmp_path, on_action=actions.append)
    try:
        window.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(getattr(AppKit, appearance)))
        banners = (window.start_update_banner, window.overview_update_banner)
        assert all(box.isHidden() for box, _, _ in banners)
        assert window.start_scroll.frame().origin.y == 0
        model.updates.available = Release('9.9.9', 'https://example.com', 'installer', 'https://example.com/installer')
        window.update_status(main_status(model, NOW))
        for box, title, button in banners:
            assert not box.isHidden()
            assert str(title.stringValue()) == 'Blackboard Sync 9.9.9 is ready'
            assert str(button.title()) == 'Update' and button.isEnabled()
            assert button.action() == window.update_button.action() == 'update:'
            button.performClick_(None)
        window.update_button.performClick_(None)
        assert actions == ['update', 'update', 'update']
        assert window.start_scroll.frame().origin.y == PAD + UPDATE_BANNER_HEIGHT + GAP
        signed_in(model).recent = [RecentItem('T/C/file.pdf', 'C', NOW.isoformat())]
        window.update_status(main_status(model, NOW))
        assert visible_page(window) == OVERVIEW
        box = window.overview_update_banner[0]
        assert box.frame().origin.y == HEADER
        # Home's two columns start under the banner; the last files keep their own scroll area.
        assert window.status_card.frame().origin.y == box.frame().origin.y + UPDATE_BANNER_HEIGHT + GAP
        assert window.notify_card.frame().origin.y == window.status_card.frame().origin.y
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.scene_view.isHidden()
        assert window.status_card.frame().origin.y == box.frame().origin.y + UPDATE_BANNER_HEIGHT + GAP
        model.note = 'Checking for new content…'
        window.window.setContentSize_((960, 378))  # 400-point window including its title bar
        window.update_status(main_status(model, NOW))
        assert box.frame().origin.y + box.frame().size.height < window.status_card.frame().origin.y
        window.window.setContentSize_((960, 560))
        window.update_status(main_status(model, NOW))
        frame = window.status_card.frame()
        assert frame.origin.y + frame.size.height <= window.pages[OVERVIEW].frame().size.height - PAD
        model.busy = None
        model.updates.begin('download')
        window.update_status(main_status(model, NOW))
        assert all(str(button.title()) == 'Downloading…' and not button.isEnabled() for _, _, button in banners)
        window.select(GENERAL)
        assert visible_page(window) == GENERAL and not window.update_button.isEnabled()
        model.updates.finish_download()
        model.updates.available = None
        model.note = ''
        window.update_status(main_status(model, NOW))
        assert all(box.isHidden() for box, _, _ in banners)
        assert window.status_card.frame().origin.y == HEADER
        assert window.start_scroll.frame().origin.y == 0
    finally:
        window.window.close()


def test_a_running_sync_shows_the_illustration_and_it_stops_with_the_sync(tmp_path, monkeypatch):
    from blackboard_sync.menubar import sync_scene_view
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RecentItem, RunOutcome

    monkeypatch.setattr(sync_scene_view, 'reduce_motion', lambda: False)  # CI machines may have it on
    window, model, _ = make_window(tmp_path)
    try:
        model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada Student'}}
        window.state.open = True  # as if shown; nothing is put on screen
        window.update_status(main_status(model, NOW))
        assert window.scene_view.isHidden() and not window.state_icon.isHidden()
        assert not window.scene_view.animating and not window.recent_scroll.isHidden()

        # The first sync: the illustration takes the symbol's place in the status card.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.scene_view.isHidden() and window.state_icon.isHidden()
        assert str(window.state_detail.stringValue()) == 'Downloading your files for the first time…'
        assert window.scene_view.animating and not window.recent_scroll.isHidden()
        # It keeps one timer across refreshes.
        timer = window.scene_view.timer
        window.update_status(main_status(model, NOW))
        assert window.scene_view.timer is timer

        model.finish_sync(RunOutcome('ok', finished_at=NOW), NOW)
        model.recent = [RecentItem('T/SWE305/Homework1.docx', 'SWE305', NOW.isoformat())]
        window.update_status(main_status(model, NOW))
        assert window.scene_view.isHidden() and not window.scene_view.animating
        assert not window.state_icon.isHidden()

        # A later sync: the same illustration, and the list stays in view.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.scene_view.isHidden() and window.scene_view.animating
        assert str(window.state_detail.stringValue()) == 'Checking for new content…'
        assert not window.recent_scroll.isHidden()
        # Only while Home is in view: on another page the motion stops, and returns with Home.
        window.select('activity')
        assert not window.scene_view.animating
        window.select('overview')
        assert window.scene_view.animating
        # Closing the window stops the motion; the sync goes on.
        window.closed()
        assert not window.scene_view.animating and model.busy == 'sync'
    finally:
        window.window.close()


def test_reduce_motion_shows_the_still_illustration(tmp_path, monkeypatch):
    from blackboard_sync.menubar import sync_scene_view
    from blackboard_sync.menubar.main_window_model import main_status

    monkeypatch.setattr(sync_scene_view, 'reduce_motion', lambda: True)
    window, model, _ = make_window(tmp_path)
    try:
        model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada Student'}}
        model.begin('sync')
        window.state.open = True
        window.update_status(main_status(model, NOW))
        assert not window.scene_view.isHidden()
        assert window.scene_view.still and not window.scene_view.animating
    finally:
        window.window.close()


def test_a_note_shows_in_the_status_card_and_the_account_menu_offers_sign_in(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RunOutcome

    window, model, _ = make_window(tmp_path)
    try:
        signed_in(model)
        window.update_status(main_status(model, NOW))
        assert window.account_message.isHidden()
        model.last = RunOutcome('error', message='Blackboard\'a ulaşılamadı', finished_at=NOW)
        window.update_status(main_status(model, NOW))
        assert not window.account_message.isHidden()
        assert str(window.account_message.stringValue()) == 'Sync did not finish: Blackboard\'a ulaşılamadı'
        assert str(window.state_title.stringValue()) == 'Sync did not finish'
        model.session, model.session_expired = None, True
        window.update_status(main_status(model, NOW))
        assert str(window.home_action.title()) == 'Sign in' and not window.home_action.isHidden()
        assert window.status.form.account_title == 'Sign in'  # what the account menu offers
        assert str(window.avatar_text.stringValue()) == '!'
    finally:
        window.window.close()


def test_genel_bar_appears_only_after_a_change_and_saving_keeps_the_window_open(tmp_path):
    from blackboard_sync.menubar.settings_form import FormValues

    submitted, closed = [], []
    saved = [FormValues('https://bb.example.edu', str(tmp_path), True)]

    def submit(values, login):
        submitted.append((values, login))
        if values.base_url == 'http://bad':
            return 'Geçerli bir adres yazın.', 'base_url'
        saved.append(values)
        return None

    window, model, _ = make_window(tmp_path, on_submit=submit, on_close=lambda: closed.append(True),
                                   on_values=lambda: saved[-1])
    try:
        assert window.button_bar.isHidden()
        assert str(window.cancel_button.keyEquivalent()) == ''
        window.interval_popup.selectItemWithTitle_('Every 3 hours')
        window.target.changed_(window.interval_popup)
        assert not window.button_bar.isHidden()
        assert str(window.error_label.stringValue()) == 'Unsaved changes'
        assert [str(b.title()) for b in (window.cancel_button, window.save_button)] == ['Cancel', 'Save']
        assert str(window.cancel_button.keyEquivalent()) == '\x1b'
        window.target.cancel_(None)  # Vazgeç: back to what is saved
        assert window.button_bar.isHidden() and window.values().sync_interval_minutes == 60

        # Language: English and Türkçe, each named in itself; picking one is an edit like any other.
        assert [str(t) for t in window.language_popup.itemTitles()] == ['English', 'Türkçe']
        assert window.values().language == 'en'
        window.language_popup.selectItemWithTitle_('Türkçe')
        window.target.changed_(window.language_popup)
        assert not window.button_bar.isHidden() and window.values().language == 'tr'
        window.target.cancel_(None)
        assert str(window.language_popup.titleOfSelectedItem()) == 'English'

        # Başlangıç and Genel edit the same school address.
        window.start_url.setStringValue_('https://new.example.edu')
        window.changed(window.start_url)
        assert str(window.url_field.stringValue()) == 'https://new.example.edu'
        assert not window.button_bar.isHidden()
        window.target.save_(None)
        assert submitted[-1] == (window.values(), False)
        assert window.button_bar.isHidden() and window.saved.base_url == 'https://new.example.edu'
        assert closed == [] and window.window.delegate() is window.target

        # A failed save keeps the edit and says why.
        window.url_field.setStringValue_('http://bad')
        window.changed(window.url_field)
        window.target.save_(None)
        assert not window.button_bar.isHidden()
        assert str(window.error_label.stringValue()) == 'Geçerli bir adres yazın.'
        assert str(window.url_field.stringValue()) == 'http://bad'

        # Closing drops the unsaved edit; the app is told, nothing else stops.
        window.state.show()
        window.closed()
        assert closed == [True] and not window.state.open
        assert str(window.url_field.stringValue()) == 'https://new.example.edu'
        assert window.button_bar.isHidden()
    finally:
        window.window.close()


def test_baslangic_signs_in_with_the_form(tmp_path):
    from blackboard_sync.menubar.model import AppModel

    submitted = []
    window, _, _ = make_window(tmp_path, AppModel(tmp_path, NOW, configured=False),
                               on_submit=lambda v, l: submitted.append((v, l)))
    try:
        window.start_dest.setStringValue_('~/Belgeler')
        window.changed(window.start_dest)
        window.start_autostart.setState_(0)
        window.target.changed_(window.start_autostart)
        assert str(window.dest_field.stringValue()) == '~/Belgeler' and not window.autostart.state()
        window.target.start_(None)
        values, login = submitted[-1]
        assert login is True and values.dest == '~/Belgeler' and values.autostart is False
    finally:
        window.window.close()


def test_dersler_lists_courses_with_a_checkbox_and_saves_a_change(tmp_path):
    from blackboard_sync import courses
    from blackboard_sync.courses import CourseRow
    from blackboard_sync.menubar.main_window_model import COURSES

    rows = [CourseRow('_1_1', 'CSE301', 'Algorithms', 'T', True), CourseRow('_2_1', 'MTH201', 'Linear', 'T', True)]
    toggles = []

    def toggle(course_id, enabled):
        toggles.append((course_id, enabled))
        rows[:] = [CourseRow(r.id, r.code, r.title, r.term, enabled if r.id == course_id else r.enabled) for r in rows]

    window, model, _ = make_window(tmp_path, on_course_toggle=toggle)
    window.on_courses = lambda: tuple(rows)
    try:
        window.select(COURSES)
        labels = [str(v.stringValue()) for v in window.pages[COURSES].subviews() if hasattr(v, 'stringValue')]
        assert courses.T_HINT in labels and courses.T_UNTICK_HINT in labels
        document = window.courses_scroll.documentView()
        texts = [str(v.stringValue()) for v in document.subviews() if hasattr(v, 'stringValue')]
        assert 'CSE301 Algorithms' in texts and 'T · syncing' in texts
        boxes = [v for v in document.subviews() if hasattr(v, 'action') and str(v.action() or '') == 'courseToggled:']
        assert [int(b.state()) for b in boxes] == [1, 1] and str(window.nav_items[COURSES][3].stringValue()) == ''
        boxes[1].setState_(0)
        window.target.courseToggled_(boxes[1])
        assert toggles == [('_2_1', False)]
        assert str(window.nav_items[COURSES][3].stringValue()) == '1/2'
        texts = [str(v.stringValue()) for v in window.courses_scroll.documentView().subviews()
                 if hasattr(v, 'stringValue')]
        assert 'T · not syncing' in texts  # drawn again with the new choice
        rows.clear()
        window.refresh_courses()
        assert courses.T_EMPTY in [str(v.stringValue()) for v in window.courses_scroll.documentView().subviews()
                                   if hasattr(v, 'stringValue')]
    finally:
        window.window.close()


def settings_texts(window):
    """Every text on the Settings page as (top, text), from the top down."""
    found = []

    def walk(view, top):
        for child in view.subviews():
            y = top + child.frame().origin.y
            if hasattr(child, 'stringValue'):
                found.append((y, str(child.stringValue())))
            walk(child.contentView() if hasattr(child, 'contentView') and child.contentView() is not None
                 and hasattr(child, 'boxType') else child, y)

    walk(window.form_scroll.documentView(), 0)
    return sorted((entry for entry in found if entry[1]), key=lambda entry: entry[0])


def test_settings_page_is_sections_of_rows(tmp_path):
    from AppKit import NSAppearance, NSBoxSeparator, NSSwitch, NSButton, NSPopUpButton, NSTextField
    from blackboard_sync.menubar.main_window import INNER, SETTINGS_PAD
    from blackboard_sync.menubar.main_window_model import GENERAL, main_status
    from blackboard_sync.menubar.settings_form import SECTION_CALENDAR, SECTIONS, settings_sections

    window, model, _ = make_window(tmp_path)
    try:
        window.select(GENERAL)
        signed_in(model)
        window.update_status(main_status(model, NOW))
        texts = settings_texts(window)
        by_text = {text: top for top, text in texts}

        # Sections top to bottom, each with its rows' titles under its own title; no Calendar yet.
        expected = []
        for section in settings_sections():
            expected.append(section.title)
            expected += [row.title for row in section.rows if row.title]
        order = [text for _, text in texts if text in expected]
        assert order == expected
        assert SECTION_CALENDAR not in SECTIONS and 'Calendar' not in by_text
        above = [t for t in expected if t not in ('Danger zone', 'Uninstall Blackboard Sync')]
        assert max(by_text[t] for t in above) < by_text['Danger zone'] < by_text['Uninstall Blackboard Sync']  # last

        # The right controls for the right fields.
        assert isinstance(window.autostart, NSSwitch) and isinstance(window.check_updates, NSSwitch)
        assert isinstance(window.interval_popup, NSPopUpButton) and isinstance(window.language_popup, NSPopUpButton)
        assert isinstance(window.url_field, NSTextField) and isinstance(window.dest_field, NSTextField)
        assert str(window.account_label.stringValue()) == 'Signed in as Ada Student'
        assert str(window.account_button.title()) == 'Sign out' and str(window.version_label.stringValue()).startswith('Version ')

        # Every row: the control at the card's right edge, clear of the row's text.
        edge = INNER - SETTINGS_PAD
        for key in ('base_url', 'account', 'interval', 'autostart', 'language', 'past_term', 'past_download',
                    'check_updates', 'update', 'uninstall'):
            row = window.settings_rows[key]
            frame = row.control.frame()
            assert round(frame.origin.x + frame.size.width) == edge, key
            if key != 'account':  # its title is the live "Signed in as …"
                assert row.title.frame().origin.x + row.title.frame().size.width <= frame.origin.x, key
        # The folder row has its Choose… button at the edge and the field before it.
        field = window.dest_field.frame()
        choose = next(v for v in window.dest_field.superview().subviews()
                      if isinstance(v, NSButton) and str(v.title()) == 'Choose…')
        assert round(choose.frame().origin.x + choose.frame().size.width) == edge
        assert field.origin.x + field.size.width < choose.frame().origin.x

        # Hairlines between the rows of a card, none around a single row.
        def lines(card):
            return sum(1 for v in card.subviews() if hasattr(v, 'boxType') and v.boxType() == NSBoxSeparator)
        cards = {key: window.settings_rows[key].control.superview() for key in ('base_url', 'interval', 'dest')}
        assert lines(cards['base_url']) == 1 and lines(cards['interval']) == 2 and lines(cards['dest']) == 0

        # Accessibility: controls are named after their rows.
        assert str(window.autostart.accessibilityLabel()) == 'Start when the computer starts'
        assert str(window.interval_popup.accessibilityLabel()) == 'Automatic sync'
        assert str(window.check_updates.accessibilityLabel()) == 'Check for updates automatically'
        assert str(window.url_field.accessibilityLabel()) == "Your school's Blackboard address"
        assert 'Danger zone' in by_text and str(window.uninstall_button.attributedTitle().string()) == 'Uninstall app…'

        # Both appearances draw.
        for name in ('NSAppearanceNameAqua', 'NSAppearanceNameDarkAqua'):
            window.window.setAppearance_(NSAppearance.appearanceNamed_(name))
            doc = window.form_scroll.documentView()
            rep = doc.bitmapImageRepForCachingDisplayInRect_(doc.bounds())
            doc.cacheDisplayInRect_toBitmapImageRep_(doc.bounds(), rep)
            assert rep.pixelsHigh() > 0
        assert window.form_height == window.form_scroll.documentView().frame().size.height
    finally:
        window.window.close()


def test_settings_switches_keep_the_save_and_cancel_semantics(tmp_path):
    from blackboard_sync.menubar.main_window_model import GENERAL

    submitted = []
    window, model, _ = make_window(tmp_path, on_submit=lambda values, login: submitted.append(values) or None)
    try:
        window.select(GENERAL)
        assert window.button_bar.isHidden() and window.autostart.state() == 1
        window.autostart.setState_(0)
        window.target.changed_(window.autostart)  # what clicking the switch sends
        assert not window.button_bar.isHidden() and window.values().autostart is False
        # The Get started form's check box is the same draft.
        assert window.start_autostart.state() == 0
        window.target.cancel_(None)
        assert window.button_bar.isHidden() and window.autostart.state() == 1 and window.start_autostart.state() == 1
        window.check_updates.setState_(0)
        window.target.changed_(window.check_updates)
        window.target.save_(None)
        assert submitted[-1].check_updates is False and submitted[-1].autostart is True
        assert window.button_bar.isHidden()  # saved: back to nothing unsaved
    finally:
        window.window.close()


def test_settings_rows_follow_the_app_state(tmp_path):
    from blackboard_sync.menubar.main_window_model import GENERAL, main_status

    window, model, _ = make_window(tmp_path)
    try:
        window.select(GENERAL)
        window.update_status(main_status(model, NOW))
        assert str(window.account_button.title()) == 'Sign in' and window.past_scene.isHidden()
        assert str(window.past_label.stringValue()) == 'Sign in to see past terms.'
        signed_in(model)
        window.update_status(main_status(model, NOW))
        assert str(window.account_button.title()) == 'Sign out' and window.account_button.isEnabled()
        assert window.uninstall_button.isEnabled()
        model.begin('sync')  # the job slot is taken: sign out, update and uninstall wait
        window.update_status(main_status(model, NOW))
        assert not window.account_button.isEnabled() and not window.uninstall_button.isEnabled()
        model.busy = None

        # A past term downloading: the list is locked, the button says so and the papers fly.
        from blackboard_sync.menubar.model import RunOutcome
        model.finish_past_terms(['2025-2026 Bahar'], RunOutcome('ok'))
        window.update_status(main_status(model, NOW))
        assert window.past_popup.isEnabled() and window.past_button.isEnabled() and window.past_scene.isHidden()
        assert model.select_past_term('2025-2026 Bahar')
        model.begin('past_term')
        window.update_status(main_status(model, NOW))
        assert str(window.past_button.title()) == 'Downloading…' and not window.past_popup.isEnabled()
        assert not window.past_scene.isHidden() and 'Downloading' in str(window.past_label.stringValue())
    finally:
        window.window.close()


def test_genel_past_terms_section_and_uninstall_button(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RunOutcome

    actions, downloads = [], []
    window, model, _ = make_window(tmp_path, on_action=actions.append, on_past_term=downloads.append)
    try:
        labels = [text for _, text in settings_texts(window)]
        sections = [label for label in labels if label in ('Account', 'Folder', 'Past terms', 'Sync', 'Updates',
                                                           'Danger zone')]
        assert sections == ['Account', 'Sync', 'Folder', 'Past terms', 'Updates', 'Danger zone']
        assert 'A past term is downloaded once and not updated.' in labels
        assert str(window.past_button.title()) == 'Download past term'
        assert str(window.past_label.stringValue()) == 'Sign in to see past terms.'
        assert not window.past_button.isEnabled() and not window.past_popup.isEnabled()
        assert str(window.uninstall_button.title()) == 'Uninstall app…'
        window.target.uninstall_(None)
        assert actions == ['uninstall']

        model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada'}}
        window.update_status(main_status(model, NOW))
        assert str(window.past_label.stringValue()) == 'Loading past terms…'
        model.finish_past_terms(['2025-2026 Bahar', '2025-2026 Güz'], RunOutcome('ok'))
        window.update_status(main_status(model, NOW))
        assert [str(t) for t in window.past_popup.itemTitles()] == ['2025-2026 Bahar', '2025-2026 Güz']
        window.past_popup.selectItemWithTitle_('2025-2026 Güz')
        window.update_status(main_status(model, NOW))
        assert str(window.past_popup.titleOfSelectedItem()) == '2025-2026 Güz'
        window.target.pastTerm_(None)
        assert downloads == ['2025-2026 Güz']
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.past_button.isEnabled() and not window.uninstall_button.isEnabled()
        window.target.pastTerm_(None)
        assert downloads == ['2025-2026 Güz']
        window.target.account_(None)  # signed in: "Sign out"
        assert actions[-1] == 'logout'
    finally:
        window.window.close()


def test_main_window_fits_a_short_screen_and_scrolls_with_the_bar_in_view(tmp_path):
    from types import SimpleNamespace
    from AppKit import NSScrollView, NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable
    from Foundation import NSMakeRect
    from blackboard_sync.menubar.main_window import HEIGHT, WIDTH
    from blackboard_sync.menubar.main_window_model import GENERAL
    from blackboard_sync.menubar.settings_form import SCREEN_MARGIN

    window, _, _ = make_window(tmp_path)

    def screen(height):  # visibleFrame: the screen without the menu bar and Dock
        return SimpleNamespace(visibleFrame=lambda: NSMakeRect(0, 0, 1440, height))

    try:
        mask = window.window.styleMask()
        assert mask & NSWindowStyleMaskResizable and mask & NSWindowStyleMaskMiniaturizable
        assert str(window.window.title()) == 'Blackboard Sync'
        assert isinstance(window.form_scroll, NSScrollView)
        window.select(GENERAL)
        window.interval_popup.selectItemWithTitle_('Only manually')
        window.changed(window.interval_popup)
        # A 13-inch MacBook (about 640 points free): the window fits and Genel scrolls.
        window.fit_to_screen(screen(640))
        assert window.window.frame().size.height == 640 - SCREEN_MARGIN
        page = window.pages[GENERAL].frame().size.height
        form = window.form_scroll.documentView().frame().size.height
        assert window.form_scroll.contentView().frame().size.height < form
        bar = window.button_bar.frame()
        assert bar.origin.y + bar.size.height == page  # at the bottom, in view
        assert window.form_scroll.frame().origin.y + window.form_scroll.frame().size.height == bar.origin.y
        minimum = window.window.contentMinSize()
        assert minimum.width == window.window.contentMaxSize().width == WIDTH
        # A big screen opens at the full size.
        window.fit_to_screen(screen(1400))
        assert window.window.contentView().frame().size.height == HEIGHT
    finally:
        window.window.close()


@pytest.fixture
def menu_app(config, monkeypatch):
    """The real menu bar app object, without its run loop, timers or a real main window."""
    import AppKit
    from blackboard_sync.menubar import app, main_window

    AppKit.NSApplication.sharedApplication()
    monkeypatch.setattr(rumps.Timer, "start", lambda self: None)
    monkeypatch.setattr(rumps.events.on_notification, "register", lambda callback: None)
    monkeypatch.setattr(rumps.events.on_wake, "register", lambda callback: None)
    docks = []
    monkeypatch.setattr(app, "set_dock_icon", docks.append)

    class Window:
        built = []

        def __init__(self, values, status, **handlers):
            from blackboard_sync.menubar.main_window_model import WindowState

            # Creating the NSWindow as an accessory assigns it the wrong Space
            # role. Every entry point must promote the app before construction.
            assert docks == [True]
            self.state, self.handlers, self.shown, self.statuses = WindowState(), handlers, [], []
            Window.built.append(self)

        @property
        def section(self):
            return self.state.section

        def show(self, section=None):
            self.shown.append(section)
            self.state.show(section)

        def update_status(self, status):
            self.statuses.append(status)

        def close(self):
            self.state.closed()
            self.handlers["on_close"]()

    monkeypatch.setattr(main_window, "MainWindow", Window)
    menu_app = app.build_app(config)
    menu_app.docks = docks
    menu_app.windows = Window.built
    return menu_app


@pytest.mark.parametrize('exists', [True, False])
def test_open_recent_marks_file_seen_and_persists_immediately(menu_app, monkeypatch, exists):
    from blackboard_sync.menubar import app, jobs
    from blackboard_sync.menubar.model import RecentItem

    item = RecentItem('course/a.pdf', 'CSE303', NOW.isoformat())
    menu_app.model.recent = [item]
    menu_app.model.recent_seen.show()
    target = menu_app.model.root / item.path
    target.parent.mkdir(parents=True)
    if exists:
        target.write_text('file')
    opened = []
    monkeypatch.setattr(app, 'open_path', opened.append)
    monkeypatch.setattr(menu_app, 'refresh', lambda: None)
    menu_app.open_recent(item.path)
    assert opened == [target if exists else target.parent]
    assert menu_app.model.recent_seen.is_new(item.path, item.at, NOW) is not exists
    if exists:
        restored = jobs.load_model(menu_app.config, NOW, autostart=False)
        assert not restored.recent_seen.is_new(item.path, item.at, NOW)


def test_reopening_the_app_shows_one_main_window_with_the_dock_icon(menu_app):
    from rumps.rumps import NSApp as Delegate

    delegate = Delegate.alloc().init()
    # Finder, Launchpad or the Dock opened the running app: handled, not AppKit's default.
    assert delegate.applicationShouldHandleReopen_hasVisibleWindows_(None, False) is False
    assert len(menu_app.windows) == 1 and menu_app.windows[0].shown == [None]
    assert menu_app.docks == [True]
    menu_app._requests.showWindow_(None)  # a second start, from the other process
    assert len(menu_app.windows) == 1 and menu_app.windows[0].shown == [None, None]


def test_ayarlar_opens_genel_and_closing_keeps_the_app_running(menu_app):
    from blackboard_sync.menubar.main_window_model import GENERAL

    menu_app.refresh()
    assert menu_app.windows == []  # nothing drawn before the window exists
    menu_app.open_settings()
    window = menu_app.windows[0]
    assert window.shown == [GENERAL] and menu_app.docks == [True]
    menu_app.refresh()
    assert window.statuses  # the open window follows the app
    assert menu_app.past_terms_wanted() is False  # not signed in: nothing to look up
    menu_app.model.configured = True
    menu_app.model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada'}}
    assert menu_app.past_terms_wanted()  # Genel lists them
    window.state.select('overview')
    assert not menu_app.past_terms_wanted()  # opening the app does not ask the school
    window.close()
    assert menu_app.docks == [True, False]  # the Dock icon leaves with the window
    count = len(window.statuses)
    menu_app.refresh()
    assert len(window.statuses) == count  # a closed window is not redrawn
    assert menu_app._timer is not None and not menu_app._uninstalling


def test_window_buttons_reach_the_app_actions(menu_app, monkeypatch):
    calls = []
    for name in ("start_sync", "open_school_folder", "start_login", "logout", "start_update_check"):
        monkeypatch.setattr(menu_app, name, lambda *args, name=name: calls.append(name))
    for action in ("sync", "folder", "login", "logout", "check_updates"):
        menu_app.window_action(action)
    assert calls == ["start_sync", "open_school_folder", "start_login", "logout", "start_update_check"]


def test_dock_icon_switches_only_when_needed(monkeypatch):
    import AppKit
    from types import SimpleNamespace
    from blackboard_sync.menubar import app

    calls = []
    application = SimpleNamespace(activationPolicy=lambda: AppKit.NSApplicationActivationPolicyAccessory,
                                  setActivationPolicy_=lambda policy: calls.append(policy) or True)
    monkeypatch.setattr(AppKit, "NSApplication", SimpleNamespace(sharedApplication=lambda: application))
    app.set_dock_icon(False)
    assert calls == []
    app.set_dock_icon(True)
    assert calls == [AppKit.NSApplicationActivationPolicyRegular]


def test_main_menu_quits_edits_and_closes_the_window():
    from blackboard_sync.menubar import app

    main, window_menu = app.build_main_menu()
    menus = {str(item.title()): item.submenu() for item in main.itemArray()}
    assert list(menus) == ["Blackboard Sync", "Edit", "Window"]
    actions = {str(item.title()): (item.action(), str(item.keyEquivalent()))
               for menu in menus.values() for item in menu.itemArray() if not item.isSeparatorItem()}
    assert actions["Quit Blackboard Sync"] == ("terminate:", "q")
    assert actions["Paste"] == ("paste:", "v")
    assert actions["Close"] == ("performClose:", "w")
    assert actions["Minimize"] == ("performMiniaturize:", "m")
    assert window_menu is menus["Window"]


def test_pause_stops_a_running_sync_and_resume_syncs_again(menu_app, monkeypatch):
    from blackboard_sync.menubar import jobs

    stopped, ticks = [], []
    monkeypatch.setattr(jobs, 'stop_sync', lambda: stopped.append(True) or True)
    monkeypatch.setattr(menu_app, 'refresh', lambda: None)
    monkeypatch.setattr(menu_app, 'tick', lambda *args: ticks.append(True))
    menu_app.model.configured = True
    menu_app.toggle_pause()  # idle: nothing to stop
    assert menu_app.model.paused and stopped == []
    assert jobs.load_model(menu_app.config, NOW, autostart=False).paused  # saved at once
    menu_app.toggle_pause()  # resume: a check runs right away
    assert not menu_app.model.paused and ticks == [True]
    assert menu_app.model.begin('sync')
    menu_app.toggle_pause()  # a running sync is ended
    assert menu_app.model.paused and stopped == [True]
