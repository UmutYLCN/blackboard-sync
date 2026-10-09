import pytest

rumps = pytest.importorskip("rumps")
pytest.importorskip("AppKit")

from rumps.rumps import NSApp

from blackboard_sync.menubar.app import forget_menu_items


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


def test_settings_past_terms_section_and_uninstall_button(tmp_path):
    from datetime import datetime, timezone
    from AppKit import NSApplication
    from blackboard_sync.menubar.model import AppModel, RunOutcome
    from blackboard_sync.menubar.settings_form import FormValues, window_status
    from blackboard_sync.menubar.settings_window import SettingsWindow

    NSApplication.sharedApplication()
    model = AppModel(tmp_path, datetime.now(timezone.utc), configured=True)
    actions, downloads = [], []
    window = SettingsWindow(FormValues('https://bb.example.edu', str(tmp_path), True),
                            window_status(model), False, lambda v, l: None, actions.append,
                            lambda: None, on_past_term=downloads.append)
    try:
        labels = [str(view.stringValue()) for view in window.form_scroll.documentView().subviews()
                  if hasattr(view, 'stringValue')]
        sections = [label for label in labels if label in ('Hesap', 'Klasör', 'Eski dönemler', 'Genel', 'Güncellemeler')]
        assert sections == ['Hesap', 'Klasör', 'Eski dönemler', 'Genel', 'Güncellemeler']
        assert 'Eski dönem bir kez indirilir, güncellenmez.' in labels
        assert str(window.past_button.title()) == 'Eski dönemi indir'
        assert str(window.past_label.stringValue()) == 'Eski dönemleri görmek için giriş yapın.'
        assert not window.past_button.isEnabled() and not window.past_popup.isEnabled()
        # Below the version row, in the Güncellemeler section.
        assert str(window.uninstall_button.title()) == 'Uygulamayı kaldır…'
        assert window.uninstall_button.frame().origin.y > window.update_button.frame().origin.y
        window.target.uninstall_(None)
        assert actions == ['uninstall']

        model.session = {'saved_at': datetime.now(timezone.utc).timestamp(), 'user': {'displayName': 'Ada'}}
        window.update_status(window_status(model))
        assert str(window.past_label.stringValue()) == 'Eski dönemler yükleniyor…'
        model.finish_past_terms(['2025-2026 Bahar', '2025-2026 Güz'], RunOutcome('ok'))
        window.update_status(window_status(model))
        assert [str(t) for t in window.past_popup.itemTitles()] == ['2025-2026 Bahar', '2025-2026 Güz']
        assert window.past_button.isEnabled() and window.past_popup.isEnabled()
        window.past_popup.selectItemWithTitle_('2025-2026 Güz')
        window.update_status(window_status(model))
        assert str(window.past_popup.titleOfSelectedItem()) == '2025-2026 Güz'
        window.target.pastTerm_(None)
        assert downloads == ['2025-2026 Güz']
        model.begin('sync')
        window.update_status(window_status(model))
        assert not window.past_button.isEnabled() and not window.uninstall_button.isEnabled()
        window.target.pastTerm_(None)
        assert downloads == ['2025-2026 Güz']
    finally:
        window.window.close()


def test_settings_window_scrolls_on_a_short_screen_with_the_buttons_in_view(tmp_path):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from AppKit import NSApplication, NSScrollView, NSWindowStyleMaskResizable
    from Foundation import NSMakeRect
    from blackboard_sync.menubar.model import AppModel
    from blackboard_sync.menubar.settings_form import FormValues, SCREEN_MARGIN, window_status
    from blackboard_sync.menubar.settings_window import SettingsWindow

    NSApplication.sharedApplication()
    model = AppModel(tmp_path, datetime.now(timezone.utc), configured=True)
    window = SettingsWindow(FormValues('https://bb.example.edu', str(tmp_path), True),
                            window_status(model), True, lambda v, l: None, lambda a: None, lambda: None)

    def screen(height):  # visibleFrame: the screen without the menu bar and Dock
        return SimpleNamespace(visibleFrame=lambda: NSMakeRect(0, 0, 1440, height))

    try:
        assert window.window.styleMask() & NSWindowStyleMaskResizable
        assert isinstance(window.form_scroll, NSScrollView)
        assert window.form_scroll.hasVerticalScroller() and window.form_scroll.autohidesScrollers()
        form = window.form_scroll.documentView()
        assert window.url_field.superview() is form and window.uninstall_button.superview() is form
        # Vazgeç, Kaydet and the error line sit below the scrolling form, not in it.
        assert [str(b.title()) for b in (window.cancel_button, window.save_button)] == ['Vazgeç', 'Kaydet']
        for control in (window.cancel_button, window.save_button, window.error_label):
            assert control.superview() is window.button_bar
        general = window.tabs.tabViewItems()[0].view()
        assert window.form_scroll.superview() is general and window.button_bar.superview() is general

        # A 13-inch MacBook (1440x900, about 800 points free): the window fits and the form scrolls.
        window.fit_to_screen(screen(800))
        assert window.window.frame().size.height == 800 - SCREEN_MARGIN
        clip = window.form_scroll.contentView().frame().size.height
        assert clip < form.frame().size.height
        bar = window.button_bar.frame()
        assert bar.origin.y + bar.size.height == general.frame().size.height  # at the bottom
        assert window.form_scroll.frame().size.height == bar.origin.y
        minimum = window.window.contentMinSize()
        assert minimum.width == window.window.contentMaxSize().width == window.window.contentView().frame().size.width
        assert minimum.height < window.window.contentView().frame().size.height

        # Taller by hand: the form gets the room, the bar follows the bottom edge.
        frame = window.window.frame()
        window.window.setFrame_display_(NSMakeRect(frame.origin.x, frame.origin.y, frame.size.width,
                                                   frame.size.height + 50), False)
        assert window.form_scroll.contentView().frame().size.height == clip + 50
        assert window.button_bar.frame().origin.y == bar.origin.y + 50
        window.tabs.selectTabViewItemAtIndex_(1)  # the Silinenler list keeps scrolling on its own
        deleted_list = window.deleted_scroll.frame()
        assert window.refetch_button.frame().origin.y > deleted_list.origin.y + deleted_list.size.height
        window.tabs.selectTabViewItemAtIndex_(0)

        # A big screen shows the whole form, nothing to scroll.
        window.fit_to_screen(screen(1400))
        assert window.window.frame().size.height < 1400 - SCREEN_MARGIN
        assert window.window.contentView().frame().size.height == window.content_height
        assert window.form_scroll.contentView().frame().size.height == form.frame().size.height
    finally:
        window.window.close()
