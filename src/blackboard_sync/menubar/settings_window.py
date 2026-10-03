"""The settings window (AppKit): draws ``FormValues`` and reports which button was pressed.

Everything the window means (defaults, validation, what a changed school or
folder implies) lives in ``settings_form.py``; this module only lays out
controls, runs the folder picker and shows the error it is handed back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSEventModifierFlagCommand,
    NSEventModifierFlagDeviceIndependentFlagsMask,
    NSEventTypeKeyDown,
    NSFont,
    NSModalResponseOK,
    NSOpenPanel,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSURL, NSMakeRect, NSObject

from blackboard_sync.menubar.model import T_AUTOSTART
from blackboard_sync.menubar.settings_form import (
    T_CANCEL,
    T_CHOOSE_FOLDER,
    T_CHOOSE_FOLDER_MESSAGE,
    T_CHOOSE_FOLDER_PROMPT,
    T_DEST_HINT,
    T_DEST_LABEL,
    T_INTRO_FIRST_RUN,
    T_LOGIN,
    T_SAVE,
    T_TITLE,
    T_TITLE_FIRST_RUN,
    T_URL_HINT,
    T_URL_LABEL,
    T_URL_PLACEHOLDER,
    FormValues,
)
from blackboard_sync.settings import display_path

WIDTH = 500
MARGIN = 20
CONTENT = WIDTH - 2 * MARGIN
FIELD_HEIGHT = 24
BUTTON_HEIGHT = 32

# The app has no main menu (menu bar accessory), so Cmd+V and friends would not
# reach the text fields; the window forwards them itself.
EDIT_KEYS = {"x": "cut:", "c": "copy:", "v": "paste:", "a": "selectAll:", "z": "undo:"}

# Called with (values, login pressed); returns (error, field) to show, or None to close.
SubmitHandler = Callable[[FormValues, bool], "tuple[str, str] | None"]


class _FlippedView(NSView):
    def isFlipped(self):
        return True


class _EditableWindow(NSWindow):
    def performKeyEquivalent_(self, event):
        flags = event.modifierFlags() & NSEventModifierFlagDeviceIndependentFlagsMask
        if event.type() == NSEventTypeKeyDown and flags == NSEventModifierFlagCommand:
            action = EDIT_KEYS.get(event.charactersIgnoringModifiers())
            responder = self.firstResponder()
            if action and responder is not None and responder.tryToPerform_with_(action, self):
                return True
        return objc.super(_EditableWindow, self).performKeyEquivalent_(event)


class _Target(NSObject):
    """Receives button clicks and the window-closed notice for ``SettingsWindow``."""

    def login_(self, _sender):
        self.owner.submit(login=True)

    def save_(self, _sender):
        self.owner.submit(login=False)

    def cancel_(self, _sender):
        self.owner.close()

    def chooseFolder_(self, _sender):
        self.owner.choose_folder()

    def windowWillClose_(self, _notification):
        self.owner.closed()


class SettingsWindow:
    def __init__(self, values: FormValues, first_run: bool, on_submit: SubmitHandler, on_close: Callable[[], None]):
        self.on_submit = on_submit
        self.on_close = on_close
        self.target = _Target.alloc().init()
        self.target.owner = self
        self.window = _EditableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, 100),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_(T_TITLE_FIRST_RUN if first_run else T_TITLE)
        self.window.setDelegate_(self.target)
        self._build(values, first_run)

    # -- layout --------------------------------------------------------------
    def _build(self, values: FormValues, first_run: bool) -> None:
        view = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 100))
        y = MARGIN

        def place(control, height: float, gap: float = 8, x: float = MARGIN, width: float = CONTENT) -> None:
            nonlocal y
            control.setFrame_(NSMakeRect(x, y, width, height))
            view.addSubview_(control)
            y += height + gap

        def wrapping(text: str, small: bool = False):
            label = NSTextField.wrappingLabelWithString_(text)
            if small:
                label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
                label.setTextColor_(NSColor.secondaryLabelColor())
            label.setPreferredMaxLayoutWidth_(CONTENT)
            return label, label.fittingSize().height

        def heading(text: str):
            label = NSTextField.labelWithString_(text)
            label.setFont_(NSFont.boldSystemFontOfSize_(NSFont.systemFontSize()))
            return label

        if first_run:
            intro, height = wrapping(T_INTRO_FIRST_RUN)
            place(intro, height, gap=16)

        place(heading(T_URL_LABEL), 17, gap=6)
        self.url_field = NSTextField.textFieldWithString_(values.base_url)
        self.url_field.setPlaceholderString_(T_URL_PLACEHOLDER)
        place(self.url_field, FIELD_HEIGHT, gap=4)
        hint, height = wrapping(T_URL_HINT, small=True)
        place(hint, height, gap=16)

        place(heading(T_DEST_LABEL), 17, gap=6)
        choose = NSButton.buttonWithTitle_target_action_(T_CHOOSE_FOLDER, self.target, "chooseFolder:")
        choose_width = max(choose.fittingSize().width, 80)
        self.dest_field = NSTextField.textFieldWithString_(values.dest)
        dest_y = y
        place(self.dest_field, FIELD_HEIGHT, gap=4, width=CONTENT - choose_width - 8)
        choose.setFrame_(NSMakeRect(WIDTH - MARGIN - choose_width, dest_y - 4, choose_width, BUTTON_HEIGHT))
        view.addSubview_(choose)
        hint, height = wrapping(T_DEST_HINT, small=True)
        place(hint, height, gap=16)

        self.autostart = NSButton.checkboxWithTitle_target_action_(T_AUTOSTART, None, None)
        self.autostart.setState_(1 if values.autostart else 0)
        place(self.autostart, 18, gap=12)

        self.error_label, _ = wrapping("")
        self.error_label.setTextColor_(NSColor.systemRedColor())
        place(self.error_label, 34, gap=8)

        # Right-aligned buttons: [Vazgeç] [Kaydet] [Giriş yap]; Return presses
        # "Giriş yap" on the first launch and "Kaydet" afterwards.
        buttons = [
            NSButton.buttonWithTitle_target_action_(T_CANCEL, self.target, "cancel:"),
            NSButton.buttonWithTitle_target_action_(T_SAVE, self.target, "save:"),
            NSButton.buttonWithTitle_target_action_(T_LOGIN, self.target, "login:"),
        ]
        buttons[0].setKeyEquivalent_("\x1b")
        buttons[2 if first_run else 1].setKeyEquivalent_("\r")
        x = WIDTH - MARGIN
        for button in reversed(buttons):
            width = max(button.fittingSize().width + 12, 90)
            x -= width
            button.setFrame_(NSMakeRect(x, y, width, BUTTON_HEIGHT))
            view.addSubview_(button)
            x -= 8
        y += BUTTON_HEIGHT + MARGIN

        view.setFrame_(NSMakeRect(0, 0, WIDTH, y))
        self.window.setContentView_(view)
        self.window.setContentSize_((WIDTH, y))

    # -- behaviour ------------------------------------------------------------
    def show(self) -> None:
        NSApp.activateIgnoringOtherApps_(True)
        if not self.window.isVisible():
            self.window.center()
        self.window.makeKeyAndOrderFront_(None)

    def values(self) -> FormValues:
        return FormValues(
            base_url=str(self.url_field.stringValue()),
            dest=str(self.dest_field.stringValue()),
            autostart=bool(self.autostart.state()),
        )

    def submit(self, login: bool) -> None:
        error = self.on_submit(self.values(), login)
        if error is None:
            self.close()
            return
        message, field = error
        self.error_label.setStringValue_(message)
        self.window.makeFirstResponder_(self.url_field if field == "base_url" else self.dest_field)

    def choose_folder(self) -> None:
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setCanCreateDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setPrompt_(T_CHOOSE_FOLDER_PROMPT)
        panel.setMessage_(T_CHOOSE_FOLDER_MESSAGE)
        start = Path(str(self.dest_field.stringValue()).strip() or "~").expanduser()
        while not start.is_dir() and start != start.parent:
            start = start.parent
        panel.setDirectoryURL_(NSURL.fileURLWithPath_(str(start)))
        if panel.runModal() == NSModalResponseOK and panel.URL() is not None:
            self.dest_field.setStringValue_(display_path(Path(panel.URL().path())))

    def close(self) -> None:
        self.window.close()  # windowWillClose_ reports it

    def closed(self) -> None:
        self.on_close()
