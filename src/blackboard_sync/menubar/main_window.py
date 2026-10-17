"""The main window (AppKit): Başlangıç / Genel bakış, Dersler, Takvim, Duyurular and Genel.

What the window shows and means lives in ``main_window_model.py`` (sections,
the overview, the unsaved-changes bar) and ``settings_form.py`` (the Genel
form, validation, what a changed school or folder implies); this module only
lays out controls, runs the folder picker and reports clicks. The sync
illustration is drawn by ``sync_scene_view.py``.
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
    NSViewMaxYMargin,
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
from Foundation import NSURL, NSMakeRect, NSObject, NSTimer, NSRunLoop, NSRunLoopCommonModes

from blackboard_sync import __version__, courses, deadlines
from blackboard_sync.menubar.main_window_model import (
    COURSES,
    CALENDAR,
    SECTIONS,
    GENERAL,
    OVERVIEW,
    SCENE_COMPACT,
    SCENE_FIRST,
    START_STEPS,
    T_NAV_GENERAL,
    T_NEW,
    T_NAV_COURSES,
    T_OPEN_FOLDER,
    T_UPDATE_INTRO,
    T_START_FORM,
    T_START_INTRO,
    T_START_TITLE,
    T_UNSAVED,
    T_WINDOW_TITLE,
    MainStatus,
    WindowState,
    course_detail,
    course_title,
    enabled_count,
    has_changes,
    recent_count,
    reopen_hint,
)
from blackboard_sync.menubar.model import T_RECENT, T_RECENT_EMPTY
from blackboard_sync import announcements
from blackboard_sync.menubar.main_window_model import ANNOUNCEMENTS
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
    T_PAST_DOWNLOADING,
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
from blackboard_sync.menubar.sync_scene_view import SyncSceneView
from blackboard_sync.menubar.presentation import configure_main_window, present_main_window
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
# Genel, Eski dönemler: the button row is this tall and the illustration beside it this wide while a term downloads.
PAST_ROW = 56
PAST_SCENE_WIDTH = 96
AVATAR = 34  # the sidebar's account card
SCENE_HEIGHT = 84  # the small illustration above Son indirilenler while a sync runs
UPDATE_BANNER_HEIGHT = 86
FIRST_SCENE = (320, 187)  # the large one in the empty list on the first sync
# Buttons whose title changes with the app's state ("Giriş yap" / "Hesaptan
# çıkış yap") keep one width so the row does not jump.
ACTION_WIDTH = 160
NAV_SYMBOLS = {OVERVIEW: "house", COURSES: "books.vertical", CALENDAR: "calendar", ANNOUNCEMENTS: "megaphone",
               GENERAL: "gearshape"}

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
        self.owner.select(SECTIONS[int(sender.tag())])

    def openDeadline_(self, sender):
        self.owner.on_deadline(self.owner.deadline_targets[int(sender.tag())])

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

    def recentTick_(self, _timer):
        self.owner.observe_recent()

    def windowDidResignKey_(self, _notification):
        if self.owner.recent_seen is not None:
            self.owner.recent_seen.reset_exposure()

    def windowDidMiniaturize_(self, _notification):
        if self.owner.recent_seen is not None:
            self.owner.recent_seen.hide()

    def windowDidDeminiaturize_(self, _notification):
        self.owner._show_section()
        self.owner.on_section(self.owner.section)

    def start_(self, _sender):
        self.owner.submit(login=self.owner.status.start_login)

    def openAnnouncement_(self, sender):
        rows = self.owner._drawn_announcements or ()
        index = int(sender.tag())
        if 0 <= index < len(rows):
            self.owner.on_open_announcement(rows[index])

    def account_(self, _sender):
        self.owner.account_pressed()

    def changed_(self, sender):
        self.owner.changed(sender)

    def controlTextDidChange_(self, notification):
        self.owner.changed(notification.object())

    def courseToggled_(self, sender):
        self.owner.toggle_course(self.owner.course_ids[int(sender.tag())], bool(sender.state()))

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


def _wrapping(text: str, width: float, size: float | None = None, secondary: bool = False,
              bold: bool = False):
    """A multi-line label and the height it needs at ``width``."""
    field = NSTextField.wrappingLabelWithString_(text)
    font = NSFont.boldSystemFontOfSize_ if bold else NSFont.systemFontOfSize_
    field.setFont_(font(size or NSFont.systemFontSize()))
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
        on_courses=lambda: (),
        on_course_toggle: Callable[[str, bool], None] = lambda course_id, enabled: None,
        on_past_term: Callable[[str], object] = lambda name: None,
        on_section: Callable[[str], None] = lambda section: None,
        reopen_where: str = "Applications veya Launchpad'den",
        on_deadlines=deadlines.DeadlinePage,
        on_deadline: Callable[[str], None] = lambda target: None,
        recent_seen=None,
        on_seen=lambda: None,
        on_announcements=lambda: (),
        on_open_announcement=lambda row: None,
    ):
        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.on_section = on_section
        self.on_deadlines, self.on_deadline = on_deadlines, on_deadline
        self._drawn_deadlines = None
        self.deadline_targets = []
        self.recent_seen, self.on_seen = recent_seen, on_seen
        self._recent_timer = None
        self.on_values = on_values or (lambda: self.saved)
        self.on_open, self.on_past_term = on_open, on_past_term
        self.on_courses, self.on_course_toggle = on_courses, on_course_toggle
        self.on_announcements, self.on_open_announcement = on_announcements, on_open_announcement
        self.state = WindowState()
        self.status = status
        self.saved = values
        self.error = ""
        self._past_terms: tuple[str, ...] | None = None
        self._drawn_recent = None
        self._drawn_announcements = None
        self._drawn_courses = None
        self.course_ids: list[str] = []
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
        configure_main_window(self.window)
        self.window.setTitle_(T_WINDOW_TITLE)
        self.window.setDelegate_(self.target)
        root = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        self.window.setContentView_(root)
        self._build_sidebar(root)
        self.pages = {}
        for name, build in (("start", self._build_start), (OVERVIEW, self._build_overview),
                            (CALENDAR, self._build_calendar),
                            (ANNOUNCEMENTS, self._build_announcements),
                            (GENERAL, self._build_general), (COURSES, self._build_courses)):
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
        self.refresh_courses()  # the sidebar shows how many courses sync from the start
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
        for index, section in enumerate(SECTIONS):
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
        self.nav_items[ANNOUNCEMENTS][2].setStringValue_(announcements.T_TAB)
        self.nav_items[COURSES][2].setStringValue_(T_NAV_COURSES)
        self.nav_items[CALENDAR][2].setStringValue_(deadlines.T_TAB)

        # The account at the bottom: who is signed in, the last sync and a badge or "Giriş yap".
        self.sidebar_view = view
        width = SIDEBAR - 20
        self.account_card = _card(NSMakeRect(10, HEIGHT - 92, width, 80))
        self.account_card.setAutoresizingMask_(NSViewMinYMargin)
        content = self.account_card.contentView()
        self.avatar = _pill(NSMakeRect(12, 12, AVATAR, AVATAR),
                            NSColor.controlAccentColor().colorWithAlphaComponent_(0.18))
        content.addSubview_(self.avatar)
        self.avatar_text = _centered("", NSMakeRect(0, 0, AVATAR, AVATAR), 12, bold=True)
        self.avatar.contentView().addSubview_(self.avatar_text)
        self.account_title = _label("", 12, bold=True)
        content.addSubview_(self.account_title)
        self.badge = _pill(NSMakeRect(0, 0, 10, 18), NSColor.controlAccentColor().colorWithAlphaComponent_(0.18))
        self.badge_text = _label("", 10)
        self.badge.contentView().addSubview_(self.badge_text)
        content.addSubview_(self.badge)
        self.account_detail = _label("", _small() - 0.5, secondary=True)
        content.addSubview_(self.account_detail)
        self.login_button = NSButton.buttonWithTitle_target_action_("", self.target, "login:")
        _primary(self.login_button)
        content.addSubview_(self.login_button)
        view.addSubview_(self.account_card)

    def _header(self, page, title: str):
        label = _label(title, 22, bold=True)
        label.setFrame_(NSMakeRect(PAD, 26, INNER - 330, 30))
        page.addSubview_(label)
        return label

    def _build_start(self, page, reopen_where: str) -> None:
        scroll, view = _scroll(NSMakeRect(0, 0, PAGE, HEIGHT), 1)
        self.start_scroll = scroll
        page.addSubview_(scroll)
        self.start_update_banner = self._build_update_banner(page)
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

    def _build_update_banner(self, page):
        box = _card(NSMakeRect(PAD, HEADER, INNER, UPDATE_BANNER_HEIGHT))
        box.setFillColor_(NSColor.controlAccentColor().colorWithAlphaComponent_(0.08))
        box.setBorderColor_(NSColor.controlAccentColor().colorWithAlphaComponent_(0.4))
        content = box.contentView()
        title = _label("", 15, bold=True)
        title.setFrame_(NSMakeRect(20, 18, INNER - 176, 22))
        content.addSubview_(title)
        intro = _label(T_UPDATE_INTRO, _small(), secondary=True)
        intro.setFrame_(NSMakeRect(20, 48, INNER - 176, 18))
        content.addSubview_(intro)
        button = NSButton.buttonWithTitle_target_action_("", self.target, "update:")
        button.setFrame_(NSMakeRect(INNER - 140, (UPDATE_BANNER_HEIGHT - BUTTON_HEIGHT) / 2,
                                    120, BUTTON_HEIGHT))
        _primary(button)
        content.addSubview_(button)
        page.addSubview_(box)
        return box, title, button

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

        # A note or the last error, the one thing the sidebar's account card has no room for.
        self.account_message = _label("", _small())
        page.addSubview_(self.account_message)

        # While a sync runs and files are listed already: a small illustration above them.
        self.scene_card = _card(NSMakeRect(PAD, HEADER, INNER, SCENE_HEIGHT))
        content = self.scene_card.contentView()
        self.scene_view = SyncSceneView.alloc().initWithFrame_(NSMakeRect(14, 6, 124, SCENE_HEIGHT - 12))
        content.addSubview_(self.scene_view)
        self.scene_line = _label("", 13)
        self.scene_line.setFrame_(NSMakeRect(152, (SCENE_HEIGHT - 18) / 2, INNER - 172, 18))
        content.addSubview_(self.scene_line)
        page.addSubview_(self.scene_card)

        self.overview_update_banner = self._build_update_banner(page)

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
        # The first sync, before anything is listed: a large illustration in place of the empty list.
        self.first_scene = SyncSceneView.alloc().initWithFrame_(NSMakeRect(0, 0, *FIRST_SCENE))
        self.first_line = _label("", 13, secondary=True)
        self.first_line.setAlignment_(NSTextAlignmentCenter)
        for view in (self.first_scene, self.first_line):
            view.setAutoresizingMask_(NSViewMinYMargin | NSViewMaxYMargin)  # stays centred as the card grows
            content.addSubview_(view)
        page.addSubview_(self.recent_card)

    def _layout_account(self) -> None:
        """The sidebar's account card, kept at the bottom of the sidebar."""
        card = self.status.account
        width = SIDEBAR - 20
        text_x = 12 + AVATAR + 10
        self.badge.setHidden_(not card.badge)
        if card.badge:
            self.badge_text.setStringValue_(card.badge)
            text = self.badge_text.fittingSize()
            badge_width = min(text.width + 16, width - text_x - 10)
            self.badge.setFrame_(NSMakeRect(text_x + 1, 12 + AVATAR - 18 + 1, badge_width, 18))
            self.badge_text.setFrame_(NSMakeRect(8, (18 - text.height) / 2, badge_width - 16, text.height))
            self.account_title.setFrame_(NSMakeRect(text_x, 11, width - text_x - 10, 16))
        else:
            self.account_title.setFrame_(NSMakeRect(text_x, 12 + (AVATAR - 16) / 2, width - text_x - 10, 16))
        self.avatar.setFrameOrigin_((12, 12))
        y = 12 + AVATAR + 8
        self.account_detail.setFrame_(NSMakeRect(12, y, width - 24, 15))
        y += 15 + 10
        if card.action_title:
            self.login_button.setTitle_(card.action_title)
            self.login_button.setFrame_(NSMakeRect(8, y - 4, width - 16, BUTTON_HEIGHT))
            y += BUTTON_HEIGHT - 4 + 8
        self.login_button.setHidden_(not card.action_title)
        self.login_button.setEnabled_(card.action_enabled)
        sidebar_height = self.sidebar_view.frame().size.height
        self.account_card.setFrame_(NSMakeRect(10, sidebar_height - y - 12, width, y))
        self.account_card.contentView().setFrame_(NSMakeRect(0, 0, width, y))

    def _layout_overview(self) -> None:
        """The note, the small illustration while a sync runs, then Son indirilenler below."""
        status = self.status
        page_height = self.pages[OVERVIEW].frame().size.height
        top = HEADER
        self.account_message.setHidden_(not status.account.message)
        if status.account.message:
            self.account_message.setFrame_(NSMakeRect(PAD, top - 8, INNER, 16))
            top += 16
        compact = status.scene == SCENE_COMPACT
        self.scene_card.setHidden_(not compact)
        if compact:
            self.scene_card.setFrame_(NSMakeRect(PAD, top, INNER, SCENE_HEIGHT))
            top += SCENE_HEIGHT + GAP
        if status.update_banner is not None:
            self.overview_update_banner[0].setFrame_(NSMakeRect(PAD, top, INNER, UPDATE_BANNER_HEIGHT))
            top += UPDATE_BANNER_HEIGHT + GAP
        # A short window can still show the recent heading and scroll its files
        # while the scene, a message and the update banner are all visible.
        height = max(page_height - top - PAD, 52)
        self.recent_card.setFrame_(NSMakeRect(PAD, top, INNER, height))
        first = status.scene == SCENE_FIRST
        self.recent_scroll.setHidden_(first)
        self.first_scene.setHidden_(not first)
        self.first_line.setHidden_(not first)
        if first:
            width, scene_height = FIRST_SCENE
            # Smaller on a short window, so the line under it still shows.
            scene_height = max(60, min(scene_height, height - 46 - 40 - 16))
            width = scene_height * FIRST_SCENE[0] / FIRST_SCENE[1]
            y = 46 + max(0, (height - 46 - scene_height - 30) / 2 - 8)
            self.first_scene.setFrame_(NSMakeRect((INNER - width) / 2, y, width, scene_height))
            self.first_line.setFrame_(NSMakeRect(20, y + scene_height + 10, INNER - 40, 18))

    def _animate(self) -> None:
        """Run the illustration in view while the window is open; stop the other one."""
        for view, scene in ((self.scene_view, SCENE_COMPACT), (self.first_scene, SCENE_FIRST)):
            if self.status.scene == scene and self.state.open:
                view.start()
            else:
                view.stop()
        if self.status.form.past_running and self.state.open and self.state.section == GENERAL:
            self.past_scene.start()
        else:
            self.past_scene.stop()

    def _build_announcements(self, page) -> None:
        self._header(page, announcements.T_TAB)
        hint, height = _wrapping(announcements.T_HINT, INNER, _small(), secondary=True)
        hint.setFrame_(NSMakeRect(PAD, 62, INNER, height))
        page.addSubview_(hint)
        top = 62 + height + 16
        self.announcements_scroll, _ = _scroll(NSMakeRect(PAD, top, INNER, HEIGHT - top - PAD), 1)
        page.addSubview_(self.announcements_scroll)

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
            self.past_button.setFrame_(NSMakeRect(16, y + (PAST_ROW - BUTTON_HEIGHT) / 2, button_width, BUTTON_HEIGHT))
            content.addSubview_(self.past_button)
            # The papers fly into the folder beside the button for as long as the term is downloading.
            self.past_scene = SyncSceneView.alloc().initWithFrame_(
                NSMakeRect(16 + button_width + 12, y, PAST_SCENE_WIDTH, PAST_ROW))
            self.past_scene.setHidden_(True)
            content.addSubview_(self.past_scene)
            y += PAST_ROW + 4
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

    def _build_calendar(self, page) -> None:
        self._header(page, deadlines.T_TAB)
        hint, height = _wrapping(deadlines.T_HINT, INNER, secondary=True)
        hint.setFrame_(NSMakeRect(PAD, 62, INNER, height))
        page.addSubview_(hint)
        y = 62 + height + 16
        self.calendar_scroll, _ = _scroll(NSMakeRect(PAD, y, INNER, HEIGHT - y - PAD), 1)
        self.calendar_scroll.setAutoresizingMask_(NSViewHeightSizable)
        page.addSubview_(self.calendar_scroll)

    def refresh_calendar(self) -> None:
        data = self.on_deadlines()
        if data == self._drawn_deadlines:
            return
        self._drawn_deadlines = data
        self.deadline_targets = []
        document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 1))
        y = 8
        if data.message:
            message, height = _wrapping(data.message, INNER - 16, secondary=True)
            message.setFrame_(NSMakeRect(8, y, INNER - 16, height))
            document.addSubview_(message)
            y += height + 16
        if not data.days:
            empty = _label(deadlines.T_EMPTY, secondary=True)
            empty.setFrame_(NSMakeRect(8, y, INNER - 16, 20))
            document.addSubview_(empty)
            y += 32
        section = None
        for day in data.days:
            if day.past != section:
                section = day.past
                heading = _label(deadlines.T_PAST if day.past else deadlines.T_UPCOMING, 15, bold=True)
                heading.setFrame_(NSMakeRect(8, y, INNER - 16, 24))
                document.addSubview_(heading)
                y += 32
                if day.past:
                    hint, height = _wrapping(deadlines.T_PAST_HINT, INNER - 16, secondary=True)
                    hint.setFrame_(NSMakeRect(8, y, INNER - 16, height))
                    document.addSubview_(hint)
                    y += height + 12
            height = 42 + len(day.rows) * ROW_HEIGHT
            card = _card(NSMakeRect(0, y, INNER, height), warning=day.past)
            document.addSubview_(card)
            content = card.contentView()
            title = _label(day.title, 13, bold=True)
            title.setFrame_(NSMakeRect(16, 12, INNER - 32, 18))
            content.addSubview_(title)
            for index, row in enumerate(day.rows):
                top = 42 + index * ROW_HEIGHT
                time_label = _label(row.time, 13, bold=True)
                time_label.setFrame_(NSMakeRect(16, top + 10, 58, 20))
                content.addSubview_(time_label)
                name = _label(row.title, 13)
                name.setFrame_(NSMakeRect(86, top + 7, INNER - 102, 18))
                name.setToolTip_(row.title)
                content.addSubview_(name)
                course = _label(row.course, _small(), secondary=True)
                course.setFrame_(NSMakeRect(86, top + 27, INNER - 102, 18))
                course.setToolTip_(row.course)
                content.addSubview_(course)
                button = NSButton.buttonWithTitle_target_action_("", self.target, "openDeadline:")
                button.setBordered_(False)
                button.setTransparent_(True)
                button.setTag_(len(self.deadline_targets))
                self.deadline_targets.append(row.target)
                button.setAccessibilityLabel_(f"{row.title}, {row.course}, {row.time}")
                button.setToolTip_("İndirilen notu aç" if not row.target.startswith("https://") else "Blackboard'da aç")
                button.setFrame_(NSMakeRect(0, top, INNER, ROW_HEIGHT))
                content.addSubview_(button)
            y += height + 16
        document.setFrame_(NSMakeRect(0, 0, INNER, y))
        self.calendar_scroll.setDocumentView_(document)

    def _build_courses(self, page) -> None:
        self._header(page, T_NAV_COURSES)
        hint, height = _wrapping(courses.T_HINT, INNER, secondary=True)
        hint.setFrame_(NSMakeRect(PAD, 62, INNER, height))
        page.addSubview_(hint)
        y = 62 + height + 8
        untick, height = _wrapping(courses.T_UNTICK_HINT, INNER, _small(), secondary=True)
        untick.setFrame_(NSMakeRect(PAD, y, INNER, height))
        page.addSubview_(untick)
        y += height + 16
        self.courses_card = _card(NSMakeRect(PAD, y, INNER, HEIGHT - y - PAD))
        self.courses_card.setAutoresizingMask_(NSViewHeightSizable)
        content = self.courses_card.contentView()
        content.setAutoresizingMask_(NSViewHeightSizable)
        self.courses_scroll, _ = _scroll(NSMakeRect(0, 1, INNER, HEIGHT - y - PAD - 2), 1)
        content.addSubview_(self.courses_scroll)
        page.addSubview_(self.courses_card)

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
        self._layout_overview()
        self._layout_bar()

    # -- behaviour ------------------------------------------------------------
    def show(self, section: str | None = None) -> None:
        """Open the window (or bring it forward) on ``section``; see ``WindowState.show``."""
        self.state.show(section)
        self._show_section()
        self.refresh_courses()
        self._animate()
        if not self.window.isVisible():
            self.fit_to_screen()
        present_main_window(self.window, NSApp)
        if self.recent_seen is not None and self._recent_timer is None:
            self._recent_timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                0.25, self.target, "recentTick:", None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self._recent_timer, NSRunLoopCommonModes)

    def select(self, section: str) -> None:
        self.state.select(section)
        self._show_section()
        self._animate()  # the past-term illustration only moves while Genel is in view
        self.on_section(section)

    @property
    def section(self) -> str:
        return self.state.section

    def _show_section(self) -> None:
        section = self.state.section
        visible = "start" if section == OVERVIEW and self.status.first_run else section
        if self.recent_seen is not None:
            if self.state.open and visible == OVERVIEW:
                self.recent_seen.show()
            else:
                self.recent_seen.hide()
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
        if section == COURSES:
            self.refresh_courses()
        elif section == CALENDAR:
            self.refresh_calendar()
        elif section == ANNOUNCEMENTS:
            self.refresh_announcements()

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
        if first_run_changed:
            self._show_section()
        banner = status.update_banner
        for box, title, button in (self.start_update_banner, self.overview_update_banner):
            box.setHidden_(banner is None)
            if banner is not None:
                title.setStringValue_(banner.title)
                title.setToolTip_(banner.title)
                button.setTitle_(banner.button_title)
                button.setEnabled_(banner.enabled)
        self.start_update_banner[0].setFrameOrigin_((PAD, PAD))
        start_top = PAD + UPDATE_BANNER_HEIGHT + GAP if banner is not None else 0
        self.start_scroll.setFrame_(NSMakeRect(0, start_top, PAGE,
                                              self.pages["start"].frame().size.height - start_top))
        # Başlangıç
        self.start_button.setTitle_(status.start_title)
        self.start_button.setEnabled_(status.start_enabled)
        self._draw_start_message()
        # Genel bakış
        self.overview_title.setStringValue_(status.overview_title)
        self.sync_button.setTitle_(status.sync_title)
        self.sync_button.setEnabled_(status.sync_enabled)
        self.account_message.setStringValue_(status.account.message)
        self.account_message.setToolTip_(status.account.message or None)
        self.account_message.setTextColor_(NSColor.systemOrangeColor() if status.account.warning
                                           else NSColor.secondaryLabelColor())
        self.scene_line.setStringValue_(status.scene_line)
        self.first_line.setStringValue_(status.scene_line)
        self._layout_overview()
        self._animate()
        self._draw_recent()
        self.refresh_calendar()
        if self.state.section == COURSES:
            self.refresh_courses()  # a sync may have found another course
        # The account, at the bottom of the sidebar.
        self.account_card.setHidden_(not status.shows_account)
        card = status.account
        _tone(self.account_card, card.warning)
        self.avatar_text.setStringValue_(card.initials)
        self.avatar.setFillColor_((NSColor.systemOrangeColor() if card.warning else NSColor.controlAccentColor())
                                  .colorWithAlphaComponent_(0.18))
        self.account_title.setStringValue_(card.title)
        self.account_title.setToolTip_(card.title)
        self.account_detail.setStringValue_(card.detail)
        self.account_detail.setToolTip_(card.detail)
        self._layout_account()
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
        self.past_popup.setEnabled_(bool(form.past_terms) and not form.past_running)
        self.past_button.setEnabled_(form.past_enabled)
        self.past_button.setTitle_(T_PAST_DOWNLOADING if form.past_running else T_PAST_DOWNLOAD)
        self.past_scene.setHidden_(not form.past_running)
        self._animate()
        self.past_label.setStringValue_(form.past_message)
        self.past_label.setToolTip_(form.past_message or None)
        self.refresh_announcements()

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
            text_width = width - (170 if row.is_new else 120)
            name.setFrame_(NSMakeRect(64, y + 9, text_width, 17))
            document.addSubview_(name)
            detail = _label(row.detail, _small(), secondary=True)
            detail.setFrame_(NSMakeRect(64, y + 28, text_width, 15))
            document.addSubview_(detail)
            if row.is_new:
                pill = _pill(NSMakeRect(width - 76, y + 17, 52, 22),
                             NSColor.colorWithSRGBRed_green_blue_alpha_(37 / 255, 99 / 255, 235 / 255, 1))
                label = _centered(T_NEW, NSMakeRect(0, 0, 52, 22), 10, bold=True)
                label.setTextColor_(NSColor.whiteColor())
                pill.contentView().addSubview_(label)
                document.addSubview_(pill)
            arrow = NSImageView.alloc().initWithFrame_(NSMakeRect(width - 40, y + 18, 16, 16))
            arrow.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_("arrow.up.right", None))
            arrow.setContentTintColor_(NSColor.tertiaryLabelColor())
            if not row.is_new:
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

    def observe_recent(self) -> None:
        active = (self.state.open and self.section == OVERVIEW and not self.status.first_run
                  and self.window.isVisible() and not self.window.isMiniaturized()
                  and self.window.isKeyWindow() and NSApp.isActive())
        visible = []
        if active:
            rect = self.recent_scroll.documentVisibleRect()
            top, bottom = rect.origin.y, rect.origin.y + rect.size.height
            if rect.size.height > 0:
                visible = [(row.path, row.at) for index, row in enumerate(self.status.recent)
                           if index * ROW_HEIGHT < bottom and (index + 1) * ROW_HEIGHT > top]
        if self.recent_seen.observe(visible, active):
            self.on_seen()
    def refresh_announcements(self) -> None:
        rows = self.on_announcements()
        if rows == self._drawn_announcements:
            return
        self._drawn_announcements = rows
        document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 1))
        y = 0
        if not rows:
            empty, height = _wrapping(announcements.T_EMPTY, INNER - 40, secondary=True)
            empty.setFrame_(NSMakeRect(20, 16, INNER - 40, height))
            document.addSubview_(empty)
            y = height + 32
        for index, row in enumerate(rows):
            width = INNER - 40
            detail = _label(row.detail, _small(), secondary=True)
            detail.setFrame_(NSMakeRect(20, 16, width, 17))
            detail.setToolTip_(row.detail)
            title, title_height = _wrapping(row.title, width, 14, bold=True)
            title.setFrame_(NSMakeRect(20, 40, width, title_height))
            preview, preview_height = _wrapping(row.preview, width, _small(), secondary=True)
            preview.setFrame_(NSMakeRect(20, 48 + title_height, width, preview_height))
            height = 64 + title_height + preview_height
            card = _card(NSMakeRect(0, y, INNER, height))
            for label in (detail, title, preview):
                card.contentView().addSubview_(label)
            button = NSButton.buttonWithTitle_target_action_("", self.target, "openAnnouncement:")
            button.setBordered_(False)
            button.setTransparent_(True)
            button.setTag_(index)
            button.setAccessibilityLabel_(f"{row.title} · {row.detail}")
            button.setFrame_(NSMakeRect(0, 0, INNER, height))
            card.contentView().addSubview_(button)
            document.addSubview_(card)
            y += height + 12
        document.setFrame_(NSMakeRect(0, 0, INNER, max(y, 1)))
        self.announcements_scroll.setDocumentView_(document)

    def refresh_courses(self) -> None:
        """Draw Dersler again when the course list or a choice changed."""
        rows = self.on_courses()
        self.nav_items[COURSES][3].setStringValue_(enabled_count(rows))
        if rows == self._drawn_courses:
            return
        self._drawn_courses = rows
        width = INNER
        document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, width, 1))
        self.course_ids = []
        if not rows:
            empty = _label(courses.T_EMPTY, secondary=True)
            empty.setFrame_(NSMakeRect(20, 16, width - 40, 17))
            document.addSubview_(empty)
        for index, row in enumerate(rows):
            y = index * ROW_HEIGHT
            if index:
                line = NSBox.alloc().initWithFrame_(NSMakeRect(16, y, width - 32, 1))
                line.setBoxType_(NSBoxSeparator)
                document.addSubview_(line)
            title = course_title(row)
            button = NSButton.checkboxWithTitle_target_action_("", self.target, "courseToggled:")
            button.setFrame_(NSMakeRect(16, y + 16, 20, 20))
            button.setTag_(index)
            button.setState_(1 if row.enabled else 0)
            button.setAccessibilityLabel_(title)
            self.course_ids.append(row.id)
            document.addSubview_(button)
            name = _label(title, 13)
            name.setFrame_(NSMakeRect(48, y + 9, width - 68, 17))
            name.setToolTip_(title)
            if not row.enabled:
                name.setTextColor_(NSColor.secondaryLabelColor())
            document.addSubview_(name)
            detail = _label(course_detail(row), _small(), secondary=True)
            detail.setFrame_(NSMakeRect(48, y + 28, width - 68, 15))
            document.addSubview_(detail)
        document.setFrame_(NSMakeRect(0, 0, width, max(len(rows) * ROW_HEIGHT, 50)))
        self.courses_scroll.setDocumentView_(document)

    def toggle_course(self, course_id: str, enabled: bool) -> None:
        self.on_course_toggle(course_id, enabled)
        self.refresh_courses()

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
        if self._recent_timer is not None:
            self._recent_timer.invalidate()
            self._recent_timer = None
        if self.recent_seen is not None:
            self.recent_seen.hide()
        self._animate()
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
