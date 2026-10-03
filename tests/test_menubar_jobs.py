import json
import plistlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs, launchagent
from blackboard_sync.menubar.model import Icon

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


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
    result = jobs.run_sync(runner, now=lambda: NOW)
    cmd, kwargs = runner.calls[0]
    assert cmd == [sys.executable, "-m", "blackboard_sync", "sync", "--json"]
    assert kwargs["capture_output"] and kwargs["stdin"] == subprocess.DEVNULL
    assert result.status == "ok" and result.finished_at == NOW


def test_sync_respects_cli_exit_codes():
    assert jobs.run_sync(fake_runner(returncode=3), now=lambda: NOW).status == "login_required"
    assert jobs.run_sync(fake_runner(returncode=4), now=lambda: NOW).status == "locked"


def test_hung_sync_becomes_an_error():
    runner = fake_runner(raises=subprocess.TimeoutExpired("x", 1))
    assert jobs.run_sync(runner, now=lambda: NOW).status == "error"


def test_login_result():
    assert jobs.run_login(fake_runner(returncode=0)) == (True, "")
    assert jobs.run_login(fake_runner(returncode=1, stderr="Error: The browser did not start.\n")) == (
        False,
        "Error: The browser did not start.",
    )


def test_model_is_restored_from_last_run_and_saved_state(tmp_path):
    config = Config(data_dir=tmp_path / "data", dest=tmp_path / "Okul")
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
    assert (jobs.menubar_state_file(config).stat().st_mode & 0o777) == 0o600
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
        "/py", Path("/log"), env={"BBSYNC_DEST": "/Okul", "HOME": "/Users/x"}
    )
    assert plist["EnvironmentVariables"] == {"BBSYNC_DEST": "/Okul"}
    assert "EnvironmentVariables" not in launchagent.build_plist("/py", Path("/log"), env={})
