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
    window = MainWindow(values, main_status(model, NOW), on_missing=lambda: list(rows), **handlers)
    return window, model, rows


def signed_in(model):
    from blackboard_sync.menubar.model import RunOutcome

    model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada Student'}}
    model.last = RunOutcome('ok', finished_at=NOW)
    return model


def visible_page(window):
    return next(name for name, page in window.pages.items() if not page.isHidden())


def test_sidebar_switches_sections_and_baslangic_becomes_genel_bakis(tmp_path):
    from blackboard_sync.deleted import MissingOutput
    from blackboard_sync.menubar.main_window_model import DELETED, GENERAL, OVERVIEW, main_status
    from blackboard_sync.menubar.model import AppModel

    row = MissingOutput('one', 'T/C/one.pdf', 'T', 'C', 'one.pdf', 'T/C')
    window, model, _ = make_window(tmp_path, AppModel(tmp_path, NOW, configured=False), rows=[row])
    try:
        titles = [str(window.nav_items[s][2].stringValue()) for s in (OVERVIEW, GENERAL, DELETED)]
        assert titles == ['Başlangıç', 'Genel', 'Silinenler']
        assert str(window.nav_items[DELETED][3].stringValue()) == '1'
        assert visible_page(window) == 'start' and window.section == OVERVIEW
        assert str(window.start_button.title()) == 'Giriş yap'
        assert str(window.start_button.keyEquivalent()) == '\r'  # Return signs in
        assert window.account_card.isHidden()  # Başlangıç signs in with its own form
        window.target.nav_(window.nav_items[GENERAL][4])
        assert visible_page(window) == GENERAL and window.section == GENERAL
        assert str(window.start_button.keyEquivalent()) == ''  # not from a hidden section
        window.target.nav_(window.nav_items[DELETED][4])
        assert visible_page(window) == DELETED

        # Signed in: the first section becomes Genel bakış, on its own page.
        model.configured = True
        signed_in(model)
        window.update_status(main_status(model, NOW))
        window.select(OVERVIEW)
        assert visible_page(window) == OVERVIEW
        assert str(window.nav_items[OVERVIEW][2].stringValue()) == 'Genel bakış'
        # The account sits at the bottom of the sidebar, not on the page.
        assert not window.account_card.isHidden()
        assert window.account_card.superview() is window.sidebar_view
        frame, sidebar = window.account_card.frame(), window.sidebar_view.frame()
        assert frame.origin.y + frame.size.height == sidebar.size.height - 12
        assert str(window.avatar_text.stringValue()) == 'AS'
        assert str(window.account_title.stringValue()) == 'Ada Student'
        assert str(window.account_detail.stringValue()).startswith('Son senkron: bugün ')
        assert window.badge.isHidden() and window.login_button.isHidden()  # no "Bağlı" badge
        # A sync keeps showing when the last one finished.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert str(window.badge_text.stringValue()) == 'Senkron sürüyor'
        assert str(window.account_detail.stringValue()).startswith('Son senkron: bugün ')
        assert str(window.sync_button.title()) == 'Senkronize ediliyor…' and not window.sync_button.isEnabled()
    finally:
        window.window.close()


def test_overview_buttons_and_recent_files(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RecentItem

    actions, opened = [], []
    window, model, _ = make_window(tmp_path, on_action=actions.append, on_open=opened.append)
    try:
        signed_in(model).recent = [RecentItem('T/SWE305/Homework1.docx', 'SWE305', NOW.isoformat()),
                                   RecentItem('T/CSE301/week1.pdf', 'CSE301', NOW.isoformat())]
        window.update_status(main_status(model, NOW))
        assert str(window.recent_count.stringValue()) == '2 dosya'
        buttons = [v for v in window.recent_scroll.documentView().subviews()
                   if hasattr(v, 'action') and v.action() == 'openRecent:']
        assert [b.toolTip() for b in buttons] == ['Homework1.docx', 'week1.pdf']
        window.target.openRecent_(buttons[1])
        assert opened == ['T/CSE301/week1.pdf']
        window.target.sync_(None)
        window.target.folder_(None)
        assert actions == ['sync', 'folder']
        # Expired: the card offers signing in instead of the badge.
        model.session = None
        model.session_expired = True
        window.update_status(main_status(model, NOW))
        assert str(window.account_title.stringValue()) == 'Oturum sona erdi'
        assert not window.login_button.isHidden() and str(window.login_button.title()) == 'Giriş yap'
        assert window.badge.isHidden() and not window.sync_button.isEnabled()
        window.target.login_(None)
        assert actions[-1] == 'login'
    finally:
        window.window.close()


def test_a_running_sync_shows_the_illustration_and_it_stops_with_the_sync(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RecentItem, RunOutcome

    window, model, _ = make_window(tmp_path)
    try:
        model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada Student'}}
        window.state.open = True  # as if shown; nothing is put on screen
        window.update_status(main_status(model, NOW))
        assert window.first_scene.isHidden() and window.scene_card.isHidden()
        assert not window.first_scene.animating and not window.recent_scroll.isHidden()

        # The first sync: the large illustration in place of the empty list.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.first_scene.isHidden() and window.recent_scroll.isHidden()
        assert str(window.first_line.stringValue()) == 'Dosyalarınız ilk kez indiriliyor…'
        assert window.first_scene.animating and not window.scene_view.animating
        assert window.scene_card.isHidden()
        # It keeps one timer across refreshes.
        timer = window.first_scene.timer
        window.update_status(main_status(model, NOW))
        assert window.first_scene.timer is timer

        model.finish_sync(RunOutcome('ok', finished_at=NOW), NOW)
        model.recent = [RecentItem('T/SWE305/Homework1.docx', 'SWE305', NOW.isoformat())]
        window.update_status(main_status(model, NOW))
        assert window.first_scene.isHidden() and not window.first_scene.animating
        assert window.scene_card.isHidden() and not window.recent_scroll.isHidden()
        top = window.recent_card.frame().origin.y

        # A later sync: small, above the list, which stays in view and moves down.
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.scene_card.isHidden() and window.scene_view.animating
        assert str(window.scene_line.stringValue()) == 'Yeni içerik kontrol ediliyor…'
        assert window.first_scene.isHidden() and not window.recent_scroll.isHidden()
        assert window.recent_card.frame().origin.y > top
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
        assert not window.first_scene.isHidden()
        assert window.first_scene.still and not window.first_scene.animating
    finally:
        window.window.close()


def test_a_note_shows_above_the_list_and_the_sidebar_card_offers_sign_in(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RunOutcome

    window, model, _ = make_window(tmp_path)
    try:
        signed_in(model)
        window.update_status(main_status(model, NOW))
        assert window.account_message.isHidden()
        height = window.account_card.frame().size.height
        model.last = RunOutcome('error', message='Blackboard\'a ulaşılamadı', finished_at=NOW)
        window.update_status(main_status(model, NOW))
        assert not window.account_message.isHidden()
        assert str(window.account_message.stringValue()) == 'Senkron tamamlanamadı: Blackboard\'a ulaşılamadı'
        assert window.badge.isHidden()
        model.session, model.session_expired = None, True
        window.update_status(main_status(model, NOW))
        assert not window.login_button.isHidden() and window.login_button.superview() is window.account_card.contentView()
        assert window.account_card.frame().size.height > height  # it grows upwards for the button
        frame = window.account_card.frame()
        assert frame.origin.y + frame.size.height == window.sidebar_view.frame().size.height - 12
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
        window.interval_popup.selectItemWithTitle_('Her 3 saatte')
        window.target.changed_(window.interval_popup)
        assert not window.button_bar.isHidden()
        assert str(window.error_label.stringValue()) == 'Kaydedilmemiş değişiklikler'
        assert [str(b.title()) for b in (window.cancel_button, window.save_button)] == ['Vazgeç', 'Kaydet']
        assert str(window.cancel_button.keyEquivalent()) == '\x1b'
        window.target.cancel_(None)  # Vazgeç: back to what is saved
        assert window.button_bar.isHidden() and window.values().sync_interval_minutes == 60

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


def test_silinenler_selection_dismissal_and_empty_state(tmp_path):
    from blackboard_sync.deleted import MissingOutput
    from blackboard_sync.menubar.main_window_model import DELETED, main_status

    rows = [MissingOutput('one', 'term/course/one.pdf', 'term', 'course', 'one.pdf', 'term/course')]
    actions = []

    def action(name, keys):
        actions.append((name, keys))
        if name == 'dismiss':
            rows.clear()

    window, model, _ = make_window(tmp_path, on_deleted_action=action)
    window.on_missing = lambda: list(rows)
    try:
        window.select(DELETED)
        labels = [str(v.stringValue()) for v in window.pages[DELETED].subviews() if hasattr(v, 'stringValue')]
        assert ('Daha önce indirilip klasörden silinen dosyaları seçip geri indirebilirsiniz; '
                'listeden kaldırılanlar tekrar önerilmez.') in labels
        assert not window.refetch_button.isEnabled()
        button = window.checks['one']
        button.setState_(1)
        window.target.checked_(button)
        assert window.refetch_button.isEnabled()
        window.target.refetch_(None)
        assert actions == [('refetch', ['one'])]
        model.begin('sync')
        window.update_status(main_status(model, NOW))
        assert not window.refetch_button.isEnabled() and not window.dismiss_button.isEnabled()
        model.busy = None
        window.update_status(main_status(model, NOW))
        window.target.dismiss_(None)
        assert actions[-1] == ('dismiss', ['one'])
        assert window.selection.rows == [] and str(window.nav_items[DELETED][3].stringValue()) == ''
        assert 'Silinmiş dosya yok.' in [str(control.stringValue())
                                      for control in window.deleted_scroll.documentView().subviews()]
    finally:
        window.window.close()


def test_genel_past_terms_section_and_uninstall_button(tmp_path):
    from blackboard_sync.menubar.main_window_model import main_status
    from blackboard_sync.menubar.model import RunOutcome

    actions, downloads = [], []
    window, model, _ = make_window(tmp_path, on_action=actions.append, on_past_term=downloads.append)
    try:
        labels = [str(view.stringValue()) for box in window.form_scroll.documentView().subviews()
                  for view in box.contentView().subviews() if hasattr(view, 'stringValue')]
        sections = [label for label in labels if label in ('Hesap', 'Klasör', 'Eski dönemler', 'Genel', 'Güncellemeler')]
        assert sections == ['Hesap', 'Klasör', 'Genel', 'Eski dönemler', 'Güncellemeler']
        assert 'Eski dönem bir kez indirilir, güncellenmez.' in labels
        assert str(window.past_button.title()) == 'Eski dönemi indir'
        assert str(window.past_label.stringValue()) == 'Eski dönemleri görmek için giriş yapın.'
        assert not window.past_button.isEnabled() and not window.past_popup.isEnabled()
        assert str(window.uninstall_button.title()) == 'Uygulamayı kaldır…'
        window.target.uninstall_(None)
        assert actions == ['uninstall']

        model.session = {'saved_at': NOW.timestamp(), 'user': {'displayName': 'Ada'}}
        window.update_status(main_status(model, NOW))
        assert str(window.past_label.stringValue()) == 'Eski dönemler yükleniyor…'
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
        window.target.account_(None)  # signed in: "Hesaptan çıkış yap"
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
        window.interval_popup.selectItemWithTitle_('Yalnızca elle')
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
    assert list(menus) == ["Blackboard Sync", "Düzen", "Pencere"]
    actions = {str(item.title()): (item.action(), str(item.keyEquivalent()))
               for menu in menus.values() for item in menu.itemArray() if not item.isSeparatorItem()}
    assert actions["Blackboard Sync'ten çık"] == ("terminate:", "q")
    assert actions["Yapıştır"] == ("paste:", "v")
    assert actions["Kapat"] == ("performClose:", "w")
    assert actions["Küçült"] == ("performMiniaturize:", "m")
    assert window_menu is menus["Pencere"]
