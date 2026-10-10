"""All destructive operations use temporary paths or injected platform hooks."""

import logging
import shutil
import sys

import pytest

from blackboard_sync import cli, uninstall
from blackboard_sync.errors import AlreadyRunning, BlackboardSyncError, EXIT_LOCKED
from blackboard_sync.menubar import jobs
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock


@pytest.fixture
def hooks(config, tmp_path):
    config.ensure_data_dir()
    calls = []
    recycle = tmp_path / "recycle"
    recycle.mkdir()

    def trash(path):
        calls.append(("trash", path))
        shutil.move(str(path), str(recycle / str(len(calls))))

    return dict(send_to_trash=trash, clear_web=lambda: calls.append(("web",)),
                startup_cleanup=lambda: calls.append(("startup",)),
                app_cleanup=lambda: calls.append(("app",)) or []), calls


def record(config, *paths):
    state = State(config.state_file)
    for i, rel in enumerate(paths):
        state.record_output(str(i), rel, "hash", 10)
    state.save()


def file_at(root, rel, content="download"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_all_data_is_removed_and_course_files_kept_by_default(config, hooks, tmp_path):
    options, calls = hooks
    names = ["session.json", "settings.json", "last-run.json", "menubar.json", "menubar.log",
             "windows-tray.log", "windows-tray-faults.log", "menubar.lock", "sync.lock",
             "state.json.corrupt-old", "tray-hint-shown", "update-request"]
    for name in names:
        file_at(config.data_dir, name)
    for name in ("browser-profile", "inapp-profile", "unknown-future-app-data"):
        file_at(config.data_dir, name + "/nested/storage")
    outside = file_at(tmp_path, "outside/keep")
    if sys.platform != "win32":
        (config.data_dir / "linked-profile").symlink_to(outside.parent, target_is_directory=True)
    course = file_at(config.dest, "Term/Course/slides.pdf")
    record(config, "Term/Course/slides.pdf")
    assert uninstall.uninstall(config, **options) == []
    assert list(config.data_dir.iterdir()) == []
    assert course.exists() and outside.exists()
    assert calls == [("web",), ("startup",), ("app",)]


def test_only_recorded_files_and_empty_parents_are_trashed(config, hooks):
    options, calls = hooks
    owned = file_at(config.dest, "Term/Course/Unit/slides.pdf")
    unrelated = file_at(config.dest, "Term/Course/my-notes.txt")
    empty_course = file_at(config.dest, "Old/Other/handout.pptx")
    unrecorded_empty = config.dest / "Empty-unrelated"
    unrecorded_empty.mkdir()
    record(config, "Term/Course/Unit/slides.pdf", "Old/Other/handout.pptx")
    assert uninstall.uninstall(config, True, **options) == []
    trashed = [call[1] for call in calls if call[0] == "trash"]
    assert set(trashed) == {owned, owned.parent, empty_course, empty_course.parent, config.dest / "Old"}
    assert unrelated.read_text() == "download"
    assert config.dest.is_dir() and unrecorded_empty.is_dir()
    assert list(config.data_dir.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require Windows privileges")
def test_replaced_directory_and_unsafe_state_paths_survive(config, hooks, tmp_path):
    options, calls = hooks
    outside = file_at(tmp_path, "outside/precious.pdf")
    linked = config.dest / "Term/Link"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(outside.parent, target_is_directory=True)
    leaf = config.dest / "leaf.pdf"
    leaf.symlink_to(outside)
    replacement = file_at(config.dest, "Term/Course/replaced.pdf/user-file")
    record(config, "../outside/precious.pdf", str(outside), "Term/Link/precious.pdf",
           "leaf.pdf", "Term/Course/replaced.pdf", "C:/outside/file.pdf", "Term/../leaf.pdf",
           "Term\\Course\\file.pdf", "bad\0file.pdf")
    assert uninstall.uninstall(config, True, **options) == []
    assert outside.exists() and leaf.is_symlink() and linked.is_symlink() and replacement.exists()
    assert not any(call[0] == "trash" for call in calls)


def test_uninstall_refuses_live_sync_or_move_lock(config, hooks):
    options, calls = hooks
    course = file_at(config.dest, "Term/Course/file.pdf")
    record(config, "Term/Course/file.pdf")
    original = config.state_file.read_bytes()
    with run_lock(config.lock_file):
        with pytest.raises(AlreadyRunning, match="senkronizasyonun"):
            uninstall.uninstall(config, True, before_cleanup=lambda: calls.append(("prepare",)), **options)
    assert calls == [] and config.state_file.read_bytes() == original and course.exists()


def test_cli_refuses_running_gui_to_prevent_data_being_recreated(config, hooks):
    options, calls = hooks
    lock = jobs.single_instance(config)
    try:
        with pytest.raises(AlreadyRunning, match="Önce Blackboard"):
            uninstall.uninstall(config, **options)
        assert not calls
    finally:
        lock.close()


def test_gui_closes_handles_only_after_taking_run_lock(config, hooks):
    options, calls = hooks
    lock = jobs.single_instance(config)

    def prepare():
        with pytest.raises(AlreadyRunning):
            with run_lock(config.lock_file):
                pass
        lock.close()
        calls.append(("prepare",))

    assert uninstall.uninstall(config, owns_app_lock=True, before_cleanup=prepare, **options) == []
    assert calls[0] == ("prepare",) and lock.closed
    assert list(config.data_dir.iterdir()) == []


def test_trash_failure_keeps_file_but_finishes_data_and_app_cleanup(config, hooks):
    options, calls = hooks
    owned = file_at(config.dest, "Term/Course/file.pdf")
    record(config, "Term/Course/file.pdf")

    def fail(path):
        raise PermissionError("denied")

    options["send_to_trash"] = fail
    warnings = uninstall.uninstall(config, True, **options)
    assert "Dosya Çöp Sepeti" in warnings[0]
    assert owned.exists() and list(config.data_dir.iterdir()) == []
    assert calls[-1] == ("app",)


def test_corrupt_state_keeps_courses_but_cleans_data(config, hooks):
    options, calls = hooks
    file_at(config.data_dir, "state.json", "not json")
    course = file_at(config.dest, "Term/Course/file.pdf")
    warnings = uninstall.uninstall(config, True, **options)
    assert "kayıtları okunamadı" in warnings[0]
    assert course.exists() and not list(config.data_dir.iterdir())


def test_app_removal_failure_is_reported_after_cleanup(config, hooks):
    options, calls = hooks
    file_at(config.data_dir, "session.json")

    def fail():
        assert not list(config.data_dir.iterdir())
        raise PermissionError("denied")

    options["app_cleanup"] = fail
    assert "elle silin" in uninstall.uninstall(config, **options)[0]
    assert ("startup",) in calls and ("web",) in calls


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require Windows privileges")
def test_symlink_lock_is_not_opened_or_followed(config, hooks, tmp_path):
    options, calls = hooks
    target = file_at(tmp_path, "keep", "untouched")
    config.lock_file.symlink_to(target)
    with pytest.raises(BlackboardSyncError, match="bağlantı"):
        uninstall.uninstall(config, **options)
    assert target.read_text() == "untouched" and calls == []


def test_cli_flag_and_lock_exit_code(config, monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "make_config", lambda _: config)
    monkeypatch.setattr(uninstall, "uninstall", lambda config, delete_course_files: called.append(delete_course_files) or [])
    assert cli.main(["uninstall"]) == 0
    assert cli.main(["uninstall", "--delete-course-files"]) == 0
    assert called == [False, True]

    def locked(*args, **kwargs):
        raise AlreadyRunning(uninstall.BUSY)

    monkeypatch.setattr(uninstall, "uninstall", locked)
    assert cli.main(["uninstall"]) == EXIT_LOCKED
    assert uninstall.BUSY in capsys.readouterr().err


def test_macos_removes_the_running_bundle_and_reports_trash_failure(tmp_path, monkeypatch):
    bundle = tmp_path / "Blackboard Sync.app"
    executable = bundle / "Contents/MacOS/Blackboard Sync"
    executable.parent.mkdir(parents=True)
    monkeypatch.setattr(uninstall.runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(uninstall.sys, "platform", "darwin")
    monkeypatch.setattr(uninstall.sys, "executable", str(executable))
    trashed = []
    monkeypatch.setattr(uninstall, "trash", trashed.append)
    assert uninstall.remove_app() == [] and trashed == [bundle]

    def denied(path):
        raise PermissionError("denied")

    monkeypatch.setattr(uninstall, "trash", denied)
    warnings = uninstall.remove_app()
    assert "Finder" in warnings[0] and str(bundle) in warnings[0]


def test_windows_invokes_inno_uninstaller_and_reports_missing(tmp_path, monkeypatch):
    executable = tmp_path / "Blackboard Sync.exe"
    installer = file_at(tmp_path, "unins000.exe")
    monkeypatch.setattr(uninstall.runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(uninstall.sys, "platform", "win32")
    monkeypatch.setattr(uninstall.sys, "executable", str(executable))
    launched = []
    monkeypatch.setattr(uninstall.subprocess, "Popen", lambda command, **kw: launched.append(command))
    assert uninstall.remove_app() == []
    assert launched[0][0] == str(installer)
    installer.unlink()
    assert "Windows Ayarlar" in uninstall.remove_app()[0]


def test_startup_cleanup_uses_existing_platform_helpers(monkeypatch):
    from blackboard_sync.menubar import launchagent
    from blackboard_sync.windows import autostart
    calls = []
    monkeypatch.setattr(launchagent, "remove", lambda: calls.append("mac"))
    monkeypatch.setattr(autostart, "set_enabled", lambda value: calls.append(value))
    monkeypatch.setattr(uninstall.sys, "platform", "darwin")
    uninstall.remove_startup()
    monkeypatch.setattr(uninstall.sys, "platform", "win32")
    uninstall.remove_startup()
    assert calls == ["mac", False]


def test_windows_closes_fault_and_rotating_log_handles(tmp_path, monkeypatch):
    from blackboard_sync.windows import startup
    logger = logging.getLogger("uninstall-test")
    handler = logging.FileHandler(tmp_path / "log")
    stream = handler.stream
    logger.addHandler(handler)
    fault = open(tmp_path / "fault", "w")
    monkeypatch.setattr(startup, "_fault_file", fault)
    monkeypatch.setattr(startup.faulthandler, "disable", lambda: None)
    monkeypatch.setattr(startup.faulthandler, "cancel_dump_traceback_later", lambda: None)
    startup.close_logging()
    assert fault.closed and stream.closed and handler not in logger.handlers


def test_webkit_cleanup_waits_for_completion_before_uninstall_can_quit(monkeypatch):
    import sys
    from types import SimpleNamespace
    from blackboard_sync import signout

    callbacks, runs = [], []
    store = SimpleNamespace(removeDataOfTypes_modifiedSince_completionHandler_=lambda types, date, cb: callbacks.append(cb))

    def advance(date):
        runs.append(date)
        callbacks.pop()()

    monkeypatch.setattr(signout.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "WebKit", SimpleNamespace(WKWebsiteDataStore=SimpleNamespace(
        defaultDataStore=lambda: store, allWebsiteDataTypes=lambda: "all")))
    monkeypatch.setitem(sys.modules, "Foundation", SimpleNamespace(
        NSDate=SimpleNamespace(distantPast=lambda: "past", dateWithTimeIntervalSinceNow_=lambda seconds: seconds),
        NSRunLoop=SimpleNamespace(currentRunLoop=lambda: SimpleNamespace(runUntilDate_=advance))))
    signout.clear_webkit_data()
    assert runs == [0.05] and callbacks == []


def test_windows_cancel_leaves_everything_untouched(config, monkeypatch):
    from types import SimpleNamespace
    from blackboard_sync.windows import app as module, main_window

    app = module.TrayApp.__new__(module.TrayApp)
    app.config, app.settings = config, SimpleNamespace(dest=config.dest)
    app.model = SimpleNamespace(busy=None, updates=SimpleNamespace(busy=None))
    app.root, app.window = object(), None
    app.uninstalling = False
    monkeypatch.setattr(main_window, "ask_uninstall", lambda *args: None)
    monkeypatch.setattr(uninstall, "uninstall", lambda *args, **kw: pytest.fail("cancel must not clean up"))
    app.start_uninstall()
    assert not app.uninstalling


@pytest.mark.parametrize("busy", ["sync", "move"])
def test_windows_busy_refuses_before_confirmation(config, monkeypatch, busy):
    from types import SimpleNamespace
    from tkinter import messagebox
    from blackboard_sync.windows import app as module, main_window

    app = module.TrayApp.__new__(module.TrayApp)
    app.config, app.settings = config, SimpleNamespace(dest=config.dest)
    app.model = SimpleNamespace(busy=busy, updates=SimpleNamespace(busy=None))
    app.root, app.window = object(), None
    shown = []
    monkeypatch.setattr(main_window, "ask_uninstall", lambda *args: pytest.fail("must refuse before asking"))
    monkeypatch.setattr(messagebox, "showinfo", lambda title, text, **kw: shown.append(text))
    app.start_uninstall()
    assert shown == [uninstall.BUSY]


@pytest.mark.parametrize("choice", [None, False, True])
def test_mac_confirmation_defaults_to_keep_and_reveals_path(config, monkeypatch, choice):
    pytest.importorskip("AppKit")
    from types import SimpleNamespace
    from blackboard_sync.menubar import main_window as window

    class Alert:
        def init(self):
            return self

        def setMessageText_(self, title):
            assert title == uninstall.TITLE

        def setInformativeText_(self, message):
            assert message == uninstall.MESSAGE

        def addButtonWithTitle_(self, title):
            return SimpleNamespace(setKeyEquivalent_=lambda key: None)

        def setAccessoryView_(self, view):
            self.view = view

        def runModal(self):
            checkbox, label = list(self.view.subviews())
            assert checkbox.state() == 0 and label.isHidden()
            assert str(config.dest) in label.stringValue()
            if choice:
                checkbox.setState_(1)
                checkbox.target().changed_(checkbox)
                assert not label.isHidden()
            return window.NSAlertFirstButtonReturn + int(choice is None)

    monkeypatch.setattr(window, "NSAlert", SimpleNamespace(alloc=Alert))
    monkeypatch.setattr(window, "NSApp", SimpleNamespace(activateIgnoringOtherApps_=lambda flag: None))
    assert window.ask_uninstall(config.dest) is choice


@pytest.mark.parametrize("delete_files", [False, True])
def test_windows_confirmation_cleans_then_removes_app_and_quits(config, monkeypatch, delete_files):
    from types import SimpleNamespace
    from tkinter import messagebox
    from blackboard_sync.windows import app as module, main_window

    calls = []
    app = module.TrayApp.__new__(module.TrayApp)
    app.config, app.settings = config, SimpleNamespace(dest=config.dest)
    app.model = SimpleNamespace(busy=None, updates=SimpleNamespace(busy=None))
    app.root = SimpleNamespace(destroy=lambda: calls.append("quit"))
    app.icon = SimpleNamespace(stop=lambda: calls.append("stop"))
    app.window = None
    app.uninstalling, app.closed = False, False
    app.prepare_uninstall = lambda: calls.append("prepare")
    monkeypatch.setattr(main_window, "ask_uninstall", lambda *args: delete_files)

    def cleanup(config, flag, **kwargs):
        assert flag is delete_files and kwargs["owns_app_lock"]
        kwargs["before_cleanup"]()
        calls.append("data")
        return ["data warning"]

    monkeypatch.setattr(uninstall, "uninstall", cleanup)
    monkeypatch.setattr(uninstall, "remove_app", lambda: calls.append("app") or ["manual app removal"])
    monkeypatch.setattr(messagebox, "showwarning", lambda title, text, **kw: calls.append(text))
    app.start_uninstall()
    assert calls == ["prepare", "data", "data warning", "app", "manual app removal", "stop", "quit"]
    assert app.closed and app.uninstalling


@pytest.mark.parametrize("recyclable", [True, False])
def test_windows_trash_vetoes_permanent_delete(config, monkeypatch, recyclable):
    from types import SimpleNamespace
    from blackboard_sync.windows import trash

    calls = []

    class ComError(Exception):
        pass

    class ComException(ComError):
        def __init__(self, message, scode):
            super().__init__(message)
            assert scode == trash.E_ABORT

    class Sink:
        pass

    class Operation:
        def SetOperationFlags(self, flags):
            assert flags & 0x00080000  # recycle on delete
            assert flags & 0x2000  # do not delete associated files

        def DeleteItem(self, item, sink):
            self.sink = sink

        def PerformOperations(self):
            self.sink.PreDeleteItem(trash.RECYCLE_IF_POSSIBLE if recyclable else 0, None)
            calls.append("recycle")
            return 0

        def GetAnyOperationsAborted(self):
            return False

    monkeypatch.setitem(sys.modules, "pythoncom", SimpleNamespace(
        CoInitialize=lambda: calls.append("init"), CoUninitialize=lambda: calls.append("uninit"),
        CoCreateInstance=lambda *args: Operation(), CLSCTX_ALL=0, WrapObject=lambda sink, iid: sink))
    monkeypatch.setitem(sys.modules, "pywintypes", SimpleNamespace(com_error=ComError))
    monkeypatch.setitem(sys.modules, "win32com.shell", SimpleNamespace(shell=SimpleNamespace(
        CLSID_FileOperation=0, IID_IFileOperation=0, IID_IShellItem=0, IID_IFileOperationProgressSink=0,
        SHCreateItemFromParsingName=lambda *args: None)))
    monkeypatch.setitem(sys.modules, "win32com.server.exception", SimpleNamespace(COMException=ComException))
    monkeypatch.setitem(sys.modules, "send2trash.win.IFileOperationProgressSink", SimpleNamespace(FileOperationProgressSink=Sink))
    if recyclable:
        trash.recycle(config.dest / "file.pdf")
        assert calls == ["init", "recycle", "uninit"]
    else:
        with pytest.raises(OSError):
            trash.recycle(config.dest / "file.pdf")
        assert calls == ["init", "uninit"]
