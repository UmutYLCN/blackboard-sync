"""These regressions run without AppKit, a WindowServer, or a real display."""

import sys
from types import SimpleNamespace

import pytest

from blackboard_sync.menubar.presentation import configure_main_window, present_main_window


def test_main_window_uses_normal_level_and_one_managed_space(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "AppKit", SimpleNamespace(
        NSNormalWindowLevel=0,
        NSWindowCollectionBehaviorManaged=4,
        NSWindowCollectionBehaviorFullScreenPrimary=128,
    ))
    window = SimpleNamespace(
        setLevel_=lambda value: calls.append(("level", value)),
        setCollectionBehavior_=lambda value: calls.append(("behavior", value)),
    )

    configure_main_window(window)

    # Exact flags exclude joining all Spaces, auxiliary full-screen windows,
    # and moving into the currently active (possibly full-screen) Space.
    assert calls == [("level", 0), ("behavior", 4 | 128)]


@pytest.mark.parametrize("minimized", [False, True])
def test_window_is_ordered_before_activation_so_appkit_can_switch_spaces(minimized):
    calls = []
    window = SimpleNamespace(
        isMiniaturized=lambda: minimized,
        deminiaturize_=lambda sender: calls.append(("restore", sender)),
        makeKeyAndOrderFront_=lambda sender: calls.append(("front", sender)),
    )
    application = SimpleNamespace(
        activateIgnoringOtherApps_=lambda ignoring: calls.append(("activate", ignoring)),
    )

    present_main_window(window, application)

    expected = [("restore", None)] if minimized else []
    assert calls == expected + [("front", None), ("activate", True)]
