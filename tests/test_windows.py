"""Windows adapters must remain importable and testable without a Windows GUI."""

import base64
import re
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from blackboard_sync.config import Config
from blackboard_sync.menubar.model import AppModel, CourseChange, RunOutcome, changes_notification
from blackboard_sync.menubar.settings_form import FormValues
from blackboard_sync.settings import Settings
from blackboard_sync.windows import autostart, notifications, presentation
from blackboard_sync.windows.app import LogThrottle, TrayApp, cli_runner


class Menu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items


class Item:
    def __init__(self, title, action, **kwargs):
        self.title, self.action = title, action
        self.__dict__.update(kwargs)


def test_entire_shared_menu_maps_recursively(tmp_path):
    model = AppModel(tmp_path, datetime.now(timezone.utc), autostart=True, session_expired=True)
    model.courses = [CourseChange("CSE", "CSE", {}, [], "Algorithms")]
    entries = model.menu(datetime.now(timezone.utc)).entries
    calls = []
    rendered = presentation.render_menu(entries, lambda *args: calls.append(args), Menu, Item)

    def compare(entries, menu):
        assert len(entries) == len(menu.items)
        for entry, item in zip(entries, menu.items):
            if not entry.title:
                assert item is Menu.SEPARATOR
                continue
            assert (item.title, item.enabled) == (entry.title, entry.enabled)
            assert (item.checked(None) if item.checked else False) == entry.checked
            if entry.children:
                compare(entry.children, item.action)
            elif entry.action:
                item.action(None, None)
                assert calls[-1] == (entry.action, entry.value)
    compare(entries, rendered)
    model.begin("sync")
    busy = presentation.render_menu(model.menu(datetime.now(timezone.utc)).entries, lambda *a: None, Menu, Item)
    assert not next(i for i in busy.items if getattr(i, 'title', '') == 'Senkronize ediliyor…').enabled


def test_run_command_quotes_spaces_and_uses_absolute_interpreter():
    assert autostart.command(r'C:\Program Files\Python\pythonw.exe') == '"C:\\Program Files\\Python\\pythonw.exe" -m blackboard_sync.windows --background'


def test_default_run_command_uses_pythonw(monkeypatch):
    monkeypatch.setattr(autostart, 'Path', PureWindowsPath)
    monkeypatch.setattr(autostart.sys, 'executable', r'C:\My App\.venv\Scripts\python.exe')
    assert autostart.command().startswith('"C:\\My App\\.venv\\Scripts\\pythonw.exe"')


def test_frozen_run_command_is_the_installed_exe(monkeypatch):
    monkeypatch.setattr(autostart.runtime, 'is_frozen', lambda: True)
    monkeypatch.setattr(autostart.sys, 'executable', r'C:\Users\Ada\AppData\Local\Programs\Blackboard Sync\Blackboard Sync.exe')
    assert autostart.command() == '"C:\\Users\\Ada\\AppData\\Local\\Programs\\Blackboard Sync\\Blackboard Sync.exe" --background'


def test_login_item_from_before_background_is_kept_and_upgraded(monkeypatch):
    monkeypatch.setattr(autostart.runtime, 'is_frozen', lambda: True)
    monkeypatch.setattr(autostart.sys, 'executable', r'C:\App\Blackboard Sync.exe')
    written = []
    monkeypatch.setattr(autostart, 'set_enabled', written.append)
    monkeypatch.setattr(autostart, '_value', lambda: '"C:\\App\\Blackboard Sync.exe"')
    assert autostart.is_installed()
    autostart.upgrade_legacy()
    assert written == [True]
    monkeypatch.setattr(autostart, '_value', lambda: '"C:\\App\\Blackboard Sync.exe" --background')
    autostart.upgrade_legacy()
    assert written == [True]
    monkeypatch.setattr(autostart, '_value', lambda: None)
    assert not autostart.is_installed()


def test_frozen_cli_runs_as_the_console_twin(monkeypatch):
    from blackboard_sync.windows import app as tray
    seen = []
    monkeypatch.setattr(tray, 'Path', PureWindowsPath)
    monkeypatch.setattr(tray.runtime, 'is_frozen', lambda: True)
    monkeypatch.setattr(tray.subprocess, 'run', lambda command, **kw: seen.append(command))
    tray.cli_runner([r'C:\App\Blackboard Sync.exe', '--version'])
    assert seen == [[r'C:\App\blackboard-sync-cli.exe', '--version']]


def test_notification_keeps_course_lines_and_safe_click_target(tmp_path):
    outcome = RunOutcome('ok', courses=[
        CourseChange('CSE & $(bad)', 'Term/CSE', {'new_files': 2}, []),
        CourseChange('MAT', 'Term/MAT', {'new_notes': 1}, []),
    ])
    note = changes_notification(outcome, tmp_path)
    fields = presentation.notification_fields(note)
    assert fields['msg'] == 'CSE & $(bad): 2 yeni dosya\nMAT: 1 yeni not'
    assert fields['launch'] == (tmp_path / 'Term').as_uri()
    script = notifications.toast_script(note)
    assert '$(bad)' not in script
    payload = re.search(r"FromBase64String\('([^']+)'\)", script).group(1)
    xml = ET.fromstring(base64.b64decode(payload))
    assert xml.find('visual/binding/text[2]').text == fields['msg']
    assert xml.attrib['launch'] == fields['launch']


def test_utf8_runner(monkeypatch):
    calls = []
    monkeypatch.setattr('blackboard_sync.windows.app.subprocess.run', lambda *a, **kw: calls.append(kw))
    cli_runner(['python'], text=True)
    assert calls[0]['encoding'] == 'utf-8'
    assert calls[0]['text'] is True


def make_app(tmp_path):
    app = TrayApp.__new__(TrayApp)
    app.config = Config(data_dir=tmp_path, dest=tmp_path / 'old')
    app.settings = Settings('https://old.school.edu', tmp_path / 'old')
    app.login_after_job = False
    app.uninstalling = False
    app.model = AppModel(app.settings.dest, datetime.now(timezone.utc))
    app.save = lambda: None
    app.refresh = lambda: None
    app.window = None
    return app


def test_settings_window_lists_past_terms_once_and_dispatches_one_time_job(tmp_path, monkeypatch):
    import sys
    from blackboard_sync.menubar import jobs
    from blackboard_sync.windows import app as tray

    app = make_app(tmp_path)
    del app.refresh  # the real one: it starts the lookup while the window is open
    app.post = lambda callback, *args: callback(*args)
    app.start_next = lambda: None
    app.notify = lambda note: None
    app.icon = SimpleNamespace(icon=None, menu=None)
    app.drawn = app.drawn_icon = None
    statuses = []
    app.window = SimpleNamespace(update_status=lambda status: statuses.append(status.form),
                                 state=SimpleNamespace(open=True, section="overview"))

    class Thread:
        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)

    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(Menu=Menu, MenuItem=Item))
    monkeypatch.setattr(tray, "icon_image", lambda state: state)
    monkeypatch.setattr(tray.autostart, "is_installed", lambda: False)
    monkeypatch.setattr(tray.threading, "Thread", Thread)
    monkeypatch.setattr(jobs, "refresh_session", lambda config, model, settings: None)
    lookups = []
    monkeypatch.setattr(jobs, "run_past_terms",
                        lambda *args, **kwargs: lookups.append(kwargs) or (["2025-2026 - Spring"], RunOutcome("ok")))
    calls = []
    monkeypatch.setattr(jobs, "run_sync", lambda *args, **kwargs: calls.append((args, kwargs)) or RunOutcome("ok"))

    app.refresh()  # not signed in: nothing to look up
    assert lookups == [] and statuses[-1].past_message == "Eski dönemleri görmek için giriş yapın."
    app.model.session = {"saved_at": datetime.now(timezone.utc).timestamp(), "user": {"displayName": "Ada"}}
    app.refresh()
    assert lookups == []  # the overview does not ask the school; Genel does
    app.window.state.section = "general"
    app.refresh()
    app.refresh()
    assert len(lookups) == 1 and lookups[0]["runner"] is tray.cli_runner
    status = statuses[-1]
    assert status.past_terms == ("2025-2026 - Spring",) and status.past_enabled
    assert app.model.busy is None
    app.download_past_term("2025-2026 - Spring")
    assert calls[0][0][0] == "past_term"
    assert calls[0][1]["term_name"] == "2025-2026 - Spring"
    assert calls[0][1]["runner"] is tray.cli_runner
    assert app.model.past_term == "" and app.model.busy is None
    assert statuses[-1].past_message == "2025-2026 - Spring · 0 dosya indirildi (eski dönem)."
    assert len(lookups) == 1
    app.window.state.open = False  # closed: no lookup without the window
    app.model.reload_past_terms()
    app.refresh()
    assert len(lookups) == 1


def test_closing_settings_while_listing_past_terms_does_not_wedge_job(tmp_path):
    app = make_app(tmp_path)
    assert app.model.begin("past_terms")
    app.window = None
    app.past_terms_done(["2025-2026 - Fall"], RunOutcome("ok"))
    assert app.model.busy is None
    assert app.model.begin("sync")


def test_uninstall_from_settings_closes_the_window_without_the_tray_hint(tmp_path, monkeypatch):
    import sys
    from blackboard_sync.windows import main_window
    from blackboard_sync.windows.app import uninstall

    app = make_app(tmp_path)
    hints, parents, destroyed = [], [], []
    app.icon = SimpleNamespace(stop=lambda: None, notify=lambda *args: hints.append(args))
    app.root = SimpleNamespace(destroy=lambda: None)
    app.window = SimpleNamespace(window='main', state=SimpleNamespace(open=True),
                                 destroy=lambda: destroyed.append(True))
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(messagebox=SimpleNamespace(
        showinfo=lambda *args, **kw: parents.append(kw["parent"]),
        showwarning=lambda *args, **kw: parents.append(kw["parent"]),
        showerror=lambda *args, **kw: parents.append(kw["parent"]))))
    choices = [None, False]
    monkeypatch.setattr(main_window, "ask_uninstall", lambda parent, dest: choices.pop(0))
    monkeypatch.setattr(uninstall, "uninstall", lambda *args, **kwargs: ["kept a file"])
    monkeypatch.setattr(uninstall, "remove_app", lambda: [])

    app.dispatch("uninstall")  # "Vazgeç": the window stays
    assert app.window is not None and not destroyed and not app.uninstalling
    app.dispatch("uninstall")
    assert app.window is None and destroyed == [True] and hints == []
    assert parents == [app.root] and app.closed


def test_settings_reject_invalid_url_and_busy_job(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(autostart, 'set_enabled', lambda enabled: None)
    values = FormValues('http://school.edu', str(tmp_path), False)
    assert app.settings_submitted(values, False)[1] == 'base_url'
    app.model.begin('sync')
    assert 'bekleyin' in app.settings_submitted(values, False)[0]
    assert not (tmp_path / 'settings.json').exists()


def test_settings_school_change_saves_and_starts_login(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    toggles, jobs = [], []
    monkeypatch.setattr(autostart, 'set_enabled', toggles.append)
    app.start_job = jobs.append
    values = FormValues('new.school.edu/ultra', str(tmp_path / 'new'), True)
    assert app.settings_submitted(values, False) is None
    assert app.settings.base_url == 'https://new.school.edu'
    assert app.model.dest == tmp_path / 'new'
    assert jobs == ['login']
    assert toggles == [True]
    assert (tmp_path / 'settings.json').exists()


def test_school_change_saved_during_past_term_lookup_signs_in_afterwards(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(autostart, 'set_enabled', lambda enabled: None)
    started = []
    app.start_job = started.append
    assert app.model.begin('past_terms')  # the open window looks the terms up
    values = FormValues('new.school.edu', str(tmp_path / 'old'), False)
    assert app.settings_submitted(values, False) is None
    assert app.settings.base_url == 'https://new.school.edu'
    assert started == [] and app.login_after_job
    app.past_terms_done(['Old school term'], RunOutcome('ok'))
    assert started == ['login'] and not app.login_after_job
    assert app.model.past_terms == [] and not app.model.past_terms_loaded  # looked up again for the new school


def test_settings_registry_failure_keeps_window_open(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    def denied(enabled):
        raise PermissionError('Denied')
    monkeypatch.setattr(autostart, 'set_enabled', denied)
    values = FormValues(app.settings.base_url, str(app.settings.dest), True)
    assert 'kaydedilemedi' in app.settings_submitted(values, False)[0]
    assert not (tmp_path / 'settings.json').exists()


def test_windows_reopen_hint_names_the_start_menu():
    from blackboard_sync.menubar.main_window_model import reopen_hint
    from blackboard_sync.windows.main_window import REOPEN_WHERE
    assert "Başlat menüsünden" in reopen_hint(REOPEN_WHERE)
    assert "Mac" not in reopen_hint(REOPEN_WHERE) and "Launchpad" not in reopen_hint(REOPEN_WHERE)


def test_pythonw_parent_runs_hidden_console_child(monkeypatch):
    import blackboard_sync.windows.app as app_module
    calls = []
    monkeypatch.setattr(app_module, 'Path', PureWindowsPath)
    monkeypatch.setattr(app_module.subprocess, 'run', lambda cmd, **kw: calls.append(cmd))
    cli_runner([r'C:\App\.venv\Scripts\pythonw.exe', '-m', 'blackboard_sync'])
    assert calls == [[r'C:\App\.venv\Scripts\python.exe', '-m', 'blackboard_sync']]


def fake_tk(monkeypatch, tmp_path):
    """Just enough of tkinter for the main window, recording what it was told."""
    import sys

    widgets = []

    class Widget:
        def __init__(self, *args, **kwargs):
            self.parent = args[0] if args else None
            self.options = dict(kwargs)
            self.children, self.bindings, self.scrolled = [], {}, []
            self.removed = self.destroyed = self.focused = False
            self.view = (0.0, 1.0)
            if isinstance(self.parent, Widget):
                self.parent.children.append(self)
            widgets.append(self)

        def __getattr__(self, name):  # columnconfigure, protocol, lift, ... do nothing
            return lambda *args, **kwargs: None

        def grid(self, **kwargs):
            self.grid_options = kwargs or getattr(self, "grid_options", {})
            self.removed = False

        def grid_remove(self):
            self.removed = True

        def configure(self, **kwargs):
            self.options.update(kwargs)

        def bind(self, event, callback):
            self.bindings[event] = callback

        def winfo_children(self):
            return list(self.children)

        def destroy(self):
            self.destroyed = True
            if isinstance(self.parent, Widget) and self in self.parent.children:
                self.parent.children.remove(self)

        def focus_set(self):
            self.focused = True

        def title(self, text):
            self.caption = text

        def geometry(self, spec):
            self.size = spec

        def minsize(self, *args):
            self.minimum = args

        def attributes(self, *args):
            self.topmost = args[1]

        def after(self, delay, callback):
            self.later = callback

        def withdraw(self):
            self.shown = False

        def deiconify(self):
            self.shown = True

        def yview(self, *args):
            return self.view

        def yview_scroll(self, *args):
            self.scrolled.append(args)

    class Variable:
        def __init__(self, master=None, value=None):
            self.value, self.traces = value, []

        def get(self):
            return self.value

        def set(self, value):
            self.value = value
            for callback in self.traces:
                callback()

        def trace_add(self, mode, callback):
            self.traces.append(callback)

    names = ('Frame', 'Label', 'Entry', 'Button', 'Checkbutton', 'Radiobutton', 'Separator', 'Combobox',
             'LabelFrame', 'Scrollbar')
    ttk = SimpleNamespace(**{name: Widget for name in names})
    fake = SimpleNamespace(Toplevel=Widget, Canvas=Widget, StringVar=Variable, BooleanVar=Variable, ttk=ttk,
                           filedialog=SimpleNamespace(askdirectory=lambda **kw: str(tmp_path / 'picked')))
    monkeypatch.setitem(sys.modules, 'tkinter', fake)
    return widgets


def test_windows_main_window_sections_layout_and_validation(monkeypatch, tmp_path):
    from blackboard_sync.deleted import MissingOutput
    from blackboard_sync.menubar.main_window_model import DELETED, GENERAL, OVERVIEW, main_status
    from blackboard_sync.menubar.model import RecentItem
    from blackboard_sync.menubar.settings_form import SCREEN_MARGIN
    from blackboard_sync.windows import main_window as module
    from blackboard_sync.windows.main_window import CHROME, MainWindow

    widgets = fake_tk(monkeypatch, tmp_path)
    monkeypatch.setattr(module, 'work_area', lambda window: (0, 0, 1366, 600))  # a short screen
    now = datetime.now(timezone.utc)
    model = AppModel(tmp_path, now, configured=False)
    saved = [FormValues('https://school.edu', str(tmp_path), True)]
    submitted, closed, actions, opened = [], [], [], []

    def submit(values, login):
        submitted.append((values, login))
        if values.base_url == 'school.edu':
            return 'Geçerli bir adres yazın.', 'base_url'
        saved.append(values)
        return None

    rows = [MissingOutput('key', 'term/course/file.pdf', 'term', 'course', 'file.pdf', 'term/course')]
    deleted_actions = []

    def deleted_action(action, keys):
        deleted_actions.append((action, keys))
        if action == 'dismiss':
            rows.clear()

    window = MainWindow(None, saved[0], main_status(model, now), submit, actions.append,
                        lambda: closed.append(True), on_values=lambda: saved[-1], on_open=opened.append,
                        on_missing=lambda: list(rows), on_deleted_action=deleted_action)

    def visible():
        return [name for name, page in window.pages.items() if not page.removed]

    def labels():
        return [w.options.get('text') for w in widgets if not w.destroyed]

    assert window.window.caption == 'Blackboard Sync'
    assert window.window.shown is False  # built hidden, shown by show()
    window.show()
    # A short screen: the window fits above the taskbar, centred; sections scroll.
    total = 600 - SCREEN_MARGIN
    assert window.window.size == f"940x{total - CHROME}+213+{SCREEN_MARGIN // 2}"
    assert window.window.minimum[0] == 760 and window.window.minimum[1] < total - CHROME
    assert window.window.shown and window.window.topmost is True
    window.window.later()
    assert window.window.topmost is False
    assert visible() == ['start'] and window.state.open
    assert [window.nav[s].options['text'] for s in (OVERVIEW, GENERAL, DELETED)] == [
        'Başlangıç', 'Genel', 'Silinenler (1)']
    assert window.start_button.options['text'] == 'Giriş yap'
    for text in ('Ders dosyalarınız burada başlayacak.', 'Okulunuzu ve klasörünüzü seçin',
                 'Bu pencereyi kapatabilirsiniz. Tekrar görmek için Başlat menüsünden Blackboard Sync\'i açmanız yeterli.'):
        assert text in labels()
    assert 'Dosyalarınız University klasörüne kaydedilir.' not in labels()
    assert window.button_bar.removed  # nothing changed yet

    # Başlangıç signs in with the form; a bad address stays, with the reason.
    window.url.set('school.edu')
    window.start_button.options['command']()
    assert submitted[-1][1] is True and submitted[-1][0].base_url == 'school.edu'
    assert window.start_message.options['text'] == 'Geçerli bir adres yazın.'
    assert window.start_fields['base_url'].focused
    window.url.set('https://school.edu')
    window.start_button.options['command']()
    assert submitted[-1][1] is True and window.start_message.options['text'] == ''

    # Genel: the bar appears with a change and leaves with Vazgeç or Kaydet; the window stays.
    window.nav[GENERAL].options['command']()
    assert visible() == [GENERAL] and window.button_bar.removed
    window.interval.set('Yalnızca elle')
    assert not window.button_bar.removed
    assert window.error_label.options['text'] == 'Kaydedilmemiş değişiklikler'
    window.window.bindings['<Escape>'](None)  # Vazgeç
    assert window.button_bar.removed and window.interval.get() == 'Her saat'
    window.check_updates.set(False)
    save = next(w for w in widgets if w.options.get('text') == 'Kaydet')
    save.options['command']()
    assert submitted[-1] == (window.values(), False) and submitted[-1][0].check_updates is False
    assert window.button_bar.removed and window.state.open and closed == []

    # Signed in: Genel bakış with the account, the last sync and the recent files.
    model.configured = True
    model.session = {'saved_at': now.timestamp(), 'user': {'displayName': 'Ada Student'}}
    model.last = RunOutcome('ok', finished_at=now)
    model.recent = [RecentItem('term/SWE305/Homework1.docx', 'SWE305', now.isoformat())]
    model.begin('sync')
    window.update_status(main_status(model, now))
    window.nav[OVERVIEW].options['command']()
    assert visible() == [OVERVIEW] and window.nav[OVERVIEW].options['text'] == 'Genel bakış'
    assert window.account_title.options['text'] == 'Ada Student'
    assert window.account_detail.options['text'].startswith('Son senkron: bugün ')
    assert window.badge.options['text'] == 'Senkron sürüyor' and window.login_button.removed
    assert window.sync_button.options['state'] == 'disabled'
    file_button = next(w for w in widgets if w.options.get('text') == 'Homework1.docx' and not w.destroyed)
    file_button.options['command']()
    assert opened == ['term/SWE305/Homework1.docx']
    model.busy = None
    window.update_status(main_status(model, now))
    window.sync_button.options['command']()
    assert actions == ['sync']

    # Silinenler: one sentence, select, bring back, dismiss.
    window.nav[DELETED].options['command']()
    assert visible() == [DELETED]
    assert ('Daha önce indirilip klasörden silinen dosyaları seçip geri indirebilirsiniz; '
            'listeden kaldırılanlar tekrar önerilmez.') in labels()
    assert 'term · course' in labels()
    assert window.refetch_button.options['state'] == 'disabled'
    window.select_all_button.options['command']()
    window.refetch_button.options['command']()
    assert deleted_actions == [('refetch', ['key'])]
    window.dismiss_button.options['command']()
    assert deleted_actions[-1] == ('dismiss', ['key']) and 'Silinmiş dosya yok.' in labels()
    assert window.nav[DELETED].options['text'] == 'Silinenler'

    # The wheel scrolls the section in view, not one that fits.
    window.canvas.view = (0.0, 0.7)
    window.window.bindings['<MouseWheel>'](SimpleNamespace(delta=-120))
    assert window.canvas.scrolled == [(1, 'units')]
    assert window.interval_dropdown.bindings['<MouseWheel>'](SimpleNamespace(delta=120)) == 'break'

    # Closing hides the window and drops unsaved edits; nothing else stops.
    window.nav[GENERAL].options['command']()
    window.url.set('https://other.edu')
    window.close()
    assert closed == [True] and window.window.shown is False and not window.window.destroyed
    assert not window.state.open and window.url.get() == 'https://school.edu'
    monkeypatch.setattr(module, 'work_area', lambda window: (0, 0, 2560, 1400))
    window.show()  # started again: the overview, at the full size on a big screen
    assert visible() == [OVERVIEW] and window.state.open
    assert window.window.size == "940x640+810+360"
    window.show(GENERAL)  # "Ayarlar…"
    assert visible() == [GENERAL]


def test_work_area_is_the_screen_above_the_taskbar():
    import sys
    from blackboard_sync.windows.main_window import work_area

    window = SimpleNamespace(winfo_screenwidth=lambda: 1366, winfo_screenheight=lambda: 768)
    left, top, width, height = work_area(window)
    if sys.platform == "win32":
        assert width > 0 and 0 < height
    else:
        assert (left, top, width, height) == (0, 0, 1366, 720)


def update_app(tmp_path, monkeypatch):
    import queue
    import blackboard_sync.windows.app as module

    app = make_app(tmp_path)
    app.events = queue.Queue()
    app.closed = False
    app.uninstalling = False
    app.root = SimpleNamespace(after=lambda *args: None, event_generate=lambda *args, **kw: None)
    app.poll_errors = LogThrottle()
    app.notices = []
    app.post_notifications = app.notices.extend
    workers = []
    class Thread:
        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args
        def start(self):
            workers.append(lambda: self.target(*self.args))
    monkeypatch.setattr(module.threading, 'Thread', Thread)
    return app, workers


def release():
    from blackboard_sync.updater import Release
    return Release('99.0.0', 'https://github.com/UmutYLCN/blackboard-sync/releases/tag/v99.0.0',
                   'Blackboard-Sync-99.0.0-Setup.exe',
                   'https://github.com/UmutYLCN/blackboard-sync/releases/download/v99.0.0/Blackboard-Sync-99.0.0-Setup.exe')


def drain_one(app):
    callback, args = app.events.get_nowait()
    callback(*args)


def test_update_check_worker_queues_result_for_tk_and_deduplicates(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import updater
    app, workers = update_app(tmp_path, monkeypatch)
    monkeypatch.setattr(updater, 'check', lambda: updater.CheckResult('available', release()))
    app.start_update_check(manual=False)
    app.start_update_check()
    assert len(workers) == 1
    workers.pop()()
    assert app.model.updates.available is None
    assert app.model.updates.busy == 'check'
    drain_one(app)
    assert app.model.updates.available == release()
    assert app.model.updates.busy is None
    assert app.notices[0].data == {'action': 'update'}
    assert not app.model.update_due(datetime.now(timezone.utc))


def test_update_tick_obeys_setting_and_runs_automatically(tmp_path, monkeypatch):
    app, workers = update_app(tmp_path, monkeypatch)
    app.model.configured = False
    app.model.updates.not_before = None
    app.model.check_updates = False
    app.tick()
    assert not workers
    app.model.check_updates = True
    app.tick()
    assert len(workers) == 1
    assert app.model.updates.busy == 'check'


def test_update_check_exception_recovers_row(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import updater
    app, workers = update_app(tmp_path, monkeypatch)
    def fail():
        raise RuntimeError('network')
    monkeypatch.setattr(updater, 'check', fail)
    app.start_update_check()
    workers.pop()()
    drain_one(app)
    assert app.model.updates.busy is None
    assert app.model.updates.not_before is not None
    assert app.notices[0].title == 'Güncellemeler denetlenemedi'


def test_update_install_waits_for_idle_and_quits_only_after_success(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import runtime, updater
    app, workers = update_app(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, 'is_frozen', lambda: True)
    installed, actions = [], []
    monkeypatch.setattr(updater, 'install_windows_update', installed.append)
    app.dispatch = actions.append
    app.model.updates.available = release()
    app.model.begin('sync')
    app.start_update()
    assert not workers
    app.model.busy = None
    app.start_update()
    app.start_update()
    assert len(workers) == 1
    app.start_job('sync')
    assert app.model.busy is None
    assert app.settings_submitted(FormValues('school.edu', str(tmp_path), False), False)
    workers.pop()()
    assert installed == [release()]
    assert not actions  # Worker does not touch Tk or quit.
    drain_one(app)
    assert actions == ['quit']
    assert app.model.updates.busy is None


def test_update_install_failure_preserves_app_and_allows_retry(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import runtime, updater
    app, workers = update_app(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, 'is_frozen', lambda: True)
    def fail(value):
        raise updater.UpdateError('Güncelleme doğrulanamadı.')
    monkeypatch.setattr(updater, 'install_windows_update', fail)
    app.model.updates.available = release()
    app.dispatch = lambda action: (_ for _ in ()).throw(AssertionError('Must not quit'))
    app.start_update()
    workers.pop()()
    drain_one(app)
    assert app.model.updates.busy is None
    assert app.notices[0].message == 'Güncelleme doğrulanamadı.'
    app.start_update()
    assert len(workers) == 1


def test_source_update_opens_release_without_installer(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import runtime, webbrowser
    app, workers = update_app(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, 'is_frozen', lambda: False)
    opened = []
    monkeypatch.setattr(webbrowser, 'open', opened.append)
    app.model.updates.available = release()
    app.start_update()
    assert opened == [release().page_url]
    assert not workers


def test_menu_and_toast_update_actions_dispatch(tmp_path, monkeypatch):
    import sys
    from blackboard_sync.menubar.model import UPDATE_ACTIONS
    app, workers = update_app(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, 'tkinter', SimpleNamespace(messagebox=SimpleNamespace()))
    actions = []
    app.start_update_check = lambda: actions.append('check_updates')
    app.start_update = lambda: actions.append('update')
    for action in UPDATE_ACTIONS:
        app.dispatch(action)
    app.notification_clicked({'action': 'update'})
    app.notification_clicked({'action': 'unrecognized'})
    assert actions == ['check_updates', 'update', 'update']


def test_update_setting_saved_and_applied(tmp_path, monkeypatch):
    from blackboard_sync.settings import load_settings
    app = make_app(tmp_path)
    monkeypatch.setattr(autostart, 'set_enabled', lambda enabled: None)
    assert app.settings_submitted(FormValues(app.settings.base_url, str(app.settings.dest), False, False), False) is None
    assert not app.model.check_updates
    assert not load_settings(tmp_path).check_updates


def test_update_toast_activation_is_fixed_and_consumed_on_tk(tmp_path, monkeypatch):
    from blackboard_sync.windows import activation
    from blackboard_sync.menubar.model import update_notification
    app, workers = update_app(tmp_path, monkeypatch)
    assert presentation.notification_fields(update_notification(release()))['launch'] == activation.UPDATE_URI
    activation.request_update(app.config)
    actions = []
    app.dispatch = actions.append
    app.poll()
    assert actions == ['update']
    app.poll()
    assert actions == ['update']


def test_activation_command_quotes_interpreter_and_uri(monkeypatch):
    from blackboard_sync.windows import activation
    monkeypatch.setattr(activation, 'Path', PureWindowsPath)
    monkeypatch.setattr(activation.sys, 'executable', r'C:\My App\python.exe')
    monkeypatch.setattr(activation.runtime, 'is_frozen', lambda: False)
    assert activation.protocol_command() == '"C:\\My App\\pythonw.exe" -m blackboard_sync.windows --notification "%1"'
    monkeypatch.setattr(activation.runtime, 'is_frozen', lambda: True)
    assert activation.protocol_command() == '"C:\\My App\\python.exe" --notification "%1"'


def test_second_start_asks_running_copy_to_show_its_main_window(tmp_path, monkeypatch):
    from blackboard_sync.windows import activation
    app, workers = update_app(tmp_path, monkeypatch)
    opened = []
    app.show_window = lambda section=None: opened.append(section)
    app.poll()
    assert opened == []
    activation.request_window(app.config)
    app.poll()
    assert opened == [None]  # the overview, or the section already in view
    app.poll()
    assert opened == [None]


def test_tray_settings_item_opens_the_main_window_on_genel(tmp_path, monkeypatch):
    import sys
    from blackboard_sync.menubar.main_window_model import GENERAL
    app, workers = update_app(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, 'tkinter', SimpleNamespace(messagebox=SimpleNamespace()))
    opened = []
    app.show_window = lambda section=None: opened.append(section)
    app.dispatch('settings')
    assert opened == [GENERAL]


def test_explicit_start_shows_the_window_and_login_start_stays_in_the_tray(tmp_path):
    def run(show_window, configured):
        app = make_app(tmp_path)
        app.model.configured = configured
        app.background = not show_window
        app.icon = SimpleNamespace(run_detached=lambda: None)
        scheduled = []
        app.root = SimpleNamespace(bind=lambda *a: None, mainloop=lambda: None,
                                   after=lambda ms, callback: scheduled.append(callback))
        app.run()
        return app.show_window in scheduled

    assert run(show_window=True, configured=True)  # Start menu, installer's last page
    assert not run(show_window=False, configured=True)  # login item, silent update
    assert run(show_window=False, configured=False)  # nothing set up yet


def test_closing_the_window_keeps_the_tray_and_hints_once(tmp_path):
    from blackboard_sync.windows.app import TRAY_HINT
    app = make_app(tmp_path)
    shown = []
    app.icon = SimpleNamespace(notify=lambda message, title: shown.append(message))
    window = app.window = SimpleNamespace(state=SimpleNamespace(open=False))
    app.window_closed()
    assert app.window is window  # kept hidden for the next start
    assert '^' in TRAY_HINT and 'saatin yanındaki' in TRAY_HINT
    app.window_closed()
    assert shown == [TRAY_HINT]


def test_startup_logs_before_tray_import_and_reports_errors(tmp_path, monkeypatch):
    import logging
    import sys
    import threading
    from blackboard_sync.windows import startup
    monkeypatch.setenv('BBSYNC_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv(startup.STACK_DUMP_ENV, '20')
    dumps = []
    monkeypatch.setattr(startup.faulthandler, 'enable', lambda *a, **kw: None)
    monkeypatch.setattr(startup.faulthandler, 'dump_traceback_later', lambda seconds, **kw: dumps.append(seconds))
    monkeypatch.setattr(threading, 'excepthook', threading.excepthook)
    shown = []
    monkeypatch.setattr(startup, 'show_error', shown.append)
    def broken(argv):
        raise ModuleNotFoundError("No module named 'pystray'")
    monkeypatch.setitem(sys.modules, 'blackboard_sync.windows.app', SimpleNamespace(main=broken))
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        assert startup.run([]) == 1
    finally:
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers[:], root.level = handlers, level
        startup._fault_file.close()
    path = tmp_path / 'data' / 'windows-tray.log'
    text = path.read_text(encoding='utf-8')
    assert 'Starting Blackboard Sync' in text and "No module named 'pystray'" in text
    assert dumps == [20.0]
    assert shown == [startup.error_text(path, None)] and str(path) in shown[0]
    assert 'OSError: denied' in startup.error_text(None, OSError('denied'))


def test_sign_out_from_main_window_asks_in_front_of_it(tmp_path, monkeypatch):
    import sys
    from blackboard_sync.windows.app import jobs
    app = make_app(tmp_path)
    app.root = 'root'
    asked, removed = [], []
    monkeypatch.setitem(sys.modules, 'tkinter', SimpleNamespace(messagebox=SimpleNamespace(
        askyesno=lambda title, message, parent: asked.append(parent) or True)))
    monkeypatch.setattr(jobs, 'logout', removed.append)
    app.dispatch('logout')
    app.window = SimpleNamespace(window='main', state=SimpleNamespace(open=True))
    app.dispatch('logout')
    assert asked == ['root', 'main'] and len(removed) == 2
    app.model.begin('sync')
    app.dispatch('logout')
    assert len(asked) == 2  # never while a job runs


def test_take_requests_consumes_each_request_once(tmp_path):
    from blackboard_sync.windows import activation
    config = SimpleNamespace(data_dir=tmp_path)
    assert activation.take_requests(config) == (False, False)
    activation.request_update(config)
    assert activation.take_requests(config) == (True, False)
    assert activation.take_requests(config) == (False, False)
    activation.request_update(config)
    (tmp_path / activation.WINDOW_REQUEST).touch()
    assert activation.take_requests(config) == (True, True)
    assert list(tmp_path.iterdir()) == []


def test_idle_request_check_makes_no_delete_attempts(tmp_path, monkeypatch):
    from blackboard_sync.windows import activation
    (tmp_path / 'state.json').write_text('{}')
    unlinked = []
    monkeypatch.setattr(Path, 'unlink', lambda self, *a, **kw: unlinked.append(self))
    assert activation.take_requests(SimpleNamespace(data_dir=tmp_path)) == (False, False)
    assert unlinked == []


def test_post_wakes_tk_from_the_worker_and_poll_is_slow(tmp_path, monkeypatch):
    app, workers = update_app(tmp_path, monkeypatch)
    woken, scheduled = [], []
    app.root = SimpleNamespace(event_generate=lambda *a, **kw: woken.append((a, kw)),
                               after=lambda ms, fn: scheduled.append(ms))
    ran = []
    app.post(ran.append, 'x')
    assert woken == [(('<<bbsync>>',), {'when': 'tail'})]
    assert ran == []
    app.drain()
    assert ran == ['x']
    app.poll()
    assert scheduled == [2000]  # the timer is only for the request files


def test_post_survives_a_destroyed_tk(tmp_path, monkeypatch):
    app, workers = update_app(tmp_path, monkeypatch)
    def gone(*args, **kwargs):
        raise RuntimeError('main thread is not in main loop')
    app.root = SimpleNamespace(event_generate=gone)
    app.post(lambda: None)
    assert app.events.qsize() == 1


def test_persistent_poll_error_is_logged_once_a_minute(tmp_path, monkeypatch, caplog):
    import logging
    from blackboard_sync.windows import app as module
    app, workers = update_app(tmp_path, monkeypatch)
    now = [100.0]
    app.poll_errors = LogThrottle(clock=lambda: now[0])
    def denied(config):
        raise PermissionError(13, 'denied', 'window-request')
    monkeypatch.setattr(module.activation, 'take_requests', denied)
    with caplog.at_level(logging.ERROR, logger=module.log.name):
        for _ in range(30):
            app.poll()
        assert len(caplog.records) == 1
        now[0] += 61
        app.poll()
        assert len(caplog.records) == 2


def test_log_throttle_is_per_key():
    now = [0.0]
    throttle = LogThrottle(interval=60, clock=lambda: now[0])
    assert throttle.allow('a') and not throttle.allow('a')
    assert throttle.allow('b')
    now[0] = 59.9
    assert not throttle.allow('a')
    now[0] = 60.0
    assert throttle.allow('a')


def test_tray_log_rotates_and_faults_have_their_own_file(tmp_path, monkeypatch):
    import logging
    from logging.handlers import RotatingFileHandler
    from blackboard_sync.windows import startup
    monkeypatch.setenv('BBSYNC_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr(startup.faulthandler, 'enable', lambda *a, **kw: None)
    monkeypatch.setattr(startup, 'LOG_MAX_BYTES', 2000)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        path = startup.setup_logging()
        added = [h for h in root.handlers if h not in handlers]
        assert [type(h) for h in added] == [RotatingFileHandler]
        for _ in range(100):
            logging.getLogger('t').info('x' * 100)
    finally:
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers[:], root.level = handlers, level
        startup._fault_file.close()
    names = sorted(p.name for p in path.parent.iterdir())
    assert 'windows-tray.log.1' in names and 'windows-tray-faults.log' in names
    assert max(p.stat().st_size for p in path.parent.iterdir()) < 3000
