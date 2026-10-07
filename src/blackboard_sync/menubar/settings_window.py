"""The settings window (AppKit): draws ``FormValues`` and ``WindowStatus`` and reports buttons.

Everything the window means (sections, defaults, validation, what a changed
school or folder implies, which buttons work right now) lives in
``settings_form.py``; this module only lays out controls, runs the folder
picker and shows the error it is handed back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApp,
    NSBackingStoreBuffered,
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSColor,
    NSEventModifierFlagCommand,
    NSEventModifierFlagDeviceIndependentFlagsMask,
    NSEventTypeKeyDown,
    NSFont,
    NSModalResponseOK,
    NSOpenPanel,
    NSPopUpButton,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSURL, NSMakeRect, NSObject

from blackboard_sync.menubar.settings_form import (
    DEST_CHOICES,
    INTERVAL_OPTIONS,
    T_AUTOSTART,
    T_CANCEL,
    T_CHECK_UPDATES,
    T_CHOOSE_FOLDER,
    T_CHOOSE_FOLDER_MESSAGE,
    T_CHOOSE_FOLDER_PROMPT,
    T_DEST_CHANGE_TITLE,
    T_DEST_HINT,
    T_DEST_LABEL,
    T_INTERVAL_LABEL,
    T_REFETCH_HINT,
    T_SAVE,
    T_SECTION_ACCOUNT,
    T_SECTION_FOLDER,
    T_SECTION_GENERAL,
    T_SECTION_UPDATES,
    T_TITLE,
    T_TITLE_FIRST_RUN,
    T_URL_HINT,
    T_URL_LABEL,
    T_URL_PLACEHOLDER,
    FormValues,
    WindowStatus,
    dest_change_message,
    interval_title,
    intro_first_run,
)
from blackboard_sync.settings import display_path

WIDTH = 500
MARGIN = 20
CONTENT = WIDTH - 2 * MARGIN
FIELD_HEIGHT = 24
BUTTON_HEIGHT = 32
# Buttons whose title changes with the app's state ("Giriş yap" / "Hesaptan
# çıkış yap") keep one width so the row does not jump.
ACTION_WIDTH = 190

# The app has no main menu (menu bar accessory), so Cmd+V and friends would not
# reach the text fields; the window forwards them itself.
EDIT_KEYS = {"x": "cut:", "c": "copy:", "v": "paste:", "a": "selectAll:", "z": "undo:"}

# Called with (values, login pressed); returns (error, field) to show, or None to close.
SubmitHandler = Callable[[FormValues, bool], "tuple[str, str] | None"]
# Called with "logout", "refetch", "check_updates" or "update": acts without saving.
ActionHandler = Callable[[str], None]


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

    def account_(self, _sender):
        self.owner.account_pressed()

    def refetch_(self, _sender):
        self.owner.on_action("refetch")

    def update_(self, _sender):
        self.owner.on_action(self.owner.status.update_action)

    def save_(self, _sender):
        self.owner.submit(login=False)

    def cancel_(self, _sender):
        self.owner.close()

    def chooseFolder_(self, _sender):
        self.owner.choose_folder()

    def windowWillClose_(self, _notification):
        self.owner.closed()


class SettingsWindow:
    def __init__(
        self,
        values: FormValues,
        status: WindowStatus,
        first_run: bool,
        on_submit: SubmitHandler,
        on_action: ActionHandler,
        on_close: Callable[[], None],
    ):
        self.on_submit = on_submit
        self.on_action = on_action
        self.on_close = on_close
        self.status = status
        self.first_run = first_run
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
        self.update_status(status)

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

        def label(text: str):
            return NSTextField.labelWithString_(text)

        def section(text: str, first: bool = False) -> None:
            nonlocal y
            if not first:
                line = NSBox.alloc().initWithFrame_(NSMakeRect(MARGIN, y, CONTENT, 1))
                line.setBoxType_(NSBoxSeparator)
                view.addSubview_(line)
                y += 13
            title = label(text)
            title.setFont_(NSFont.boldSystemFontOfSize_(NSFont.systemFontSize() + 1))
            place(title, 18, gap=8)

        def action_row(text_field, button) -> None:
            """A label on the left and a fixed-width button on the right."""
            nonlocal y
            button.setFrame_(NSMakeRect(WIDTH - MARGIN - ACTION_WIDTH, y - 4, ACTION_WIDTH, BUTTON_HEIGHT))
            view.addSubview_(button)
            text_field.setPreferredMaxLayoutWidth_(CONTENT - ACTION_WIDTH - 12)
            place(text_field, 34, gap=12, width=CONTENT - ACTION_WIDTH - 12)

        if first_run:
            intro, height = wrapping(intro_first_run("bu Mac'e", values.sync_interval_minutes))
            place(intro, height, gap=16)

        section(T_SECTION_ACCOUNT, first=True)
        place(label(T_URL_LABEL), 17, gap=6)
        self.url_field = NSTextField.textFieldWithString_(values.base_url)
        self.url_field.setPlaceholderString_(T_URL_PLACEHOLDER)
        place(self.url_field, FIELD_HEIGHT, gap=4)
        hint, height = wrapping(T_URL_HINT, small=True)
        place(hint, height, gap=12)
        self.account_label = NSTextField.wrappingLabelWithString_("")
        self.account_button = NSButton.buttonWithTitle_target_action_("", self.target, "account:")
        action_row(self.account_label, self.account_button)

        section(T_SECTION_FOLDER)
        place(label(T_DEST_LABEL), 17, gap=6)
        choose = NSButton.buttonWithTitle_target_action_(T_CHOOSE_FOLDER, self.target, "chooseFolder:")
        choose_width = max(choose.fittingSize().width, 80)
        self.dest_field = NSTextField.textFieldWithString_(values.dest)
        dest_y = y
        place(self.dest_field, FIELD_HEIGHT, gap=4, width=CONTENT - choose_width - 8)
        choose.setFrame_(NSMakeRect(WIDTH - MARGIN - choose_width, dest_y - 4, choose_width, BUTTON_HEIGHT))
        view.addSubview_(choose)
        hint, height = wrapping(T_DEST_HINT, small=True)
        place(hint, height, gap=12)
        refetch_hint, _ = wrapping(T_REFETCH_HINT, small=True)
        self.refetch_button = NSButton.buttonWithTitle_target_action_("", self.target, "refetch:")
        action_row(refetch_hint, self.refetch_button)

        section(T_SECTION_GENERAL)
        self.autostart = NSButton.checkboxWithTitle_target_action_(T_AUTOSTART, None, None)
        self.autostart.setState_(1 if values.autostart else 0)
        place(self.autostart, 18, gap=16)
        interval_label = label(T_INTERVAL_LABEL + ":")
        label_width = interval_label.fittingSize().width + 4
        interval_label.setFrame_(NSMakeRect(MARGIN, y + 4, label_width, 17))
        view.addSubview_(interval_label)
        self.interval_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(MARGIN + label_width + 8, y, 170, 25), False
        )
        self.interval_popup.addItemsWithTitles_([title for _, title in INTERVAL_OPTIONS])
        self.interval_popup.selectItemWithTitle_(interval_title(values.sync_interval_minutes))
        view.addSubview_(self.interval_popup)
        y += 25 + 4

        section(T_SECTION_UPDATES)
        self.check_updates = NSButton.checkboxWithTitle_target_action_(T_CHECK_UPDATES, None, None)
        self.check_updates.setState_(1 if values.check_updates else 0)
        place(self.check_updates, 18, gap=12)
        self.version_label = label("")
        self.update_button = NSButton.buttonWithTitle_target_action_("", self.target, "update:")
        action_row(self.version_label, self.update_button)

        self.error_label, _ = wrapping("")
        self.error_label.setTextColor_(NSColor.systemRedColor())
        place(self.error_label, 34, gap=8)

        # Right-aligned buttons: [Vazgeç] [Kaydet]; Return presses "Giriş yap"
        # (in Hesap) on the first launch and "Kaydet" afterwards.
        buttons = [
            NSButton.buttonWithTitle_target_action_(T_CANCEL, self.target, "cancel:"),
            NSButton.buttonWithTitle_target_action_(T_SAVE, self.target, "save:"),
        ]
        buttons[0].setKeyEquivalent_("\x1b")
        if not first_run:
            buttons[1].setKeyEquivalent_("\r")
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
            check_updates=bool(self.check_updates.state()),
            sync_interval_minutes=next(
                (m for m, title in INTERVAL_OPTIONS if title == str(self.interval_popup.titleOfSelectedItem())), 60
            ),
        )

    def update_status(self, status: WindowStatus) -> None:
        self.status = status
        self.account_label.setStringValue_(status.account)
        self.account_label.setTextColor_(
            NSColor.systemRedColor() if status.account_warning else NSColor.labelColor()
        )
        self.account_button.setTitle_(status.account_title)
        if self.first_run:  # Return signs in, never out
            self.account_button.setKeyEquivalent_("\r" if status.account_action == "login" else "")
        self.account_button.setEnabled_(status.account_enabled)
        self.refetch_button.setTitle_(status.refetch_title)
        self.refetch_button.setEnabled_(status.refetch_enabled)
        self.version_label.setStringValue_(status.version)
        self.update_button.setTitle_(status.update_title)
        self.update_button.setEnabled_(status.update_enabled)

    def account_pressed(self) -> None:
        if self.status.account_action == "login":
            self.submit(login=True)  # sign in with the address in the field
        else:
            self.on_action(self.status.account_action)

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


def ask_dest_choice(old: Path, new: Path, files: int) -> str | None:
    """Ask what happens to the files in ``old``; a ``DEST_CHOICES`` key, or None for "Vazgeç".

    "Taşı" is the default button (Return); Escape cancels the save.
    """
    alert = NSAlert.alloc().init()
    alert.setMessageText_(T_DEST_CHANGE_TITLE)
    alert.setInformativeText_(dest_change_message(old, new, files))
    for _, title in DEST_CHOICES:
        alert.addButtonWithTitle_(title)
    alert.addButtonWithTitle_(T_CANCEL).setKeyEquivalent_("\x1b")
    NSApp.activateIgnoringOtherApps_(True)
    index = alert.runModal() - NSAlertFirstButtonReturn
    return DEST_CHOICES[index][0] if 0 <= index < len(DEST_CHOICES) else None
