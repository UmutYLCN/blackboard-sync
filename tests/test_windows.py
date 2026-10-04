"""Windows adapters must remain importable and testable without a Windows GUI."""

import base64
import re
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from blackboard_sync.menubar.model import AppModel, CourseChange, RunOutcome, changes_notification
from blackboard_sync.menubar.settings_form import FormValues
from blackboard_sync.settings import Settings
from blackboard_sync.windows import autostart, notifications, presentation
from blackboard_sync.windows.app import TrayApp, cli_runner


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
    assert autostart.command(r'C:\Program Files\Python\pythonw.exe') == '"C:\\Program Files\\Python\\pythonw.exe" -m blackboard_sync.windows'


def test_default_run_command_uses_pythonw(monkeypatch):
    monkeypatch.setattr(autostart, 'Path', PureWindowsPath)
    monkeypatch.setattr(autostart.sys, 'executable', r'C:\My App\.venv\Scripts\python.exe')
    assert autostart.command().startswith('"C:\\My App\\.venv\\Scripts\\pythonw.exe"')


def test_frozen_run_command_is_the_installed_exe(monkeypatch):
    monkeypatch.setattr(autostart.runtime, 'is_frozen', lambda: True)
    monkeypatch.setattr(autostart.sys, 'executable', r'C:\Users\Ada\AppData\Local\Programs\Blackboard Sync\Blackboard Sync.exe')
    assert autostart.command() == '"C:\\Users\\Ada\\AppData\\Local\\Programs\\Blackboard Sync\\Blackboard Sync.exe"'


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
    app.config = SimpleNamespace(data_dir=tmp_path)
    app.settings = Settings('https://old.school.edu', tmp_path / 'old')
    app.model = AppModel(app.settings.dest, datetime.now(timezone.utc))
    app.save = lambda: None
    app.refresh = lambda: None
    return app


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


def test_settings_registry_failure_keeps_window_open(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    def denied(enabled):
        raise PermissionError('Denied')
    monkeypatch.setattr(autostart, 'set_enabled', denied)
    values = FormValues(app.settings.base_url, str(app.settings.dest), True)
    assert 'kaydedilemedi' in app.settings_submitted(values, False)[0]
    assert not (tmp_path / 'settings.json').exists()


def test_windows_intro_and_fields():
    from blackboard_sync.windows.settings_window import INTRO
    from blackboard_sync.menubar import settings_form
    assert "Mac" not in INTRO
    assert 'Giriş yap' in INTRO
    assert settings_form.T_URL_LABEL and settings_form.T_DEST_LABEL


def test_pythonw_parent_runs_hidden_console_child(monkeypatch):
    import blackboard_sync.windows.app as app_module
    calls = []
    monkeypatch.setattr(app_module, 'Path', PureWindowsPath)
    monkeypatch.setattr(app_module.subprocess, 'run', lambda cmd, **kw: calls.append(cmd))
    cli_runner([r'C:\App\.venv\Scripts\pythonw.exe', '-m', 'blackboard_sync'])
    assert calls == [[r'C:\App\.venv\Scripts\python.exe', '-m', 'blackboard_sync']]


def test_windows_settings_window_layout_and_validation(monkeypatch, tmp_path):
    import sys
    from blackboard_sync.windows.settings_window import SettingsWindow, INTRO
    widgets = []

    class Widget:
        def __init__(self, *args, **kwargs):
            self.options = kwargs
            self.focused = False
            self.destroyed = False
            widgets.append(self)
        def grid(self, **kwargs):
            self.grid_options = kwargs
        def pack(self, **kwargs):
            pass
        def columnconfigure(self, *args, **kwargs):
            pass
        def title(self, text):
            self.caption = text
        def minsize(self, *args):
            pass
        def protocol(self, *args):
            pass
        def configure(self, **kwargs):
            self.options.update(kwargs)
        def focus_set(self):
            self.focused = True
        def deiconify(self):
            pass
        def lift(self):
            pass
        def focus_force(self):
            pass
        def destroy(self):
            self.destroyed = True

    class Variable:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value

    ttk = SimpleNamespace(**{name: Widget for name in ('Frame', 'Label', 'Entry', 'Button', 'Checkbutton')})
    fake = SimpleNamespace(Toplevel=Widget, StringVar=Variable, BooleanVar=Variable, ttk=ttk,
                           filedialog=SimpleNamespace(askdirectory=lambda **kw: str(tmp_path)))
    monkeypatch.setitem(sys.modules, 'tkinter', fake)
    submitted, closed = [], []
    def submit(values, login):
        submitted.append((values, login))
        return ('Geçerli bir adres yazın.', 'base_url') if len(submitted) == 1 else None
    window = SettingsWindow(None, FormValues('school.edu', str(tmp_path), True), True,
                            submit, lambda: closed.append(True))
    labels = [w.options.get('text') for w in widgets]
    assert INTRO in labels
    assert all(label in labels for label in ('Okulunuzun Blackboard adresi',
        'Dosyaların kaydedileceği klasör', 'Bilgisayar açılınca başlat', 'Güncellemeleri otomatik denetle', 'Kaydet', 'Giriş yap', 'Vazgeç', 'Seç…'))
    assert window.fields['base_url'].grid_options['sticky'] == 'ew'
    login = next(w for w in widgets if w.options.get('text') == 'Giriş yap')
    login.options['command']()
    assert window.fields['base_url'].focused
    assert not window.window.destroyed
    assert window.error.options['text'] == 'Geçerli bir adres yazın.'
    window.check_updates.set(False)
    login.options['command']()
    assert submitted[-1][0].check_updates is False
    assert submitted[-1][1] is True
    assert closed == [True]
    assert window.window.destroyed


def update_app(tmp_path, monkeypatch):
    import queue
    import blackboard_sync.windows.app as module

    app = make_app(tmp_path)
    app.events = queue.Queue()
    app.closed = False
    app.root = SimpleNamespace(after=lambda *args: None)
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
