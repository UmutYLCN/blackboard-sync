"""The main window (AppKit): a sidebar with Başlangıç / Genel bakış, Genel and Silinenler.

What the window shows and means lives in ``main_window_model.py`` (sections,
the overview, the unsaved-changes bar) and ``settings_form.py`` (the Genel
form, validation, what a changed school or folder implies); this module only
lays out controls, runs the folder picker and reports clicks.
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
    NSBoxCustom,
    NSBoxSeparator,
    NSButton,
    NSColor,
    NSEventModifierFlagCommand,
    NSEventModifierFlagDeviceIndependentFlagsMask,
    NSEventTypeKeyDown,
    NSFont,
    NSImage,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSLineBreakByTruncatingTail,
    NSModalResponseOK,
    NSNoTitle,
    NSOpenPanel,
    NSPopUpButton,
    NSScreen,
    NSScrollView,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSViewHeightSizable,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialSidebar,
    NSVisualEffectStateFollowsWindowActiveState,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWorkspace,
)
from Foundation import NSURL, NSMakeRect, NSObject

from blackboard_sync import __version__, deleted
from blackboard_sync.menubar.main_window_model import (
    DELETED,
    GENERAL,
    OVERVIEW,
    START_STEPS,
    T_NAV_GENERAL,
    T_NAV_DELETED,
    T_OPEN_FOLDER,
    T_START_FORM,
    T_START_INTRO,
    T_START_TITLE,
    T_UNSAVED,
    T_WINDOW_TITLE,
    MainStatus,
    WindowState,
    deleted_detail,
    has_changes,
    recent_count,
    reopen_hint,
)
from blackboard_sync.menubar.model import T_RECENT, T_RECENT_EMPTY
from blackboard_sync.menubar.settings_form import (
    DEST_CHOICES,
    INTERVAL_OPTIONS,
    MIN_WINDOW_HEIGHT,
    T_AUTOSTART,
    T_CANCEL,
    T_CHECK_UPDATES,
    T_CHOOSE_FOLDER,
    T_CHOOSE_FOLDER_MESSAGE,
    T_CHOOSE_FOLDER_PROMPT,
    T_DEST_CHANGE_TITLE,
    T_DEST_HINT,
    T_DEST_LABEL,
    T_DEST_ROOT_NOTE,
    T_INTERVAL_LABEL,
    T_PAST_DOWNLOAD,
    T_PAST_NOTE,
    T_SAVE,
    T_SECTION_ACCOUNT,
    T_SECTION_FOLDER,
    T_SECTION_GENERAL,
    T_SECTION_PAST_TERMS,
    T_SECTION_UPDATES,
    T_UNINSTALL,
    T_URL_HINT,
    T_URL_LABEL,
    T_URL_PLACEHOLDER,
    FormValues,
    dest_change_message,
    interval_title,
    window_height,
)
from blackboard_sync.settings import display_path

# The window keeps its width; only the height follows the screen and the student.
WIDTH = 960
SIDEBAR = 210
PAGE = WIDTH - SIDEBAR
PAD = 28
INNER = PAGE - 2 * PAD
HEIGHT = 660  # the content height it opens with when the screen has room
HEADER = 76  # a section's title row; the rest of the section scrolls below it
BAR = 60  # Genel's Vazgeç/Kaydet bar
GAP = 16
COLUMN = (INNER - GAP) // 2
FIELD_HEIGHT = 24
BUTTON_HEIGHT = 32
ROW_HEIGHT = 52
# Buttons whose title changes with the app's state ("Giriş yap" / "Hesaptan
# çıkış yap") keep one width so the row does not jump.
ACTION_WIDTH = 160
NAV_SYMBOLS = {OVERVIEW: "house", GENERAL: "gearshape", DELETED: "arrow.counterclockwise"}

# Text fields get Cmd+V and friends from the main menu; while it is not there
# (the app is a menu bar accessory) the window forwards them itself.
EDIT_KEYS = {"x": "cut:", "c": "copy:", "v": "paste:", "a": "selectAll:", "z": "undo:"}

# Called with (values, login pressed); returns (error, field) to show, or None once saved.
SubmitHandler = Callable[[FormValues, bool], "tuple[str, str] | None"]
# Called with "sync", "folder", "login", "logout", "check_updates", "update" or "uninstall".
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
    """Receives clicks, text edits and the window-closed notice for ``MainWindow``."""

    def nav_(self, sender):
        self.owner.select((OVERVIEW, GENERAL, DELETED)[int(sender.tag())])

    def sync_(self, _sender):
        self.owner.on_action("sync")

    def folder_(self, _sender):
        self.owner.on_action("folder")

    def login_(self, _sender):
        self.owner.on_action("login")

    def openRecent_(self, sender):
        rows = self.owner.status.recent
        index = int(sender.tag())
        if index < len(rows):
            self.owner.on_open(rows[index].path)

    def start_(self, _sender):
        self.owner.submit(login=self.owner.status.start_login)

    def account_(self, _sender):
        self.owner.account_pressed()

    def changed_(self, sender):
        self.owner.changed(sender)

    def controlTextDidChange_(self, notification):
        self.owner.changed(notification.object())

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

    def update_(self, _sender):
        self.owner.on_action(self.owner.status.form.update_action)

    def pastTerm_(self, _sender):
        self.owner.download_past_term()

    def uninstall_(self, _sender):
        self.owner.on_action("uninstall")

    def save_(self, _sender):
        self.owner.submit(login=False)

    def cancel_(self, _sender):
        self.owner.discard()

    def chooseFolder_(self, sender):
        self.owner.choose_folder(sender)

    def windowWillClose_(self, _notification):
        self.owner.closed()


def _label(text: str, size: float | None = None, bold: bool = False, secondary: bool = False):
    field = NSTextField.labelWithString_(text)
    size = size or NSFont.systemFontSize()
    field.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if secondary:
        field.setTextColor_(NSColor.secondaryLabelColor())
    field.setLineBreakMode_(NSLineBreakByTruncatingTail)
    return field


def _wrapping(text: str, width: float, size: float | None = None, secondary: bool = False):
    """A multi-line label and the height it needs at ``width``."""
    field = NSTextField.wrappingLabelWithString_(text)
    field.setFont_(NSFont.systemFontOfSize_(size or NSFont.systemFontSize()))
    if secondary:
        field.setTextColor_(NSColor.secondaryLabelColor())
    field.setPreferredMaxLayoutWidth_(width)
    return field, field.fittingSize().height


def _small() -> float:
    return NSFont.smallSystemFontSize()


def _card(frame, warning: bool = False):
    """A rounded box whose content view is flipped (y grows downwards)."""
    box = NSBox.alloc().initWithFrame_(frame)
    box.setBoxType_(NSBoxCustom)
    box.setTitlePosition_(NSNoTitle)
    box.setCornerRadius_(10)
    box.setBorderWidth_(1)
    box.setContentViewMargins_((0, 0))
    _tone(box, warning)
    box.setContentView_(_FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, frame.size.width, frame.size.height)))
    return box


def _tone(box, warning: bool) -> None:
    if warning:
        box.setFillColor_(NSColor.systemOrangeColor().colorWithAlphaComponent_(0.12))
        box.setBorderColor_(NSColor.systemOrangeColor().colorWithAlphaComponent_(0.45))
    else:
        box.setFillColor_(NSColor.controlBackgroundColor())
        box.setBorderColor_(NSColor.separatorColor())


def _pill(frame, color):
    """A filled rounded shape (a badge, the avatar, a step number)."""
    box = NSBox.alloc().initWithFrame_(frame)
    box.setBoxType_(NSBoxCustom)
    box.setTitlePosition_(NSNoTitle)
    box.setBorderWidth_(0)
    box.setCornerRadius_(frame.size.height / 2)
    box.setFillColor_(color)
    box.setContentViewMargins_((0, 0))
    return box


def _centered(text: str, frame, size: float, bold: bool = False):
    field = _label(text, size, bold=bold)
    field.setAlignment_(NSTextAlignmentCenter)
    height = field.fittingSize().height
    field.setFrame_(NSMakeRect(0, (frame.size.height - height) / 2, frame.size.width, height))
    return field


def _primary(button) -> None:
    button.setBezelColor_(NSColor.controlAccentColor())


def _scroll(frame, document_height: float):
    """A vertical scroll view with a flipped document view of the scroll view's width."""
    scroll = NSScrollView.alloc().initWithFrame_(frame)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setDrawsBackground_(False)
    scroll.setAutoresizingMask_(NSViewHeightSizable)
    document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, frame.size.width, document_height))
    scroll.setDocumentView_(document)
    return scroll, document


def file_icon(name: str):
    return NSWorkspace.sharedWorkspace().iconForFileType_(Path(name).suffix[1:] or "txt")


class MainWindow:
    def __init__(
        self,
        values: FormValues,
        status: MainStatus,
        on_submit: SubmitHandler,
        on_action: ActionHandler,
        on_close: Callable[[], None],
        on_values: Callable[[], FormValues] | None = None,
        on_open: Callable[[str], None] = lambda path: None,
        on_missing=lambda: [],
        on_deleted_action=lambda action, keys: None,
        on_past_term: Callable[[str], object] = lambda name: None,
        reopen_where: str = "Applications veya Launchpad'den",
    ):
        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.on_values = on_values or (lambda: self.saved)
        self.on_open, self.on_past_term = on_open, on_past_term
        self.on_missing, self.on_deleted_action = on_missing, on_deleted_action
        self.selection = deleted.DeletedSelection()
        self.state = WindowState()
        self.status = status
        self.saved = values
        self.error = ""
        self._past_terms: tuple[str, ...] | None = None
        self._drawn_recent = None
        self._drawn_rows = None
        self.checks: dict = {}
        self.check_keys: list[str] = []
        self.target = _Target.alloc().init()
        self.target.owner = self
        self.window = _EditableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_(T_WINDOW_TITLE)
        self.window.setDelegate_(self.target)
        root = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        self.window.setContentView_(root)
        self._build_sidebar(root)
        self.pages = {}
        for name, build in (("start", self._build_start), (OVERVIEW, self._build_overview),
                            (GENERAL, self._build_general), (DELETED, self._build_deleted)):
            page = _FlippedView.alloc().initWithFrame_(NSMakeRect(SIDEBAR, 0, PAGE, HEIGHT))
            page.setAutoresizingMask_(NSViewHeightSizable)
            page.setHidden_(True)
            root.addSubview_(page)
            self.pages[name] = page
            if name == "start":
                build(page, reopen_where)
            else:
                build(page)
        # The fields Başlangıç and Genel share edit the same draft.
        self.mirrors = {}
        for one, other in ((self.start_url, self.url_field), (self.start_dest, self.dest_field),
                           (self.start_autostart, self.autostart)):
            self.mirrors[one], self.mirrors[other] = other, one
        self.set_values(values)
        self.update_status(status)
        self._show_section()

    # -- layout --------------------------------------------------------------
    def _build_sidebar(self, root) -> None:
        sidebar = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, SIDEBAR, HEIGHT))
        sidebar.setMaterial_(NSVisualEffectMaterialSidebar)
        sidebar.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        sidebar.setState_(NSVisualEffectStateFollowsWindowActiveState)
        sidebar.setAutoresizingMask_(NSViewHeightSizable)
        root.addSubview_(sidebar)
        view = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, SIDEBAR, HEIGHT))
        view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        sidebar.addSubview_(view)

        logo = NSImageView.alloc().initWithFrame_(NSMakeRect(16, 18, 36, 36))
        logo.setImage_(NSApp.applicationIconImage())
        logo.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        view.addSubview_(logo)
        name = _label(T_WINDOW_TITLE, 13, bold=True)
        name.setFrame_(NSMakeRect(60, 18, SIDEBAR - 72, 17))
        view.addSubview_(name)
        version = _label(__version__, _small(), secondary=True)
        version.setFrame_(NSMakeRect(60, 37, SIDEBAR - 72, 15))
        view.addSubview_(version)

        self.nav_items = {}
        y = 76
        for index, section in enumerate((OVERVIEW, GENERAL, DELETED)):
            highlight = _pill(NSMakeRect(10, y, SIDEBAR - 20, 32), NSColor.quaternaryLabelColor())
            highlight.setCornerRadius_(6)
            view.addSubview_(highlight)
            icon = NSImageView.alloc().initWithFrame_(NSMakeRect(20, y + 7, 18, 18))
            icon.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_(NAV_SYMBOLS[section], None))
            view.addSubview_(icon)
            title = _label("", 13)
            title.setFrame_(NSMakeRect(46, y + 7, SIDEBAR - 110, 18))
            view.addSubview_(title)
            count = _label("", _small(), secondary=True)
            count.setAlignment_(NSTextAlignmentRight)
            count.setFrame_(NSMakeRect(SIDEBAR - 70, y + 8, 46, 16))
            view.addSubview_(count)
            # One transparent button over the row takes the click.
            button = NSButton.buttonWithTitle_target_action_("", self.target, "nav:")
            button.setBordered_(False)
            button.setTransparent_(True)
            button.setTag_(index)
            button.setFrame_(NSMakeRect(10, y, SIDEBAR - 20, 32))
            view.addSubview_(button)
            self.nav_items[section] = (highlight, icon, title, count, button)
            y += 36
        self.nav_items[GENERAL][2].setStringValue_(T_NAV_GENERAL)
        self.nav_items[DELETED][2].setStringValue_(T_NAV_DELETED)

        self.sidebar_account = _label("", _small(), bold=True)
        self.sidebar_account.setFrame_(NSMakeRect(16, HEIGHT - 36, SIDEBAR - 32, 16))
        self.sidebar_account.setAutoresizingMask_(NSViewMinYMargin)
        view.addSubview_(self.sidebar_account)

    def _header(self, page, title: str):
        label = _label(title, 22, bold=True)
        label.setFrame_(NSMakeRect(PAD, 26, INNER - 330, 30))
        page.addSubview_(label)
        return label

    def _build_start(self, page, reopen_where: str) -> None:
        scroll, view = _scroll(NSMakeRect(0, 0, PAGE, HEIGHT), 1)
        page.addSubview_(scroll)
        title, height = _wrapping(T_START_TITLE, INNER, 20)
        title.setFont_(NSFont.boldSystemFontOfSize_(20))
        height = title.fittingSize().height
        title.setFrame_(NSMakeRect(PAD, 26, INNER, height))
        view.addSubview_(title)
        y = 26 + height + 6
        intro, height = _wrapping(T_START_INTRO, INNER, secondary=True)
        intro.setFrame_(NSMakeRect(PAD, y, INNER, height))
        view.addSubview_(intro)
        top = y + height + 24

        # Left: the three steps, then how to find the window again.
        left = 300
        y = top
        for number, (step, text) in enumerate(START_STEPS, start=1):
            circle = _pill(NSMakeRect(PAD, y, 24, 24), NSColor.quaternaryLabelColor())
            circle.contentView().addSubview_(_centered(str(number), NSMakeRect(0, 0, 24, 24), _small(), bold=True))
            view.addSubview_(circle)
            heading = _label(step, bold=True)
            heading.setFrame_(NSMakeRect(PAD + 36, y + 3, left - 36, 18))
            view.addSubview_(heading)
            body, height = _wrapping(text, left - 36, _small(), secondary=True)
            body.setFrame_(NSMakeRect(PAD + 36, y + 24, left - 36, height))
            view.addSubview_(body)
            y += 24 + height + 18
        hint, height = _wrapping(reopen_hint(reopen_where), left - 14, _small(), secondary=True)
        bar = _pill(NSMakeRect(PAD, y, 2, height), NSColor.controlAccentColor())
        bar.setCornerRadius_(1)
        view.addSubview_(bar)
        hint.setFrame_(NSMakeRect(PAD + 14, y, left - 14, height))
        view.addSubview_(hint)
        left_bottom = y + height

        # Right: the form, then "Giriş yap".
        x, width = PAD + left + 24, INNER - left - 24
        inner = width - 40
        card = _card(NSMakeRect(x, top, width, 100))
        content = card.contentView()
        y = 20
        heading = _label(T_START_FORM, 15, bold=True)
        heading.setFrame_(NSMakeRect(20, y, inner, 20))
        content.addSubview_(heading)
        y += 34
        label = _label(T_URL_LABEL)
        label.setFrame_(NSMakeRect(20, y, inner, 17))
        content.addSubview_(label)
        y += 22
        self.start_url = NSTextField.textFieldWithString_("")
        self.start_url.setPlaceholderString_(T_URL_PLACEHOLDER)
        self.start_url.setDelegate_(self.target)
        self.start_url.setFrame_(NSMakeRect(20, y, inner, FIELD_HEIGHT))
        content.addSubview_(self.start_url)
        y += FIELD_HEIGHT + 16
        label = _label(T_DEST_LABEL)
        label.setFrame_(NSMakeRect(20, y, inner, 17))
        content.addSubview_(label)
        y += 22
        choose = NSButton.buttonWithTitle_target_action_(T_CHOOSE_FOLDER, self.target, "chooseFolder:")
        choose_width = max(choose.fittingSize().width, 70)
        choose.setFrame_(NSMakeRect(20 + inner - choose_width, y - 4, choose_width, BUTTON_HEIGHT))
        content.addSubview_(choose)
        self.start_dest = NSTextField.textFieldWithString_("")
        self.start_dest.setDelegate_(self.target)
        self.start_dest.setFrame_(NSMakeRect(20, y, inner - choose_width - 8, FIELD_HEIGHT))
        content.addSubview_(self.start_dest)
        self.start_choose = choose
        y += FIELD_HEIGHT + 6
        note, height = _wrapping(T_DEST_ROOT_NOTE, inner, _small(), secondary=True)
        note.setFrame_(NSMakeRect(20, y, inner, height))
        content.addSubview_(note)
        y += height + 14
        self.start_autostart = NSButton.checkboxWithTitle_target_action_(T_AUTOSTART, self.target, "changed:")
        self.start_autostart.setFrame_(NSMakeRect(20, y, inner, 18))
        content.addSubview_(self.start_autostart)
        y += 18 + 18
        self.start_button = NSButton.buttonWithTitle_target_action_("", self.target, "start:")
        self.start_button.setFrame_(NSMakeRect(18, y, inner + 4, BUTTON_HEIGHT))
        _primary(self.start_button)
        content.addSubview_(self.start_button)
        y += BUTTON_HEIGHT + 8
        self.start_message, _ = _wrapping("", inner, _small(), secondary=True)
        self.start_message.setFrame_(NSMakeRect(20, y, inner, 32))
        content.addSubview_(self.start_message)
        y += 32 + 12
        card.setFrame_(NSMakeRect(x, top, width, y))
        content.setFrame_(NSMakeRect(0, 0, width, y))
        view.addSubview_(card)
        view.setFrame_(NSMakeRect(0, 0, PAGE, max(left_bottom, top + y) + PAD))

    def _build_overview(self, page) -> None:
        self.overview_title = self._header(page, "")
        self.sync_button = NSButton.buttonWithTitle_target_action_("", self.target, "sync:")
        _primary(self.sync_button)
        folder = NSButton.buttonWithTitle_target_action_(T_OPEN_FOLDER, self.target, "folder:")
        x = PAD + INNER
        for button, width in ((self.sync_button, 190), (folder, max(folder.fittingSize().width + 16, 110))):
            x -= width
            button.setFrame_(NSMakeRect(x, 24, width, BUTTON_HEIGHT))
            page.addSubview_(button)
            x -= 8
        self.folder_button = folder

        # The account and the last sync.
        self.account_card = _card(NSMakeRect(PAD, HEADER, INNER, 72))
        content = self.account_card.contentView()
        self.avatar = _pill(NSMakeRect(16, 16, 40, 40), NSColor.controlAccentColor().colorWithAlphaComponent_(0.18))
        content.addSubview_(self.avatar)
        self.avatar_text = _centered("", NSMakeRect(0, 0, 40, 40), 13, bold=True)
        self.avatar.contentView().addSubview_(self.avatar_text)
        self.account_title = _label("", 14, bold=True)
        content.addSubview_(self.account_title)
        self.account_detail = _label("", secondary=True)
        content.addSubview_(self.account_detail)
        self.account_message = _label("", _small())
        content.addSubview_(self.account_message)
        self.badge = _pill(NSMakeRect(0, 0, 10, 20), NSColor.systemGreenColor().colorWithAlphaComponent_(0.18))
        self.badge_text = _label("", _small())
        self.badge.contentView().addSubview_(self.badge_text)
        content.addSubview_(self.badge)
        self.login_button = NSButton.buttonWithTitle_target_action_("", self.target, "login:")
        _primary(self.login_button)
        content.addSubview_(self.login_button)
        page.addSubview_(self.account_card)

        # Son indirilenler: a click opens the file in its own application.
        self.recent_card = _card(NSMakeRect(PAD, HEADER + 88, INNER, HEIGHT - HEADER - 88 - PAD))
        self.recent_card.setAutoresizingMask_(NSViewHeightSizable)
        content = self.recent_card.contentView()
        content.setAutoresizingMask_(NSViewHeightSizable)
        heading = _label(T_RECENT, 13, bold=True)
        heading.setFrame_(NSMakeRect(20, 16, INNER - 140, 18))
        content.addSubview_(heading)
        self.recent_count = _label("", _small(), secondary=True)
        self.recent_count.setAlignment_(NSTextAlignmentRight)
        self.recent_count.setFrame_(NSMakeRect(INNER - 120, 18, 100, 16))
        content.addSubview_(self.recent_count)
        height = self.recent_card.frame().size.height
        self.recent_scroll, _ = _scroll(NSMakeRect(0, 46, INNER, height - 52), 1)
        content.addSubview_(self.recent_scroll)
        page.addSubview_(self.recent_card)

    def _layout_account(self) -> None:
        card = self.status.account
        width = INNER
        right = width - 16
        if card.action_title:
            self.login_button.setTitle_(card.action_title)
            button_width = max(self.login_button.fittingSize().width + 24, 110)
            self.login_button.setFrame_(NSMakeRect(right - button_width, 0, button_width, BUTTON_HEIGHT))
            right -= button_width + 12
        self.login_button.setHidden_(not card.action_title)
        self.login_button.setEnabled_(card.action_enabled)
        self.badge.setHidden_(not card.badge)
        if card.badge:
            self.badge_text.setStringValue_(card.badge)
            text = self.badge_text.fittingSize()
            badge_width = text.width + 20
            self.badge.setFrame_(NSMakeRect(right - badge_width, 0, badge_width, 22))
            self.badge_text.setFrame_(NSMakeRect(10, (22 - text.height) / 2, text.width, text.height))
            right -= badge_width + 12
        lines = 3 if card.message else 2
        height = 72 if lines == 2 else 90
        top = (height - 40) / 2
        self.avatar.setFrameOrigin_((16, top))
        text_width = right - 68
        for field, y, h in ((self.account_title, 0, 18), (self.account_detail, 20, 17), (self.account_message, 39, 16)):
            field.setFrame_(NSMakeRect(68, (height - lines * 19) / 2 + y, text_width, h))
        for control in (self.login_button, self.badge):
            frame = control.frame()
            control.setFrameOrigin_((frame.origin.x, (height - frame.size.height) / 2))
        page_height = self.pages[OVERVIEW].frame().size.height
        self.account_card.setFrame_(NSMakeRect(PAD, HEADER, INNER, height))
        self.account_card.contentView().setFrame_(NSMakeRect(0, 0, INNER, height))
        top = HEADER + height + GAP
        self.recent_card.setFrame_(NSMakeRect(PAD, top, INNER, max(page_height - top - PAD, 120)))

    def _build_general(self, page) -> None:
        self._header(page, T_NAV_GENERAL)
        self.form_scroll, view = _scroll(NSMakeRect(0, HEADER - 8, PAGE, HEIGHT - HEADER + 8), 1)
        page.addSubview_(self.form_scroll)
        inner = COLUMN - 40

        def card(x, y, width, build):
            box = _card(NSMakeRect(x, y, width, 100))
            content = box.contentView()
            height = build(content, width - 40)
            box.setFrame_(NSMakeRect(x, y, width, height))
            content.setFrame_(NSMakeRect(0, 0, width, height))
            view.addSubview_(box)
            return box, height

        def heading(content, text):
            title = _label(text, 13, bold=True)
            title.setFrame_(NSMakeRect(20, 18, COLUMN - 40, 18))
            content.addSubview_(title)
            return 18 + 18 + 12

        def text(content, value, y, width, small=False, secondary=False):
            field, height = _wrapping(value, width, _small() if small else None, secondary=secondary)
            field.setFrame_(NSMakeRect(20, y, width, height))
            content.addSubview_(field)
            return field, height

        def account(content, width):
            y = heading(content, T_SECTION_ACCOUNT)
            text(content, T_URL_LABEL, y, width)
            y += 22
            self.url_field = NSTextField.textFieldWithString_("")
            self.url_field.setPlaceholderString_(T_URL_PLACEHOLDER)
            self.url_field.setDelegate_(self.target)
            self.url_field.setFrame_(NSMakeRect(20, y, width, FIELD_HEIGHT))
            content.addSubview_(self.url_field)
            y += FIELD_HEIGHT + 6
            _, height = text(content, T_URL_HINT, y, width, small=True, secondary=True)
            y += height + 14
            self.account_button = NSButton.buttonWithTitle_target_action_("", self.target, "account:")
            self.account_button.setFrame_(NSMakeRect(20 + width - ACTION_WIDTH + 2, y - 4, ACTION_WIDTH, BUTTON_HEIGHT))
            content.addSubview_(self.account_button)
            self.account_label = NSTextField.wrappingLabelWithString_("")
            self.account_label.setPreferredMaxLayoutWidth_(width - ACTION_WIDTH - 8)
            self.account_label.setFrame_(NSMakeRect(20, y, width - ACTION_WIDTH - 8, 34))
            content.addSubview_(self.account_label)
            return y + 34 + 12

        def folder(content, width):
            y = heading(content, T_SECTION_FOLDER)
            text(content, T_DEST_LABEL, y, width)
            y += 22
            choose = NSButton.buttonWithTitle_target_action_(T_CHOOSE_FOLDER, self.target, "chooseFolder:")
            choose_width = max(choose.fittingSize().width, 70)
            choose.setFrame_(NSMakeRect(20 + width - choose_width + 2, y - 4, choose_width, BUTTON_HEIGHT))
            content.addSubview_(choose)
            self.dest_field = NSTextField.textFieldWithString_("")
            self.dest_field.setDelegate_(self.target)
            self.dest_field.setFrame_(NSMakeRect(20, y, width - choose_width - 8, FIELD_HEIGHT))
            content.addSubview_(self.dest_field)
            y += FIELD_HEIGHT + 6
            _, height = text(content, T_DEST_HINT, y, width, small=True, secondary=True)
            return y + height + 18

        def general(content, width):
            y = heading(content, T_SECTION_GENERAL)
            self.autostart = NSButton.checkboxWithTitle_target_action_(T_AUTOSTART, self.target, "changed:")
            self.autostart.setFrame_(NSMakeRect(20, y, width, 18))
            content.addSubview_(self.autostart)
            y += 18 + 14
            text(content, T_INTERVAL_LABEL, y, width)
            y += 22
            self.interval_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, y, width + 4, 25), False)
            self.interval_popup.addItemsWithTitles_([title for _, title in INTERVAL_OPTIONS])
            self.interval_popup.setTarget_(self.target)
            self.interval_popup.setAction_("changed:")
            content.addSubview_(self.interval_popup)
            return y + 25 + 18

        def past_terms(content, width):
            y = heading(content, T_SECTION_PAST_TERMS)
            self.past_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, y, width + 4, 25), False)
            content.addSubview_(self.past_popup)
            y += 25 + 8
            self.past_button = NSButton.buttonWithTitle_target_action_(T_PAST_DOWNLOAD, self.target, "pastTerm:")
            button_width = max(self.past_button.fittingSize().width + 16, 140)
            self.past_button.setFrame_(NSMakeRect(16, y, button_width, BUTTON_HEIGHT))
            content.addSubview_(self.past_button)
            y += BUTTON_HEIGHT + 6
            _, height = text(content, T_PAST_NOTE, y, width, small=True, secondary=True)
            y += height + 4
            self.past_label, _ = text(content, "", y, width, small=True, secondary=True)
            self.past_label.setFrame_(NSMakeRect(20, y, width, 30))
            return y + 30 + 8

        def updates(content, width):
            y = heading(content, T_SECTION_UPDATES)
            self.check_updates = NSButton.checkboxWithTitle_target_action_(T_CHECK_UPDATES, self.target, "changed:")
            self.check_updates.setFrame_(NSMakeRect(20, y, width, 18))
            content.addSubview_(self.check_updates)
            y += 18 + 14
            self.uninstall_button = NSButton.buttonWithTitle_target_action_(T_UNINSTALL, self.target, "uninstall:")
            self.update_button = NSButton.buttonWithTitle_target_action_("", self.target, "update:")
            x = 20 + width + 2
            for button in (self.uninstall_button, self.update_button):
                button_width = ACTION_WIDTH + 30 if button is self.update_button else max(
                    button.fittingSize().width + 16, 140)
                x -= button_width
                button.setFrame_(NSMakeRect(x, y - 4, button_width, BUTTON_HEIGHT))
                content.addSubview_(button)
                x -= 8
            self.version_label = _label("", secondary=True)
            self.version_label.setFrame_(NSMakeRect(20, y + 3, x - 20, 17))
            content.addSubview_(self.version_label)
            return y + BUTTON_HEIGHT + 12

        y = 8
        left, left_height = card(PAD, y, COLUMN, account)
        right, right_height = card(PAD + COLUMN + GAP, y, COLUMN, folder)
        for box in (left, right):
            box.setFrame_(NSMakeRect(box.frame().origin.x, y, COLUMN, max(left_height, right_height)))
        y += max(left_height, right_height) + GAP
        left, left_height = card(PAD, y, COLUMN, general)
        right, right_height = card(PAD + COLUMN + GAP, y, COLUMN, past_terms)
        for box in (left, right):
            box.setFrame_(NSMakeRect(box.frame().origin.x, y, COLUMN, max(left_height, right_height)))
        y += max(left_height, right_height) + GAP
        _, height = card(PAD, y, INNER, updates)
        y += height + PAD
        view.setFrame_(NSMakeRect(0, 0, PAGE, y))
        self.form_height = y

        # The bar under the form: only while something is not saved (or saving failed).
        self.button_bar = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, HEIGHT - BAR, PAGE, BAR))
        self.button_bar.setAutoresizingMask_(NSViewMinYMargin)
        line = NSBox.alloc().initWithFrame_(NSMakeRect(0, 0, PAGE, 1))
        line.setBoxType_(NSBoxSeparator)
        self.button_bar.addSubview_(line)
        self.cancel_button = NSButton.buttonWithTitle_target_action_(T_CANCEL, self.target, "cancel:")
        self.save_button = NSButton.buttonWithTitle_target_action_(T_SAVE, self.target, "save:")
        _primary(self.save_button)
        x = PAD + INNER
        for button in (self.save_button, self.cancel_button):
            width = max(button.fittingSize().width + 16, 90)
            x -= width
            button.setFrame_(NSMakeRect(x, (BAR - BUTTON_HEIGHT) / 2, width, BUTTON_HEIGHT))
            self.button_bar.addSubview_(button)
            x -= 8
        self.error_label = _label("", secondary=True)
        self.error_label.setFrame_(NSMakeRect(PAD, (BAR - 17) / 2, x - PAD - 8, 17))
        self.button_bar.addSubview_(self.error_label)
        page.addSubview_(self.button_bar)

    def _build_deleted(self, page) -> None:
        self._header(page, T_NAV_DELETED)
        hint, height = _wrapping(deleted.T_HINT, INNER, secondary=True)
        hint.setFrame_(NSMakeRect(PAD, 62, INNER, height))
        page.addSubview_(hint)
        y = 62 + height + 14
        self.select_all_button = NSButton.buttonWithTitle_target_action_(deleted.T_SELECT_ALL, self.target, "selectAll:")
        self.select_all_button.setFrame_(NSMakeRect(PAD - 6, y, max(self.select_all_button.fittingSize().width + 16, 110),
                                                    BUTTON_HEIGHT))
        page.addSubview_(self.select_all_button)
        y += BUTTON_HEIGHT + 10
        bottom = 2 * BUTTON_HEIGHT + 32  # the buttons and the result line below the list
        self.deleted_card = _card(NSMakeRect(PAD, y, INNER, HEIGHT - y - bottom))
        self.deleted_card.setAutoresizingMask_(NSViewHeightSizable)
        content = self.deleted_card.contentView()
        content.setAutoresizingMask_(NSViewHeightSizable)
        self.deleted_scroll, _ = _scroll(NSMakeRect(0, 1, INNER, HEIGHT - y - bottom - 2), 1)
        content.addSubview_(self.deleted_scroll)
        page.addSubview_(self.deleted_card)
        self.refetch_button = NSButton.buttonWithTitle_target_action_(deleted.T_DOWNLOAD, self.target, "refetch:")
        self.dismiss_button = NSButton.buttonWithTitle_target_action_(deleted.T_DISMISS, self.target, "dismiss:")
        _primary(self.refetch_button)
        x = PAD + INNER + 6
        for button in (self.refetch_button, self.dismiss_button):
            width = max(button.fittingSize().width + 16, 130)
            x -= width
            button.setFrame_(NSMakeRect(x, HEIGHT - bottom + 12, width, BUTTON_HEIGHT))
            button.setAutoresizingMask_(NSViewMinYMargin)
            page.addSubview_(button)
            x -= 8
        self.deleted_result = _label("", _small(), secondary=True)
        self.deleted_result.setFrame_(NSMakeRect(PAD, HEIGHT - bottom + 12 + BUTTON_HEIGHT + 8, INNER, 16))
        self.deleted_result.setAutoresizingMask_(NSViewMinYMargin)
        page.addSubview_(self.deleted_result)

    def fit_to_screen(self, screen=None) -> None:
        """Open at the size that shows everything, but never taller than ``screen`` allows.

        Only the height can change by hand; the window keeps its width.
        """
        screen = screen or self.window.screen() or NSScreen.mainScreen()
        if screen is None:
            return
        visible = screen.visibleFrame()
        frame = self.window.frameRectForContentRect_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        chrome = frame.size.height - HEIGHT
        height = window_height(HEIGHT, chrome, visible.size.height)
        self.window.setContentMinSize_((WIDTH, min(MIN_WINDOW_HEIGHT, height) - chrome))
        self.window.setContentMaxSize_((WIDTH, 100_000))
        self.window.setContentSize_((WIDTH, height - chrome))
        self.window.center()
        # center() leans towards the top; keep the whole window above the Dock.
        origin = self.window.frame().origin
        top = visible.origin.y + visible.size.height - height
        self.window.setFrameOrigin_((origin.x, max(visible.origin.y, min(origin.y, top))))
        self._layout_account()
        self._layout_bar()

    # -- behaviour ------------------------------------------------------------
    def show(self, section: str | None = None) -> None:
        """Open the window (or bring it forward) on ``section``; see ``WindowState.show``."""
        self.state.show(section)
        self._show_section()
        self.refresh_deleted()
        if not self.window.isVisible():
            self.fit_to_screen()
        if self.window.isMiniaturized():
            self.window.deminiaturize_(None)
        NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    def select(self, section: str) -> None:
        self.state.select(section)
        self._show_section()

    @property
    def section(self) -> str:
        return self.state.section

    def _show_section(self) -> None:
        section = self.state.section
        visible = "start" if section == OVERVIEW and self.status.first_run else section
        for name, page in self.pages.items():
            page.setHidden_(name != visible)
        # Return signs in on Başlangıç; a hidden button must not take the key elsewhere.
        self.start_button.setKeyEquivalent_("\r" if visible == "start" else "")
        for name, (highlight, icon, title, _count, button) in self.nav_items.items():
            selected = name == section
            highlight.setTransparent_(not selected)
            title.setFont_(NSFont.boldSystemFontOfSize_(13) if selected else NSFont.systemFontOfSize_(13))
            icon.setContentTintColor_(NSColor.controlAccentColor() if selected else NSColor.secondaryLabelColor())
            button.setAccessibilityLabel_(title.stringValue())
        if section == DELETED:
            self.refresh_deleted()

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

    def set_values(self, values: FormValues) -> None:
        """Show ``values`` as what is saved: the bar goes away."""
        self.saved = values
        for field in (self.url_field, self.start_url):
            field.setStringValue_(values.base_url)
        for field in (self.dest_field, self.start_dest):
            field.setStringValue_(values.dest)
        for box in (self.autostart, self.start_autostart):
            box.setState_(1 if values.autostart else 0)
        self.check_updates.setState_(1 if values.check_updates else 0)
        self.interval_popup.selectItemWithTitle_(interval_title(values.sync_interval_minutes))
        self.show_error("")

    def changed(self, control) -> None:
        """A field was edited: keep its twin on the other section in step, then the bar."""
        other = self.mirrors.get(control)
        if other is not None:
            if isinstance(control, NSTextField):
                other.setStringValue_(control.stringValue())
            else:
                other.setState_(control.state())
        self.error = ""
        self._layout_bar()

    def unsaved(self) -> bool:
        return has_changes(self.saved, self.values())

    def _layout_bar(self) -> None:
        visible = self.unsaved() or bool(self.error)
        self.button_bar.setHidden_(not visible)
        # Escape is Vazgeç only while the bar is in view.
        self.cancel_button.setKeyEquivalent_("\x1b" if visible else "")
        self.error_label.setStringValue_(self.error or T_UNSAVED)
        self.error_label.setTextColor_(NSColor.systemRedColor() if self.error else NSColor.secondaryLabelColor())
        height = self.pages[GENERAL].frame().size.height
        top = self.form_scroll.frame().origin.y
        self.form_scroll.setFrame_(NSMakeRect(0, top, PAGE, height - top - (BAR if visible else 0)))
        self.button_bar.setFrame_(NSMakeRect(0, height - BAR, PAGE, BAR))

    def show_error(self, message: str) -> None:
        self.error = message
        self._layout_bar()
        self._draw_start_message()

    def _draw_start_message(self) -> None:
        self.start_message.setStringValue_(self.error or self.status.start_message)
        self.start_message.setTextColor_(NSColor.systemRedColor() if self.error else NSColor.secondaryLabelColor())

    def discard(self) -> None:
        """Vazgeç: back to what is saved."""
        self.set_values(self.on_values())

    def update_status(self, status: MainStatus) -> None:
        first_run_changed = status.first_run != self.status.first_run
        self.status = status
        self.nav_items[OVERVIEW][2].setStringValue_(status.overview_title)
        self.nav_items[OVERVIEW][4].setAccessibilityLabel_(status.overview_title)
        self.sidebar_account.setStringValue_(status.account.title)
        if first_run_changed:
            self._show_section()
        # Başlangıç
        self.start_button.setTitle_(status.start_title)
        self.start_button.setEnabled_(status.start_enabled)
        self._draw_start_message()
        # Genel bakış
        self.overview_title.setStringValue_(status.overview_title)
        self.sync_button.setTitle_(status.sync_title)
        self.sync_button.setEnabled_(status.sync_enabled)
        card = status.account
        _tone(self.account_card, card.warning)
        self.avatar_text.setStringValue_(card.initials)
        self.avatar.setFillColor_((NSColor.systemOrangeColor() if card.warning else NSColor.controlAccentColor())
                                  .colorWithAlphaComponent_(0.18))
        self.account_title.setStringValue_(card.title)
        self.account_detail.setStringValue_(card.detail)
        self.account_message.setStringValue_(card.message)
        self.account_message.setToolTip_(card.message or None)
        self.account_message.setTextColor_(NSColor.systemOrangeColor() if card.warning else NSColor.secondaryLabelColor())
        self._layout_account()
        self._draw_recent()
        # Genel
        form = status.form
        self.account_label.setStringValue_(form.account)
        self.account_label.setTextColor_(NSColor.systemRedColor() if form.account_warning else NSColor.labelColor())
        self.account_button.setTitle_(form.account_title)
        self.account_button.setEnabled_(form.account_enabled)
        self.version_label.setStringValue_(form.version)
        self.update_button.setTitle_(form.update_title)
        self.update_button.setEnabled_(form.update_enabled)
        self.uninstall_button.setEnabled_(form.uninstall_enabled)
        if form.past_terms != self._past_terms:
            selected = self.past_popup.titleOfSelectedItem()
            self.past_popup.removeAllItems()
            self.past_popup.addItemsWithTitles_(list(form.past_terms))
            if selected in form.past_terms:
                self.past_popup.selectItemWithTitle_(selected)
            self._past_terms = form.past_terms
        self.past_popup.setEnabled_(bool(form.past_terms))
        self.past_button.setEnabled_(form.past_enabled)
        self.past_label.setStringValue_(form.past_message)
        self.past_label.setToolTip_(form.past_message or None)
        # Silinenler
        self.deleted_result.setStringValue_(form.deleted_message)
        self.refresh_deleted()

    def _draw_recent(self) -> None:
        rows = self.status.recent
        self.recent_count.setStringValue_(recent_count(rows))
        if rows == self._drawn_recent:
            return
        self._drawn_recent = rows
        width = INNER
        document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, width, max(len(rows) * ROW_HEIGHT, 1)))
        if not rows:
            empty = _label(T_RECENT_EMPTY, secondary=True)
            empty.setFrame_(NSMakeRect(20, 8, width - 40, 17))
            document.addSubview_(empty)
            document.setFrame_(NSMakeRect(0, 0, width, 40))
        for index, row in enumerate(rows):
            y = index * ROW_HEIGHT
            if index:
                line = NSBox.alloc().initWithFrame_(NSMakeRect(20, y, width - 40, 1))
                line.setBoxType_(NSBoxSeparator)
                document.addSubview_(line)
            icon = NSImageView.alloc().initWithFrame_(NSMakeRect(20, y + 10, 32, 32))
            icon.setImage_(file_icon(row.name))
            document.addSubview_(icon)
            name = _label(row.name, 13)
            name.setFrame_(NSMakeRect(64, y + 9, width - 120, 17))
            document.addSubview_(name)
            detail = _label(row.detail, _small(), secondary=True)
            detail.setFrame_(NSMakeRect(64, y + 28, width - 120, 15))
            document.addSubview_(detail)
            arrow = NSImageView.alloc().initWithFrame_(NSMakeRect(width - 40, y + 18, 16, 16))
            arrow.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_("arrow.up.right", None))
            arrow.setContentTintColor_(NSColor.tertiaryLabelColor())
            document.addSubview_(arrow)
            # The whole row is one transparent button on top.
            button = NSButton.buttonWithTitle_target_action_("", self.target, "openRecent:")
            button.setBordered_(False)
            button.setTransparent_(True)
            button.setTag_(index)
            button.setToolTip_(row.name)
            button.setFrame_(NSMakeRect(0, y, width, ROW_HEIGHT))
            document.addSubview_(button)
        self.recent_scroll.setDocumentView_(document)

    def refresh_deleted(self) -> None:
        rows = self.on_missing()
        self.selection.refresh(rows)
        self.nav_items[DELETED][3].setStringValue_(str(len(rows)) if rows else "")
        if rows != self._drawn_rows:
            width = INNER
            document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, width, 1))
            self.checks = {}
            self.check_keys = []
            if not rows:
                empty = _label(deleted.T_EMPTY, secondary=True)
                empty.setFrame_(NSMakeRect(20, 16, width - 40, 17))
                document.addSubview_(empty)
            for index, row in enumerate(rows):
                y = index * ROW_HEIGHT
                if index:
                    line = NSBox.alloc().initWithFrame_(NSMakeRect(16, y, width - 32, 1))
                    line.setBoxType_(NSBoxSeparator)
                    document.addSubview_(line)
                button = NSButton.checkboxWithTitle_target_action_("", self.target, "checked:")
                button.setFrame_(NSMakeRect(16, y + 16, 20, 20))
                button.setTag_(index)
                button.setState_(1 if row.key in self.selection.selected else 0)
                button.setAccessibilityLabel_(row.name)
                self.check_keys.append(row.key)
                self.checks[row.key] = button
                document.addSubview_(button)
                icon = NSImageView.alloc().initWithFrame_(NSMakeRect(44, y + 10, 32, 32))
                icon.setImage_(file_icon(row.name))
                document.addSubview_(icon)
                name = _label(row.name, 13)
                name.setFrame_(NSMakeRect(86, y + 9, width - 106, 17))
                name.setToolTip_(row.name)
                document.addSubview_(name)
                detail = _label(deleted_detail(row), _small(), secondary=True)
                detail.setFrame_(NSMakeRect(86, y + 28, width - 106, 15))
                detail.setToolTip_(row.folder)
                document.addSubview_(detail)
            document.setFrame_(NSMakeRect(0, 0, width, max(len(rows) * ROW_HEIGHT, 50)))
            self.deleted_scroll.setDocumentView_(document)
            self._drawn_rows = rows
        self.update_deleted_buttons()

    def update_deleted_buttons(self) -> None:
        enabled = self.status.form.refetch_enabled
        self.select_all_button.setEnabled_(enabled and bool(self.selection.rows))
        self.refetch_button.setTitle_(self.status.form.refetch_title)
        self.refetch_button.setEnabled_(enabled and bool(self.selection.keys()))
        self.dismiss_button.setEnabled_(enabled and bool(self.selection.keys()))
        for button in self.checks.values():
            button.setEnabled_(enabled)

    def select_all(self) -> None:
        self.selection.select_all()
        for button in self.checks.values():
            button.setState_(1)
        self.update_deleted_buttons()

    def deleted_action(self, action: str) -> None:
        keys = self.selection.keys()
        if not keys or not self.status.form.refetch_enabled:
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
        if name and self.status.form.past_enabled:
            self.on_past_term(str(name))

    def account_pressed(self) -> None:
        if self.status.form.account_action == "login":
            self.submit(login=True)  # sign in with the address in the field
        else:
            self.on_action(self.status.form.account_action)

    def submit(self, login: bool) -> None:
        """Save the form (Kaydet, or before signing in); the window stays open either way."""
        error = self.on_submit(self.values(), login)
        if error is None:
            self.set_values(self.on_values())
            return
        message, field = error
        self.show_error(message)
        if self.state.section == OVERVIEW and self.status.first_run:
            target = self.start_url if field == "base_url" else self.start_dest
        else:
            target = self.url_field if field == "base_url" else self.dest_field
        self.window.makeFirstResponder_(target)

    def choose_folder(self, sender=None) -> None:
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
            self.changed(self.dest_field)

    def close(self) -> None:
        self.window.close()  # windowWillClose_ reports it

    def closed(self) -> None:
        """The window went away: unsaved edits are dropped, the app keeps running."""
        self.state.closed()
        self.set_values(self.on_values())
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
