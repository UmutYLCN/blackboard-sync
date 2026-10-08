import json
import os
import plistlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from blackboard_sync import runtime
from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs, launchagent
from blackboard_sync.menubar.model import Icon
from blackboard_sync.settings import Settings, save_settings

from .conftest import assert_owner_only

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
# Absolute on every OS ("/Users/..." has no drive letter on Windows).
SETTINGS = Settings(base_url="https://bb.example.edu", dest=Path(os.path.abspath("/Users/student/University")))


def fake_runner(returncode=0, stdout="", stderr="", raises=None):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    run.calls = calls
    return run


def test_sync_runs_the_cli_json_mode():
    runner = fake_runner(stdout=json.dumps({"status": "ok", "courses": []}))
    result = jobs.run_sync("sync", SETTINGS, runner=runner, now=lambda: NOW)
    cmd, kwargs = runner.calls[0]
    assert cmd == [
        sys.executable, "-m", "blackboard_sync",
        "--base-url", "https://bb.example.edu", "sync", "--json", "--dest", str(SETTINGS.dest),
    ]
    assert kwargs["capture_output"] and kwargs["stdin"] == subprocess.DEVNULL
    assert result.status == "ok" and result.finished_at == NOW


def test_refetch_job_passes_refetch_missing():
    runner = fake_runner(stdout=json.dumps({"status": "ok", "courses": []}))
    jobs.run_sync("refetch", SETTINGS, runner=runner, now=lambda: NOW)
    assert runner.calls[0][0][-1] == "--refetch-missing"


def test_sync_respects_cli_exit_codes():
    assert jobs.run_sync("sync", SETTINGS, fake_runner(returncode=3), lambda: NOW).status == "login_required"
    assert jobs.run_sync("sync", SETTINGS, fake_runner(returncode=4), lambda: NOW).status == "locked"


def test_hung_sync_becomes_an_error():
    runner = fake_runner(raises=subprocess.TimeoutExpired("x", 1))
    assert jobs.run_sync("sync", SETTINGS, runner=runner, now=lambda: NOW).status == "error"


def test_login_result():
    runner = fake_runner(returncode=0)
    assert jobs.run_login(SETTINGS, runner) == (True, "")
    assert runner.calls[0][0][-3:] == ["--base-url", "https://bb.example.edu", "login"]
    assert jobs.run_login(SETTINGS, fake_runner(returncode=1, stderr="Error: The browser did not start.\n")) == (
        False,
        "Error: The browser did not start.",
    )


def test_login_method_is_the_browser_or_the_app_window(tmp_path, monkeypatch):
    from blackboard_sync import login as login_mod

    monkeypatch.setattr(login_mod, "APP_DIRS", [tmp_path])
    assert jobs.login_method(platform="darwin") == "inapp"
    (tmp_path / "Vivaldi.app").mkdir()
    assert jobs.login_method(platform="darwin") == "Vivaldi"


def test_model_is_restored_from_last_run_and_saved_state(tmp_path):
    config = Config(data_dir=tmp_path / "data", dest=tmp_path / "University")
    config.ensure_data_dir()
    folder = "2026-2027 Güz/CSE303 Algorithm Analysis"
    config.last_run_file.write_text(
        json.dumps(
            {
                "status": "login_required",
                "finished_at": "2026-10-03T11:00:00+00:00",
                "courses": [],
            }
        )
    )
    model = jobs.load_model(config, NOW, autostart=False)
    assert model.icon() == Icon.EXPIRED and model.recent == []

    # First start after a terminal sync: its new files seed "Son indirilenler".
    config.last_run_file.write_text(
        json.dumps(
            {
                "status": "ok",
                "finished_at": "2026-10-03T11:00:00+00:00",
                "courses": [{"code": "CSE303", "folder": folder, "new_files": [f"{folder}/a.pdf"]}],
            }
        )
    )
    model = jobs.load_model(config, NOW, autostart=True)
    assert [r.path for r in model.recent] == [f"{folder}/a.pdf"]
    assert model.autostart is True

    model.login_prompted = True
    jobs.save_model(config, model)
    assert_owner_only(jobs.menubar_state_file(config))
    restored = jobs.load_model(config, NOW, autostart=False)
    assert restored.login_prompted is True
    assert [r.path for r in restored.recent] == [f"{folder}/a.pdf"]


def test_dry_run_summary_is_ignored(tmp_path):
    config = Config(data_dir=tmp_path)
    config.last_run_file.write_text(json.dumps({"status": "ok", "dry_run": True}))
    assert jobs.load_last_run(config) is None


def test_only_one_app_instance(tmp_path):
    config = Config(data_dir=tmp_path)
    first = jobs.single_instance(config)
    assert first is not None
    assert jobs.single_instance(config) is None
    first.close()
    assert jobs.single_instance(config) is not None


def test_launch_agent_install_and_remove(tmp_path):
    agents = tmp_path / "LaunchAgents"
    assert not launchagent.is_installed(agents)
    path = launchagent.install(tmp_path / "menubar.log", agents_dir=agents, python="/repo/.venv/bin/python")
    assert launchagent.is_installed(agents)
    plist = plistlib.loads(path.read_bytes())
    assert plist["Label"] == launchagent.LABEL
    assert plist["ProgramArguments"] == ["/repo/.venv/bin/python", "-m", "blackboard_sync.menubar"]
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert launchagent.remove(agents) is True
    assert not launchagent.is_installed(agents)
    assert launchagent.remove(agents) is False


def test_launch_agent_keeps_custom_settings():
    plist = launchagent.build_plist(
        ["/py"], Path("/log"), env={"BBSYNC_DEST": "/University", "HOME": "/Users/x"}
    )
    assert plist["EnvironmentVariables"] == {"BBSYNC_DEST": "/University"}
    assert "EnvironmentVariables" not in launchagent.build_plist(["/py"], Path("/log"), env={})


def test_frozen_app_reinvokes_its_own_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Blackboard Sync.app/Contents/MacOS/Blackboard Sync")
    exe = sys.executable
    assert jobs.cli_command("sync", "--json") == [exe, "sync", "--json"]
    assert runtime.menubar_command() == [exe]
    plist = launchagent.build_plist(runtime.menubar_command(), Path("/log"), env={})
    assert plist["ProgramArguments"] == [exe]


def test_saved_settings_decide_what_the_app_syncs(tmp_path):
    config = Config(base_url="https://env.example.edu", data_dir=tmp_path / "data", dest=tmp_path / "University")
    assert jobs.saved_settings(config) is None
    assert jobs.effective_settings(config) == Settings("https://env.example.edu", tmp_path / "University")
    assert jobs.load_model(config, NOW, autostart=False).configured is False

    save_settings(config.data_dir, SETTINGS)
    assert jobs.effective_settings(config) == SETTINGS
    model = jobs.load_model(config, NOW, autostart=False)
    assert model.configured is True and model.dest == SETTINGS.dest


def test_packaged_app_runs_cli_when_the_school_comes_first(monkeypatch):
    import importlib.util

    path = Path(__file__).parent.parent / "packaging" / "app_entry.py"
    spec = importlib.util.spec_from_file_location("app_entry", path)
    app_entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_entry)
    called = []
    monkeypatch.setattr("blackboard_sync.cli.main", lambda args: called.append(("cli", args)) or 0)
    monkeypatch.setattr("blackboard_sync.menubar.app.main", lambda args: called.append(("menubar", args)) or 0)
    for args in (["--base-url", "https://bb.example.edu", "login"], ["--base-url=https://x.edu", "sync"], ["sync"], ["past-terms"]):
        monkeypatch.setattr(sys, "argv", ["Blackboard Sync", *args])
        app_entry.main()
    monkeypatch.setattr("blackboard_sync.windows.startup.run", lambda args: called.append(("tray", args)) or 0)
    monkeypatch.setattr(sys, "argv", ["Blackboard Sync", "--detach"])
    monkeypatch.setattr(sys, "platform", "darwin")
    app_entry.main()
    monkeypatch.setattr(sys, "platform", "win32")
    app_entry.main()
    assert [kind for kind, _ in called] == ["cli", "cli", "cli", "cli", "menubar", "tray"]


def test_session_evidence_and_logout_preserve_files(config):
    from blackboard_sync.session import save_session
    config.ensure_data_dir()
    config.dest.mkdir(parents=True, exist_ok=True)
    downloaded = config.dest / "lecture.pdf"
    downloaded.write_bytes(b"downloaded")
    config.state_file.write_text('{"keep": true}')
    save_session(config.session_file, config.base_url,
                 [{"name": "auth", "value": "test", "domain": "blackboard.example.edu"}],
                 {"id": "1", "userName": "ada", "name": {"given": "Ada", "family": "Student"}})
    model = jobs.load_model(config, NOW, False)
    assert model.menu(NOW).entries[0].title == "✓ Ada Student · henüz senkronize edilmedi"
    jobs.logout(config)
    jobs.refresh_session(config, model, jobs.effective_settings(config))
    assert model.menu(NOW).entries[0].action == "login"
    assert not config.session_file.exists()
    assert downloaded.read_bytes() == b"downloaded"
    assert config.state_file.read_text() == '{"keep": true}'
    jobs.logout(config)  # already removed


def test_courses_and_expiry_survive_restart_after_error(config):
    from blackboard_sync.menubar.model import CourseChange, RunOutcome
    model = jobs.load_model(config, NOW, False)
    model.courses = [CourseChange("CSE303", "course", {"new_files": 2}, [])]
    model.finish_sync(RunOutcome("login_required", finished_at=NOW), NOW)
    model.finish_sync(RunOutcome("error", finished_at=NOW), NOW)
    jobs.save_model(config, model)
    restored = jobs.load_model(config, NOW, False)
    assert restored.courses == model.courses
    assert restored.menu(NOW).entries[0].warning


def test_unexpected_exception_in_a_sync_worker_still_clears_busy(monkeypatch):
    from blackboard_sync.menubar.model import AppModel

    def boom(*args, **kwargs):
        raise ValueError("unexpected")

    monkeypatch.setattr(jobs, "run_sync", boom)
    model = AppModel(SETTINGS.dest, NOW)
    assert model.begin("sync")
    outcome = jobs.run_sync_guarded("sync", SETTINGS)
    assert outcome.status == "error" and "unexpected" in outcome.message
    model.finish_sync(outcome, NOW)
    assert model.busy is None
    assert model.begin("sync")  # the next job can start


def test_unexpected_exception_in_a_login_worker_still_clears_busy(monkeypatch):
    from blackboard_sync.menubar.model import AppModel

    def boom(*args, **kwargs):
        raise ValueError("unexpected")

    monkeypatch.setattr(jobs, "run_login", boom)
    model = AppModel(SETTINGS.dest, NOW)
    assert model.begin("login")
    ok, message = jobs.run_login_guarded(SETTINGS)
    assert not ok and "unexpected" in message
    model.finish_login(ok, message, NOW)
    assert model.busy is None


def test_selected_refetch_uses_selection_file_and_cleans_it_up():
    selections = []
    paths = []
    def runner(cmd, **kwargs):
        path = Path(cmd[cmd.index('--refetch-selection') + 1])
        paths.append(path)
        selections.append(json.loads(path.read_text()))
        assert '--refetch-missing' in cmd
        return subprocess.CompletedProcess(cmd, 0, '{"status": "ok"}', '')
    assert jobs.run_sync('refetch', SETTINGS, runner=runner,
                         refetch_keys=['attachment:course:one', 'note:course:two']).status == 'ok'
    assert selections == [['attachment:course:one', 'note:course:two']]
    assert not paths[0].exists()


def test_selected_refetch_removes_selection_file_after_timeout():
    paths = []
    def runner(cmd, **kwargs):
        paths.append(Path(cmd[cmd.index('--refetch-selection') + 1]))
        raise subprocess.TimeoutExpired(cmd, 1)
    assert jobs.run_sync('refetch', SETTINGS, runner=runner, refetch_keys=['key']).status == 'error'
    assert not paths[0].exists()
