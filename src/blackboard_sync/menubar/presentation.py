"""Main-window presentation, isolated from the controls for display-free tests."""


def configure_main_window(window) -> None:
    from AppKit import (
        NSNormalWindowLevel,
        NSWindowCollectionBehaviorFullScreenPrimary,
        NSWindowCollectionBehaviorManaged,
    )

    window.setLevel_(NSNormalWindowLevel)
    # A normal app window belongs to one Space and participates in Mission
    # Control. FullScreenPrimary opts out of joining other apps' full-screen
    # Spaces; don't add auxiliary, all-Spaces or move-to-active-Space flags.
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorManaged | NSWindowCollectionBehaviorFullScreenPrimary
    )


def present_main_window(window, application) -> None:
    if window.isMiniaturized():
        window.deminiaturize_(None)
    # Give activation a visible window to switch to in its ordinary Space.
    window.makeKeyAndOrderFront_(None)
    application.activateIgnoringOtherApps_(True)
