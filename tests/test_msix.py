"""The MSIX (Store) build: package layout, and start-at-login with and without package identity."""

import importlib.util
import logging
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from blackboard_sync.windows import autostart, package

ROOT = Path(__file__).resolve().parent.parent
NS = {
    "m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
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
    "name": "Example.BlackboardSync",
    "publisher": "CN=00000000-0000-0000-0000-000000000000",
    "publisher_display_name": "Ada & Co",
    "display_name": "Blackboard Sync",
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
    assert autostart.check_package() == "package ok (Example_1.5.1.0_x64__abc, startup task state 0)"
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
        "Name": "Example.BlackboardSync",
        "Publisher": "CN=00000000-0000-0000-0000-000000000000",
        "Version": "1.5.1.0",
        "ProcessorArchitecture": "x64",
    }
    assert root.findtext("m:Properties/m:PublisherDisplayName", namespaces=NS) == "Ada & Co"
    application = root.find("m:Applications/m:Application", NS)
    # The PyInstaller spec's windowed exe.
    assert application.get("Executable") == "Blackboard Sync.exe"
    assert application.get("EntryPoint") == "Windows.FullTrustApplication"
    extension = application.find("m:Extensions/uap5:Extension", NS)
    assert extension.get("Category") == "windows.startupTask"
    assert extension.get("Executable") == "Blackboard Sync.exe"
    task = extension.find("uap5:StartupTask", NS)
    # Off until the user's settings turn it on, as the installer build's Run value.
    assert task.get("TaskId") == autostart.TASK_ID and task.get("Enabled") == "false"
    capabilities = root.find("m:Capabilities", NS)
    assert capabilities.find("m:Capability", NS).get("Name") == "internetClient"
    assert capabilities.find("rescap:Capability", NS).get("Name") == "runFullTrust"
    visuals = application.find("uap:VisualElements", NS)
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
    assert make_layout.placeholders(identity) == ["name", "publisher", "publisher_display_name"]
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
