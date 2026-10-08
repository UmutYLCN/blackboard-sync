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
    NSScrollView,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSURL, NSMakeRect, NSObject

from blackboard_sync import deleted
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
    T_PAST_DOWNLOAD,
    T_PAST_NOTE,
    T_SAVE,
    T_SECTION_ACCOUNT,
    T_SECTION_FOLDER,
    T_SECTION_GENERAL,
    T_SECTION_PAST_TERMS,
    T_SECTION_UPDATES,
    T_TITLE,
    T_TITLE_FIRST_RUN,
    T_UNINSTALL,
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
# Called with "logout", "check_updates", "update" or "uninstall": acts without saving.
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
        self.owner.deleted_action("refetch")

    def dismiss_(self, _sender):
        self.owner.deleted_action("dismiss")

    def selectAll_(self, _sender):
        self.owner.select_all()

    def checked_(self, sender):
        key = self.owner.check_keys[int(sender.tag())]
        self.owner.selection.select(key, bool(sender.state()))
        self.owner.update_deleted_buttons()

    def tabView_didSelectTabViewItem_(self, _tabs, _item):
        self.owner.refresh_deleted()

    def update_(self, _sender):
        self.owner.on_action(self.owner.status.update_action)

    def pastTerm_(self, _sender):
        self.owner.download_past_term()

    def uninstall_(self, _sender):
        self.owner.on_action("uninstall")

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
        on_missing=lambda: [],
        on_deleted_action=lambda action, keys: None,
        on_past_term: Callable[[str], object] = lambda name: None,
    ):
        self.on_submit = on_submit
        self.on_past_term = on_past_term
        self._past_terms: tuple[str, ...] | None = None
        self.on_action = on_action
        self.on_close = on_close
        self.on_missing, self.on_deleted_action = on_missing, on_deleted_action
        self.selection = deleted.DeletedSelection()
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

        section(T_SECTION_PAST_TERMS)
        self.past_button = NSButton.buttonWithTitle_target_action_(T_PAST_DOWNLOAD, self.target, "pastTerm:")
        past_width = max(self.past_button.fittingSize().width + 12, 140)
        self.past_button.setFrame_(NSMakeRect(WIDTH - MARGIN - past_width, y - 4, past_width, BUTTON_HEIGHT))
        view.addSubview_(self.past_button)
        self.past_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(MARGIN, y, CONTENT - past_width - 8, 25), False
        )
        view.addSubview_(self.past_popup)
        y += 25 + 8
        note, height = wrapping(T_PAST_NOTE, small=True)
        place(note, height, gap=4)
        self.past_label, _ = wrapping("", small=True)
        place(self.past_label, 30, gap=8)

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
        self.uninstall_button = NSButton.buttonWithTitle_target_action_(T_UNINSTALL, self.target, "uninstall:")
        place(self.uninstall_button, BUTTON_HEIGHT, gap=8, x=WIDTH - MARGIN - ACTION_WIDTH, width=ACTION_WIDTH)

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
        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH + 32, y + 48))
        general = NSTabViewItem.alloc().initWithIdentifier_("general")
        general.setLabel_("Genel")
        general.setView_(view)
        tabs.addTabViewItem_(general)
        removed = NSTabViewItem.alloc().initWithIdentifier_("deleted")
        removed.setLabel_(deleted.T_TAB)
        self.deleted_view = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, y))
        removed.setView_(self.deleted_view)
        tabs.addTabViewItem_(removed)
        self._build_deleted(y)
        tabs.setDelegate_(self.target)
        self.tabs = tabs
        self.window.setContentView_(tabs)
        self.window.setContentSize_((WIDTH + 32, y + 48))

    # -- behaviour ------------------------------------------------------------
    def show(self) -> None:
        self.refresh_deleted()
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
        self.version_label.setStringValue_(status.version)
        self.update_button.setTitle_(status.update_title)
        self.update_button.setEnabled_(status.update_enabled)
        self.uninstall_button.setEnabled_(status.uninstall_enabled)
        if status.past_terms != self._past_terms:
            selected = self.past_popup.titleOfSelectedItem()
            self.past_popup.removeAllItems()
            self.past_popup.addItemsWithTitles_(list(status.past_terms))
            if selected in status.past_terms:
                self.past_popup.selectItemWithTitle_(selected)
            self._past_terms = status.past_terms
        self.past_popup.setEnabled_(bool(status.past_terms))
        self.past_button.setEnabled_(status.past_enabled)
        self.past_label.setStringValue_(status.past_message)
        self.past_label.setToolTip_(status.past_message or None)
        self.deleted_result.setStringValue_(status.deleted_message)
        self.refresh_deleted()

    def _build_deleted(self, height):
        hint = NSTextField.wrappingLabelWithString_(deleted.T_HINT)
        hint.setFrame_(NSMakeRect(MARGIN, MARGIN, CONTENT, 50))
        self.deleted_view.addSubview_(hint)
        self.deleted_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(MARGIN, 78, CONTENT, height - 194))
        self.deleted_scroll.setHasVerticalScroller_(True)
        self.deleted_scroll.setAutohidesScrollers_(True)
        self.deleted_view.addSubview_(self.deleted_scroll)
        self.select_all_button = NSButton.buttonWithTitle_target_action_(deleted.T_SELECT_ALL, self.target, "selectAll:")
        self.refetch_button = NSButton.buttonWithTitle_target_action_(deleted.T_DOWNLOAD, self.target, "refetch:")
        self.dismiss_button = NSButton.buttonWithTitle_target_action_(deleted.T_DISMISS, self.target, "dismiss:")
        x = MARGIN
        for button in (self.select_all_button, self.refetch_button, self.dismiss_button):
            width = max(button.fittingSize().width + 8, 110)
            button.setFrame_(NSMakeRect(x, height - 102, width, BUTTON_HEIGHT))
            self.deleted_view.addSubview_(button)
            x += width + 4
        self.deleted_result = NSTextField.wrappingLabelWithString_("")
        self.deleted_result.setFrame_(NSMakeRect(MARGIN, height - 62, CONTENT, 50))
        self.deleted_view.addSubview_(self.deleted_result)
        self._drawn_rows = None
        self.checks = {}
        self.check_keys = []

    def refresh_deleted(self):
        rows = self.on_missing()
        self.selection.refresh(rows)
        if rows != self._drawn_rows:
            document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, CONTENT - 20, 1))
            y = 0
            group = None
            self.checks = {}
            self.check_keys = []
            def label(text, height, bold=False):
                nonlocal y
                control = NSTextField.wrappingLabelWithString_(text)
                if bold:
                    control.setFont_(NSFont.boldSystemFontOfSize_(NSFont.systemFontSize()))
                else:
                    control.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
                    control.setTextColor_(NSColor.secondaryLabelColor())
                control.setPreferredMaxLayoutWidth_(CONTENT - 20)
                height = max(height, control.fittingSize().height)
                control.setToolTip_(text)
                control.setFrame_(NSMakeRect(0, y, CONTENT - 20, height))
                document.addSubview_(control)
                y += height + 6
            if not rows:
                label(deleted.T_EMPTY, 32)
            for row in rows:
                if group != (row.term, row.course):
                    group = (row.term, row.course)
                    label(f"{row.term} / {row.course}", 40, bold=True)
                button = NSButton.checkboxWithTitle_target_action_(row.name, self.target, "checked:")
                button.cell().setWraps_(True)
                button_height = max(24, button.cell().cellSizeForBounds_(NSMakeRect(0, 0, CONTENT - 20, 1000)).height)
                button.setFrame_(NSMakeRect(0, y, CONTENT - 20, button_height))
                button.setToolTip_(row.name)
                button.setTag_(len(self.check_keys))
                button.setState_(1 if row.key in self.selection.selected else 0)
                self.check_keys.append(row.key)
                self.checks[row.key] = button
                document.addSubview_(button)
                y += button_height + 4
                label(row.folder, 40)
            document.setFrame_(NSMakeRect(0, 0, CONTENT - 20, max(y, 1)))
            self.deleted_scroll.setDocumentView_(document)
            self._drawn_rows = rows
        self.update_deleted_buttons()

    def update_deleted_buttons(self):
        enabled = self.status.refetch_enabled
        self.select_all_button.setEnabled_(enabled and bool(self.selection.rows))
        self.refetch_button.setTitle_(self.status.refetch_title)
        self.refetch_button.setEnabled_(enabled and bool(self.selection.keys()))
        self.dismiss_button.setEnabled_(enabled and bool(self.selection.keys()))
        for button in self.checks.values():
            button.setEnabled_(enabled)

    def select_all(self):
        self.selection.select_all()
        for button in self.checks.values():
            button.setState_(1)
        self.update_deleted_buttons()

    def deleted_action(self, action):
        keys = self.selection.keys()
        if not keys or not self.status.refetch_enabled:
            return
        error = self.on_deleted_action(action, keys)
        self.refresh_deleted()
        if error:
            self.deleted_result.setStringValue_(error)
        elif action == "dismiss":
            self.deleted_result.setStringValue_("Seçilen dosyalar listeden kaldırıldı.")

    def download_past_term(self) -> None:
        """Start the one-time download of the term picked in Eski dönemler; the window stays open."""
        name = self.past_popup.titleOfSelectedItem()
        if name and self.status.past_enabled:
            self.on_past_term(str(name))

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


class _UninstallChoice(NSObject):
    def changed_(self, checkbox):
        self.path_label.setHidden_(not bool(checkbox.state()))


def ask_uninstall(dest: Path) -> bool | None:
    """False keeps course files, True trashes them, None cancels everything."""
    from blackboard_sync import uninstall

    alert = NSAlert.alloc().init()
    alert.setMessageText_(uninstall.TITLE)
    alert.setInformativeText_(uninstall.MESSAGE)
    alert.addButtonWithTitle_("Kaldır")
    cancel = alert.addButtonWithTitle_("Vazgeç")
    cancel.setKeyEquivalent_("\x1b")
    view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 440, 110))
    target = _UninstallChoice.alloc().init()
    checkbox = NSButton.checkboxWithTitle_target_action_(uninstall.CHECKBOX, target, "changed:")
    checkbox.setState_(0)
    checkbox.setFrame_(NSMakeRect(0, 80, 440, 24))
    label = NSTextField.wrappingLabelWithString_(f"Çöp Sepeti'ne taşınacak dosyaların klasörü:\n{dest}")
    label.setFrame_(NSMakeRect(0, 0, 440, 72))
    label.setHidden_(True)
    target.path_label = label
    view.addSubview_(checkbox)
    view.addSubview_(label)
    alert.setAccessoryView_(view)
    NSApp.activateIgnoringOtherApps_(True)
    if alert.runModal() != NSAlertFirstButtonReturn:
        return None
    return bool(checkbox.state())
