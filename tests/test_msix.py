"""The MSIX (Store) build: package layout, and start-at-login with and without package identity."""

import importlib.util
import logging
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from blackboard_sync.windows import activation, autostart, notifications, package

ROOT = Path(__file__).resolve().parent.parent
NS = {
    "m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    "uap3": "http://schemas.microsoft.com/appx/manifest/uap/windows10/3",
    "uap5": "http://schemas.microsoft.com/appx/manifest/uap/windows10/5",
    "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
}


def load_make_layout():
    spec = importlib.util.spec_from_file_location("make_layout", ROOT / "packaging" / "msix" / "make_layout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_layout = load_make_layout()
IDENTITY = {
    "name": "UmutYLCN.blackboard-sync",
    "publisher": "CN=32397A73-9242-4378-90EB-34A15F7502AE",
    "publisher_display_name": "UmutYLCN",
    "display_name": "blackboard-sync",
    "visual_display_name": "Blackboard Sync",
}


class Packaged:
    """Stands in for the WinRT side of ``package``: one startup task."""

    def __init__(self, monkeypatch, state=package.DISABLED, kind=None):
        self.state, self.kind, self.calls = state, kind, []
        monkeypatch.setattr(package, "is_packaged", lambda: True)
        monkeypatch.setattr(package, "startup_task_state", self.get)
        monkeypatch.setattr(package, "set_startup_task", self.set)
        monkeypatch.setattr(package, "activation_kind", self.activation)
        monkeypatch.setattr(autostart, "_value", self.registry)
        monkeypatch.setattr(autostart.runtime, "is_frozen", lambda: True)

    def get(self, task_id):
        assert task_id == autostart.TASK_ID
        return self.state

    def set(self, task_id, enabled):
        assert task_id == autostart.TASK_ID
        self.calls.append(enabled)
        if self.state in (package.DISABLED, package.ENABLED):
            self.state = package.ENABLED if enabled else package.DISABLED
        return self.state

    def activation(self):
        if isinstance(self.kind, Exception):
            raise self.kind
        return self.kind

    @staticmethod
    def registry():
        raise AssertionError("the packaged app must not use the HKCU Run key")


def test_no_package_identity_in_tests():
    # Neither macOS nor a plain Python on Windows runs with package identity.
    assert package.full_name() is None
    assert not package.is_packaged()


def test_packaged_start_at_login_is_the_startup_task(monkeypatch):
    task = Packaged(monkeypatch)
    assert not autostart.is_installed()
    autostart.set_enabled(True)
    assert task.calls == [True] and autostart.is_installed()
    autostart.set_enabled(False)
    assert task.calls == [True, False] and not autostart.is_installed()
    task.state = package.ENABLED_BY_POLICY
    assert autostart.is_installed()


def test_packaged_app_has_no_legacy_login_item_to_upgrade(monkeypatch):
    task = Packaged(monkeypatch)
    autostart.upgrade_legacy()
    assert task.calls == []


def test_startup_task_turned_off_by_the_user_is_left_alone(monkeypatch, caplog):
    task = Packaged(monkeypatch, state=package.DISABLED_BY_USER)
    with caplog.at_level(logging.WARNING):
        autostart.set_enabled(True)  # does not raise: the other settings still save
    assert task.calls == [True] and not autostart.is_installed()
    assert "Start at login stays off" in caplog.text


@pytest.mark.parametrize("kind, expected", [
    (package.STARTUP_TASK_ACTIVATION, True),
    (0, False),  # ActivationKind.Launch: the Start menu
    (None, False),
    (OSError("no WinRT"), False),
])
def test_packaged_app_started_by_its_startup_task_stays_in_the_tray(monkeypatch, kind, expected):
    Packaged(monkeypatch, kind=kind)
    assert autostart.started_at_login() is expected


def test_installer_build_keeps_the_run_key(monkeypatch):
    monkeypatch.setattr(package, "is_packaged", lambda: False)
    monkeypatch.setattr(package, "startup_task_state", lambda task_id: pytest.fail("not packaged"))
    monkeypatch.setattr(package, "activation_kind", lambda: pytest.fail("not packaged"))
    monkeypatch.setattr(autostart.runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(autostart.sys, "executable", r"C:\App\Blackboard Sync.exe")
    monkeypatch.setattr(autostart, "_value", lambda: '"C:\\App\\Blackboard Sync.exe" --background')
    assert autostart.is_installed()
    assert autostart.started_at_login() is False  # --background tells the installer build


def test_check_package_needs_identity(monkeypatch):
    monkeypatch.setattr(package, "full_name", lambda: None)
    with pytest.raises(RuntimeError, match="no package identity"):
        autostart.check_package()


def test_check_package_round_trip_restores_the_startup_task(monkeypatch):
    task = Packaged(monkeypatch)
    monkeypatch.setattr(package, "full_name", lambda: "Example_1.5.1.0_x64__abc")
    monkeypatch.setattr(package, "family_name", lambda: "Example_abc")
    scripts = []
    monkeypatch.setattr(notifications, "_run_script", scripts.append)
    assert autostart.check_package() == (
        "package ok (Example_1.5.1.0_x64__abc, startup task state 0, "
        "updater off, toast identity Example_abc!BlackboardSync)"
    )
    assert len(scripts) == 1 and "CreateToastNotifier('Example_abc!BlackboardSync')" in scripts[0]
    assert ".Show(" not in scripts[0]  # no interactive notification in CI
    assert task.calls == [True, False] and task.state == package.DISABLED


@pytest.mark.skipif(sys.platform != "win32", reason="calls the Windows Runtime")
def test_startup_task_without_package_identity_is_an_error():
    # Runs the real WinRT plumbing up to Windows' answer: no package, no task.
    with pytest.raises(OSError):
        package.startup_task_state(autostart.TASK_ID)


@pytest.mark.parametrize("version, expected", [
    ("1.5.1", "1.5.1.0"),
    ("2.0", "2.0.0.0"),
    ("1.6.0rc1", "1.6.0.0"),
    ("10.20.30", "10.20.30.0"),
])
def test_msix_version_has_a_zero_fourth_part(version, expected):
    assert make_layout.msix_version(version) == expected


@pytest.mark.parametrize("version", ["dev", "1.2.3.4", "70000.0.0"])
def test_msix_version_rejects_what_msix_cannot_hold(version):
    with pytest.raises(ValueError):
        make_layout.msix_version(version)


def test_current_app_version_makes_a_package_version():
    assert make_layout.msix_version(make_layout.app_version()).endswith(".0")


def test_manifest_is_a_full_trust_app_with_a_startup_task():
    root = ET.fromstring(make_layout.manifest(IDENTITY, "1.5.1.0"))
    identity = root.find("m:Identity", NS)
    assert identity.attrib == {
        "Name": "UmutYLCN.blackboard-sync",
        "Publisher": "CN=32397A73-9242-4378-90EB-34A15F7502AE",
        "Version": "1.5.1.0",
        "ProcessorArchitecture": "x64",
    }
    assert root.findtext("m:Properties/m:DisplayName", namespaces=NS) == "blackboard-sync"
    assert root.findtext("m:Properties/m:PublisherDisplayName", namespaces=NS) == "UmutYLCN"
    application = root.find("m:Applications/m:Application", NS)
    # The PyInstaller spec's windowed exe.
    assert application.get("Executable") == "Blackboard Sync.exe"
    assert application.get("EntryPoint") == "Windows.FullTrustApplication"
    assert application.get("Id") == package.APP_ID
    protocol_extension = application.find("m:Extensions/uap3:Extension", NS)
    assert protocol_extension.get("Category") == "windows.protocol"
    assert protocol_extension.get("Executable") == application.get("Executable")
    assert protocol_extension.get("EntryPoint") == "Windows.FullTrustApplication"
    protocol = protocol_extension.find("uap3:Protocol", NS)
    assert protocol.get("Name") == activation.STORE_PROTOCOL
    assert protocol.get("Parameters") == "--store-notification"
    assert protocol.findtext("uap:DisplayName", namespaces=NS) == "Blackboard Sync"
    extension = application.find("m:Extensions/uap5:Extension", NS)
    assert extension.get("Category") == "windows.startupTask"
    assert extension.get("Executable") == "Blackboard Sync.exe"
    task = extension.find("uap5:StartupTask", NS)
    # Off until the user's settings turn it on, as the installer build's Run value.
    assert task.get("TaskId") == autostart.TASK_ID and task.get("Enabled") == "false"
    assert task.get("DisplayName") == "Blackboard Sync"
    capabilities = root.find("m:Capabilities", NS)
    assert capabilities.find("m:Capability", NS).get("Name") == "internetClient"
    assert capabilities.find("rescap:Capability", NS).get("Name") == "runFullTrust"
    visuals = application.find("uap:VisualElements", NS)
    assert visuals.get("DisplayName") == "Blackboard Sync"
    logos = {visuals.get("Square150x150Logo"), visuals.get("Square44x44Logo"),
             visuals.find("uap:DefaultTile", NS).get("Wide310x150Logo"),
             root.findtext("m:Properties/m:Logo", namespaces=NS)}
    assert logos == {f"Assets\\{name}" for name in make_layout.ASSETS}


def test_spec_builds_the_exe_the_manifest_names():
    spec = (ROOT / "packaging" / "blackboard_sync_windows.spec").read_text(encoding="utf-8")
    assert 'name="Blackboard Sync",\n          console=False' in spec


def test_identity_placeholders_are_marked_in_one_file():
    identity = make_layout.load_identity()
    assert set(identity) == set(make_layout.IDENTITY_KEYS)
    assert make_layout.placeholders(identity) == []
    assert make_layout.placeholders({"name": "PLACEHOLDER.name"}) == ["name"]
    assert make_layout.placeholders(IDENTITY) == []


def test_layout_holds_the_app_manifest_and_logos(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    app = tmp_path / "Blackboard Sync"
    (app / "_internal").mkdir(parents=True)
    (app / "Blackboard Sync.exe").write_bytes(b"MZ")
    (app / "_internal" / "python312.dll").write_bytes(b"MZ")
    layout = tmp_path / "msix"
    (layout / "stale").mkdir(parents=True)
    version = make_layout.make_layout(app, layout, IDENTITY)
    assert version == make_layout.msix_version(make_layout.app_version())
    assert (layout / "Blackboard Sync.exe").read_bytes() == b"MZ"
    assert (layout / "_internal" / "python312.dll").exists() and not (layout / "stale").exists()
    assert f'Version="{version}"' in (layout / "AppxManifest.xml").read_text(encoding="utf-8")
    for name, (width, height, _) in make_layout.ASSETS.items():
        with Image.open(layout / "Assets" / name) as image:
            assert image.size == (width, height) and image.mode == "RGBA"


def test_layout_needs_the_pyinstaller_build(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_layout.make_layout(tmp_path, tmp_path / "msix", IDENTITY)


@pytest.mark.parametrize("packaged", [True, False])
def test_updater_never_contacts_github_or_touches_installer_in_package(tmp_path, monkeypatch, packaged):
    from blackboard_sync import updater

    monkeypatch.setattr(package, "is_packaged", lambda: packaged)
    network, launched = [], []

    class Response:
        status_code = 404
        def close(self):
            pass

    def get(*args, **kwargs):
        network.append(args[0])
        return Response()

    assert updater.enabled() is not packaged
    result = updater.check(get=get)
    assert result.status == ("store" if packaged else "unknown")
    assert len(network) == (0 if packaged else 1)
    network.clear()
    release = updater.Release("9.0.0", "", "Setup.exe", updater.DOWNLOAD_PREFIX + "v9.0.0/Setup.exe")
    if packaged:
        for operation in (
            lambda: updater.expected_checksum(release, get),
            lambda: updater.download(release, tmp_path / "update", get),
            lambda: updater.launch_installer(tmp_path / "Setup.exe", lambda *args, **kw: launched.append(args)),
            lambda: updater.install_windows_update(release, get, lambda *args, **kw: launched.append(args)),
        ):
            with pytest.raises(updater.UpdateError, match="Microsoft Store"):
                operation()
        assert network == launched == []
        assert not (tmp_path / "update").exists()
    else:
        updater.launch_installer(tmp_path / "Setup.exe", lambda *args, **kw: launched.append(args))
        assert launched[0][0] == [str(tmp_path / "Setup.exe"), *updater.WINDOWS_INSTALLER_ARGS]


@pytest.mark.parametrize("delete_files", [True, False])
def test_packaged_uninstall_preserves_app_data_and_course_files(config, monkeypatch, delete_files):
    from blackboard_sync import cli, uninstall

    monkeypatch.setattr(package, "is_packaged", lambda: True)
    config.data_dir.mkdir()
    config.dest.mkdir()
    config.session_file.write_text("session")
    course = config.dest / "course.pdf"
    course.write_bytes(b"course")
    calls = []
    assert uninstall.uninstall(
        config, delete_files, before_cleanup=lambda: calls.append("prepare"),
        startup_cleanup=lambda: calls.append("startup"), app_cleanup=lambda: calls.append("remove"),
    ) == [uninstall.STORE_REMOVAL]
    assert uninstall.remove_app() == [uninstall.STORE_REMOVAL]
    assert calls == [] and config.session_file.read_text() == "session" and course.read_bytes() == b"course"
    monkeypatch.setattr(cli, "make_config", lambda args: config)
    assert cli.main(["uninstall", "--delete-course-files"]) != 0
    assert config.session_file.read_text() == "session" and course.read_bytes() == b"course"


@pytest.mark.parametrize("packaged", [True, False])
def test_protocol_registration_is_only_for_the_installer(monkeypatch, packaged):
    from types import SimpleNamespace

    monkeypatch.setattr(package, "is_packaged", lambda: packaged)
    writes = []
    class Key:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER=1, REG_SZ=1,
        CreateKey=lambda hive, name: writes.append(name) or Key(),
        SetValueEx=lambda *args: writes.append(args[1:]),
    ))
    monkeypatch.setattr(activation, "protocol_command", lambda: "app --notification %1")
    activation.register()
    assert bool(writes) is not packaged


@pytest.mark.parametrize("packaged", [True, False])
def test_toasts_keep_safe_payload_and_select_the_right_identity(tmp_path, monkeypatch, packaged):
    import base64
    import re
    from blackboard_sync.menubar.model import Notification

    monkeypatch.setattr(package, "is_packaged", lambda: packaged)
    monkeypatch.setattr(package, "family_name", lambda: "Example_abc")
    note = Notification("Title", "Course & $(command)", {"open": str(tmp_path)})
    script = notifications.toast_script(note)
    expected = "Example_abc!BlackboardSync" if packaged else "Blackboard Sync"
    assert f"CreateToastNotifier('{expected}')" in script
    assert "$(command)" not in script
    payload = re.search(r"FromBase64String\('([^']+)'\)", script).group(1)
    toast = ET.fromstring(base64.b64decode(payload))
    assert toast.get("activationType") == "protocol"
    assert toast.get("launch") == (activation.STORE_URI if packaged else tmp_path.as_uri())
    assert toast.findtext("visual/binding/text[2]") == note.message


@pytest.mark.parametrize("packaged", [True, False])
def test_store_data_is_private_without_migrating_installer_files(tmp_path, monkeypatch, packaged):
    from blackboard_sync import system
    from blackboard_sync.config import Config

    monkeypatch.setattr(package, "is_packaged", lambda: packaged)
    monkeypatch.setattr(package, "family_name", lambda: "Example_abc")
    roaming, local = tmp_path / "Roaming", tmp_path / "Local"
    legacy = roaming / system.APP_NAME
    legacy.mkdir(parents=True)
    (legacy / "session.json").write_text("legacy session")
    data = system.default_data_dir("win32", env={"APPDATA": str(roaming), "LOCALAPPDATA": str(local)})
    expected = local / "Packages" / "Example_abc" / "LocalCache" / "Roaming" / system.APP_NAME
    assert data == (expected if packaged else legacy)
    config = Config.from_env({}, data_dir=data)
    assert config.session_file.exists() is not packaged
    assert (legacy / "session.json").read_text() == "legacy session"


@pytest.mark.parametrize("result", [0, 5])
def test_package_family_api_reads_identity_and_fails_closed(monkeypatch, result):
    import ctypes
    from types import SimpleNamespace

    class Function:
        def __call__(self, length, buffer):
            if buffer is None:
                ctypes.cast(length, ctypes.POINTER(ctypes.c_uint32)).contents.value = 12
                return package.ERROR_INSUFFICIENT_BUFFER
            if result == 0:
                buffer.value = "Example_abc"
            return result

    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=SimpleNamespace(
        GetCurrentPackageFamilyName=Function(),
    )), raising=False)
    package.family_name.cache_clear()
    try:
        if result:
            with pytest.raises(OSError, match="GetCurrentPackageFamilyName"):
                package.family_name()
        else:
            assert package.family_name() == "Example_abc"
            assert package.app_user_model_id() == "Example_abc!BlackboardSync"
    finally:
        package.family_name.cache_clear()


@pytest.mark.parametrize("already_running", [True, False])
def test_store_protocol_activation_shows_packaged_app(config, monkeypatch, already_running):
    from types import SimpleNamespace
    from blackboard_sync.windows import app as module
    from blackboard_sync.windows import theme as windows_theme

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(package, "is_packaged", lambda: True)
    config.data_dir.mkdir()
    monkeypatch.setattr(config, "ensure_data_dir", lambda: None)
    monkeypatch.setattr(module.Config, "from_env", lambda: config)
    calls = []
    lock = SimpleNamespace(close=lambda: calls.append("unlock"))
    monkeypatch.setattr(module.jobs, "single_instance", lambda config: None if already_running else lock)
    monkeypatch.setattr(autostart, "started_at_login", lambda: pytest.fail("fixed toast flag must show the window"))
    # Real packaged registration/legacy guards must not access the registry.
    monkeypatch.setitem(sys.modules, "winreg", None)
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(Tk=lambda: SimpleNamespace(withdraw=lambda: None)))
    monkeypatch.setattr(windows_theme, "apply_theme", lambda _root: None)

    class App:
        def __init__(self, config, root, show_window):
            calls.append(("show", show_window))
        def run(self):
            calls.append("run")

    monkeypatch.setattr(module, "TrayApp", App)
    assert module.main(["--store-notification"]) == 0
    if already_running:
        assert calls == []
        assert activation.take_window_request(config)
    else:
        assert calls == [("show", True), "run", "unlock"]
