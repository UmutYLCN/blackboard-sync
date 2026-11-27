"""Main-window presentation, isolated from the controls for display-free tests."""


def configure_main_window(window) -> None:
    from AppKit import (
        NSNormalWindowLevel,
        NSWindowCollectionBehaviorFullScreenNone,
        NSWindowCollectionBehaviorManaged,
    )

    window.setLevel_(NSNormalWindowLevel)
    # A normal app window belongs to one Space and participates in Mission
    # Control. It never goes full screen, and stays out of other apps' full-screen
    # Spaces; don't add auxiliary, all-Spaces or move-to-active-Space flags.
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorManaged | NSWindowCollectionBehaviorFullScreenNone
    )


def present_main_window(window, application) -> None:
    if window.isMiniaturized():
        window.deminiaturize_(None)
    # Give activation a visible window to switch to in its ordinary Space.
    window.makeKeyAndOrderFront_(None)
    application.activateIgnoringOtherApps_(True)
