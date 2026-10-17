"""The main window (AppKit), laid out like Google Drive's: Başlangıç / Home, Sync activity, Announcements,
Dersler, Takvim and Ayarlar.

What the window shows and means lives in ``main_window_model.py`` (sections,
Home, the unsaved-changes bar) and ``settings_form.py`` (the Ayarlar
form, validation, what a changed school or folder implies); this module only
lays out controls, runs the folder picker and reports clicks. The sync
illustration is drawn by ``sync_scene_view.py``.
"""

from __future__ import annotations

import sys
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
    NSImageSymbolConfiguration,
    NSImageView,
    NSLineBreakByTruncatingTail,
    NSMenu,
    NSMenuItem,
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
from Foundation import NSURL, NSMakeRect, NSObject, NSTimer, NSRunLoop, NSRunLoopCommonModes

from blackboard_sync import __version__, courses, deadlines
from blackboard_sync.menubar.main_window_model import (
    ACTIVITY,
    COURSES,
    CALENDAR,
    GENERAL,
    HOME_DEADLINE_ROWS,
    HOME_ANNOUNCEMENT_ROWS,
    NAV_SECTIONS,
    OVERVIEW,
    START_STEPS,
    STATE_ATTENTION,
    STATE_ERROR,
    STATE_PAUSED,
    STATE_SYNCED,
    T_ACTIVITY_EMPTY,
    T_ALL_GOOD,
    T_ALL_GOOD_DETAIL,
    T_HOME_CALENDAR,
    T_HOME_ANNOUNCEMENTS,
    T_HOME_RECENT,
    T_NAME,
    T_NAV_ACTIVITY,
    T_NAV_GENERAL,
    T_NEEDS_ATTENTION,
    T_NEW,
    T_NO_DEADLINES,
    T_OPEN_CALENDAR,
    T_SIZE,
    T_STATUS,
    T_VIEW_ALL,
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
from blackboard_sync.menubar.model import T_RECENT_EMPTY
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
SCENE_HEIGHT = 84  # the small illustration in Home's status card while a sync runs
UPDATE_BANNER_HEIGHT = 86
# Home: the left column holds the status card and the last files, the right one notifications and due dates.
LEFT_W = 420
RIGHT_W = INNER - LEFT_W - GAP
STATUS_H = 150
SCENE_W = 124
ICON_W = 64  # the state symbol's column in the status card
HOME_ROW = 54  # a notification or due-date row on Home
CTRL = 36  # the round buttons at the top right
CTRL_Y = 20
# Buttons whose title changes with the app's state ("Giriş yap" / "Hesaptan
# çıkış yap") keep one width so the row does not jump.
ACTION_WIDTH = 160
NAV_SYMBOLS = {OVERVIEW: "house", ACTIVITY: "arrow.triangle.2.circlepath", ANNOUNCEMENTS: "megaphone",
               COURSES: "books.vertical", CALENDAR: "calendar"}
# The logo beside the name, without the app icon's background; the frozen app carries it in its bundle.
LOGO = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "assets" / "icon" / "logo.png"
# Home's state symbol and its tint.
STATE_SYMBOLS = {
    STATE_SYNCED: ("checkmark.icloud", "systemGreenColor"),
    STATE_PAUSED: ("pause.circle", "secondaryLabelColor"),
    STATE_ATTENTION: ("person.crop.circle.badge.exclamationmark", "systemOrangeColor"),
    STATE_ERROR: ("exclamationmark.icloud", "systemOrangeColor"),
}

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
        self.owner.select(NAV_SECTIONS[int(sender.tag())])

    def pause_(self, _sender):
        self.owner.on_action("pause")

    def gear_(self, _sender):
        self.owner.select(GENERAL)

    def accountMenu_(self, sender):
        self.owner.show_account_menu(sender)

    def homeAction_(self, _sender):
        self.owner.on_action(self.owner.status.home.action)

    def showActivity_(self, _sender):
        self.owner.select(ACTIVITY)

    def showAnnouncements_(self, _sender):
        self.owner.select(ANNOUNCEMENTS)

    def openHomeAnnouncement_(self, sender):
        rows = self.owner.home_announcements
        index = int(sender.tag())
        if 0 <= index < len(rows):
            self.owner.on_open_announcement(rows[index])

    def showCalendar_(self, _sender):
        self.owner.select(CALENDAR)

    def attention_(self, sender):
        self.owner.run_attention(int(sender.tag()))

    def openHomeDeadline_(self, sender):
        self.owner.on_deadline(self.owner.home_deadline_targets[int(sender.tag())])

    def openActivity_(self, sender):
        rows = self.owner.status.activity
        index = int(sender.tag())
        if 0 <= index < len(rows):
            self.owner.on_open(rows[index].path)

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


def _symbol_image(name: str, size: float):
    """An SF Symbol at ``size`` points (None when the system has no such symbol)."""
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if image is None:
        return None
    config = NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(size, 4, 2)
    return image.imageWithSymbolConfiguration_(config) or image


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
        self.home_deadline_targets = []
        self.home_announcements = ()
        self._drawn_home = None
        self._drawn_activity = None
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
        self._drawn_attention = None
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
                            (ACTIVITY, self._build_activity),
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
        self._build_topbar(root)
        # The fields Başlangıç and Ayarlar share edit the same draft.
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
        image = NSImage.alloc().initWithContentsOfFile_(str(LOGO))
        logo.setImage_(image if image is not None and image.isValid() else NSApp.applicationIconImage())
        logo.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        view.addSubview_(logo)
        name = _label(T_WINDOW_TITLE, 13, bold=True)
        name.setFrame_(NSMakeRect(60, 18, SIDEBAR - 72, 17))
        view.addSubview_(name)
        version = _label(__version__, _small(), secondary=True)
        version.setFrame_(NSMakeRect(60, 37, SIDEBAR - 72, 15))
        view.addSubview_(version)

        # Drive's "Open Drive folder": the one big button above the sections.
        # A rounded, filled pill with a folder symbol, like Drive's.
        pill = _card(NSMakeRect(14, 70, SIDEBAR - 28, 48))
        pill.setCornerRadius_(16)
        pill.setFillColor_(NSColor.quaternaryLabelColor())
        pill.setBorderWidth_(0)
        content = pill.contentView()
        folder_icon = NSImageView.alloc().initWithFrame_(NSMakeRect(16, 13, 22, 22))
        folder_icon.setImage_(_symbol_image("folder", 17))
        folder_icon.setContentTintColor_(NSColor.labelColor())
        content.addSubview_(folder_icon)
        folder_title = _label(T_OPEN_FOLDER, 14)
        folder_title.setFrame_(NSMakeRect(48, 14, SIDEBAR - 28 - 60, 20))
        content.addSubview_(folder_title)
        self.folder_button = NSButton.buttonWithTitle_target_action_("", self.target, "folder:")
        self.folder_button.setBordered_(False)
        self.folder_button.setTransparent_(True)
        self.folder_button.setAccessibilityLabel_(T_OPEN_FOLDER)
        self.folder_button.setToolTip_(T_OPEN_FOLDER)
        self.folder_button.setFrame_(NSMakeRect(0, 0, SIDEBAR - 28, 48))
        content.addSubview_(self.folder_button)
        view.addSubview_(pill)

        self.nav_items = {}
        y = 134
        for index, section in enumerate(NAV_SECTIONS):
            highlight = _pill(NSMakeRect(10, y, SIDEBAR - 20, 32), NSColor.quaternaryLabelColor())
            highlight.setCornerRadius_(6)
            view.addSubview_(highlight)
            icon = NSImageView.alloc().initWithFrame_(NSMakeRect(20, y + 7, 18, 18))
            icon.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_(NAV_SYMBOLS[section], None))
            view.addSubview_(icon)
            title = _label("", 13)
            title.setFrame_(NSMakeRect(46, y + 7, SIDEBAR - 46 - 50, 18))
            view.addSubview_(title)
            count = _label("", _small(), secondary=True)
            count.setAlignment_(NSTextAlignmentRight)
            count.setFrame_(NSMakeRect(SIDEBAR - 58, y + 8, 34, 16))
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
        self.nav_items[ACTIVITY][2].setStringValue_(T_NAV_ACTIVITY)
        self.nav_items[ANNOUNCEMENTS][2].setStringValue_(announcements.T_TAB)
        self.nav_items[COURSES][2].setStringValue_(T_NAV_COURSES)
        self.nav_items[CALENDAR][2].setStringValue_(deadlines.T_TAB)
        self.sidebar_view = view

    def _build_topbar(self, root) -> None:
        """Duraklat / Devam et, Ayarlar and the account: round buttons at the top right of every page."""
        self.topbar = []
        x = WIDTH - PAD - CTRL
        # The account (initials) opens a small menu: who is signed in, sign out or in, Ayarlar.
        self.avatar = _pill(NSMakeRect(x, CTRL_Y, CTRL, CTRL), NSColor.controlAccentColor().colorWithAlphaComponent_(0.18))
        self.avatar_text = _centered("", NSMakeRect(0, 0, CTRL, CTRL), 13, bold=True)
        self.avatar.contentView().addSubview_(self.avatar_text)
        root.addSubview_(self.avatar)
        self.avatar_button = NSButton.buttonWithTitle_target_action_("", self.target, "accountMenu:")
        self.avatar_button.setBordered_(False)
        self.avatar_button.setTransparent_(True)
        self.avatar_button.setFrame_(NSMakeRect(x, CTRL_Y, CTRL, CTRL))
        root.addSubview_(self.avatar_button)
        x -= CTRL + 8
        self.gear_button = self._round_button("gearshape", "gear:", x)
        self.gear_button.setToolTip_(T_NAV_GENERAL)
        self.gear_button.setAccessibilityLabel_(T_NAV_GENERAL)
        root.addSubview_(self.gear_button)
        x -= CTRL + 8
        self.pause_button = self._round_button("pause.circle", "pause:", x)
        root.addSubview_(self.pause_button)
        self.topbar = [self.avatar, self.avatar_button, self.gear_button, self.pause_button]

    def _round_button(self, symbol: str, action: str, x: float):
        button = NSButton.buttonWithTitle_target_action_("", self.target, action)
        button.setBordered_(False)
        button.setImage_(_symbol_image(symbol, 24))
        button.setImagePosition_(1)  # NSImageOnly
        button.setContentTintColor_(NSColor.secondaryLabelColor())
        button.setFrame_(NSMakeRect(x, CTRL_Y, CTRL, CTRL))
        return button

    def show_account_menu(self, sender) -> None:
        form = self.status.form
        menu = NSMenu.alloc().initWithTitle_("")
        header = menu.addItemWithTitle_action_keyEquivalent_(form.account, None, "")
        header.setEnabled_(False)
        menu.addItem_(NSMenuItem.separatorItem())
        action = menu.addItemWithTitle_action_keyEquivalent_(form.account_title, "account:", "")
        action.setTarget_(self.target)
        action.setEnabled_(form.account_enabled)
        settings = menu.addItemWithTitle_action_keyEquivalent_(T_NAV_GENERAL, "gear:", "")
        settings.setTarget_(self.target)
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0, CTRL + 4), sender)

    def run_attention(self, index: int) -> None:
        items = self.status.attention
        if 0 <= index < len(items) and items[index].action:
            self.on_action(items[index].action)

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
        self.overview_update_banner = self._build_update_banner(page)

        # Left: the status card (an illustration while a sync runs), then the last files.
        self.status_card = _card(NSMakeRect(PAD, HEADER, LEFT_W, STATUS_H))
        content = self.status_card.contentView()
        self.state_icon = NSImageView.alloc().initWithFrame_(NSMakeRect(18, 16, 44, 44))
        content.addSubview_(self.state_icon)
        self.scene_view = SyncSceneView.alloc().initWithFrame_(NSMakeRect(14, 8, SCENE_W, SCENE_HEIGHT - 4))
        content.addSubview_(self.scene_view)
        self.state_title = _label("", 22)
        content.addSubview_(self.state_title)
        self.state_detail = _label("", _small(), secondary=True)
        content.addSubview_(self.state_detail)
        # A note or the last error, the one thing the title and its line have no room for.
        self.account_message = _label("", _small())
        content.addSubview_(self.account_message)
        self.sync_button = NSButton.buttonWithTitle_target_action_("", self.target, "sync:")
        _primary(self.sync_button)
        self.sync_button.setFrame_(NSMakeRect(18, STATUS_H - BUTTON_HEIGHT - 16, 190, BUTTON_HEIGHT))
        content.addSubview_(self.sync_button)
        self.home_action = NSButton.buttonWithTitle_target_action_("", self.target, "homeAction:")
        self.home_action.setFrame_(NSMakeRect(216, STATUS_H - BUTTON_HEIGHT - 16, 130, BUTTON_HEIGHT))
        content.addSubview_(self.home_action)
        page.addSubview_(self.status_card)

        # Son indirilenler: a click opens the file in its own application.
        self.recent_card = _card(NSMakeRect(PAD, HEADER + STATUS_H + GAP, LEFT_W,
                                            HEIGHT - HEADER - STATUS_H - GAP - PAD))
        self.recent_card.setAutoresizingMask_(NSViewHeightSizable)
        content = self.recent_card.contentView()
        content.setAutoresizingMask_(NSViewHeightSizable)
        heading = _label(T_HOME_RECENT, 13, bold=True)
        heading.setFrame_(NSMakeRect(20, 16, LEFT_W - 140, 18))
        content.addSubview_(heading)
        self.recent_count = _label("", _small(), secondary=True)
        self.recent_count.setAlignment_(NSTextAlignmentRight)
        self.recent_count.setFrame_(NSMakeRect(LEFT_W - 120, 18, 100, 16))
        content.addSubview_(self.recent_count)
        height = self.recent_card.frame().size.height
        self.recent_scroll, _ = _scroll(NSMakeRect(0, 46, LEFT_W, height - 46 - 48), 1)
        content.addSubview_(self.recent_scroll)
        self.recent_all = NSButton.buttonWithTitle_target_action_(T_VIEW_ALL, self.target, "showActivity:")
        self.recent_all.setFrame_(NSMakeRect(14, height - 42, max(self.recent_all.fittingSize().width + 16, 100), 30))
        self.recent_all.setAutoresizingMask_(NSViewMinYMargin)
        content.addSubview_(self.recent_all)
        page.addSubview_(self.recent_card)

        # Right: what needs attention, then the next due dates.
        x = PAD + LEFT_W + GAP
        self.notify_card = _card(NSMakeRect(x, HEADER, RIGHT_W, 150))
        self.notify_body = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, RIGHT_W, 150))
        self.notify_card.contentView().addSubview_(self.notify_body)
        page.addSubview_(self.notify_card)
        self.calendar_card = _card(NSMakeRect(x, HEADER + 166, RIGHT_W, 150))
        self.calendar_body = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, RIGHT_W, 150))
        self.calendar_card.contentView().addSubview_(self.calendar_body)
        page.addSubview_(self.calendar_card)
        self._home_heights = (150, 150)

    def _card_heading(self, body, title: str, action: str | None = None, link: str = T_VIEW_ALL) -> None:
        heading = _label(title, 13, bold=True)
        heading.setFrame_(NSMakeRect(18, 16, RIGHT_W - 36, 18))
        body.addSubview_(heading)

    def _card_footer(self, body, y: float, title: str, action: str) -> float:
        button = NSButton.buttonWithTitle_target_action_(title, self.target, action)
        button.setFrame_(NSMakeRect(12, y, max(button.fittingSize().width + 16, 100), 30))
        body.addSubview_(button)
        return y + 30 + 12

    def _draw_home_notifications(self) -> float:
        """Home's Announcements card: what needs attention, then the newest announcements."""
        items = self.status.attention[:HOME_ANNOUNCEMENT_ROWS]
        rows = tuple(self.on_announcements()[:max(HOME_ANNOUNCEMENT_ROWS - len(items), 0)])
        key = ("announcements", items, rows)
        if key == getattr(self, "_drawn_home_notifications", None):
            return self._home_heights[0]
        self._drawn_home_notifications = key
        self.home_announcements = rows
        body = self.notify_body
        for view in list(body.subviews()):
            view.removeFromSuperview()
        self._card_heading(body, T_HOME_ANNOUNCEMENTS)
        y = 46
        if not items and not rows:
            icon = NSImageView.alloc().initWithFrame_(NSMakeRect(18, y + 2, 30, 30))
            icon.setImage_(_symbol_image("checkmark.circle", 24))
            icon.setContentTintColor_(NSColor.systemGreenColor())
            body.addSubview_(icon)
            title = _label(T_ALL_GOOD, 13, bold=True)
            title.setFrame_(NSMakeRect(56, y + 1, RIGHT_W - 74, 17))
            body.addSubview_(title)
            detail, height = _wrapping(T_ALL_GOOD_DETAIL, RIGHT_W - 74, _small(), secondary=True)
            detail.setFrame_(NSMakeRect(56, y + 20, RIGHT_W - 74, height))
            body.addSubview_(detail)
            return max(y + max(36, 22 + height) + 12, 120)
        for index, item in enumerate(items):
            self._attention_row(body, y, item, index, RIGHT_W, compact=True)
            y += HOME_ROW
        for index, row in enumerate(rows):
            title = _label(row.title, 12, bold=True)
            title.setFrame_(NSMakeRect(18, y, RIGHT_W - 36, 17))
            title.setToolTip_(row.title)
            body.addSubview_(title)
            detail = _label(row.detail, _small(), secondary=True)
            detail.setFrame_(NSMakeRect(18, y + 18, RIGHT_W - 36, 15))
            detail.setToolTip_(row.detail)
            body.addSubview_(detail)
            button = NSButton.buttonWithTitle_target_action_("", self.target, "openHomeAnnouncement:")
            button.setBordered_(False)
            button.setTransparent_(True)
            button.setTag_(index)
            button.setFrame_(NSMakeRect(0, y - 4, RIGHT_W, HOME_ROW - 8))
            body.addSubview_(button)
            y += HOME_ROW - 8
        return max(self._card_footer(body, y + 2, T_VIEW_ALL, "showAnnouncements:"), 120)

    def _attention_row(self, body, y: float, item, index: int, width: float, compact: bool) -> None:
        tint = NSColor.systemOrangeColor() if item.warning else NSColor.secondaryLabelColor()
        dot = _pill(NSMakeRect(18, y + 5, 8, 8), tint)
        body.addSubview_(dot)
        button_width = 0
        if item.action:
            button = NSButton.buttonWithTitle_target_action_(item.action_title, self.target, "attention:")
            button.setTag_(index)
            button_width = max(button.fittingSize().width + 12, 70) if not compact else 0
            if not compact:
                button.setFrame_(NSMakeRect(width - 20 - button_width, y, button_width, 28))
                body.addSubview_(button)
        text_width = width - 32 - 18 - (button_width + 8 if button_width else 0)
        title = _label(item.title, 12, bold=True)
        title.setFrame_(NSMakeRect(34, y, text_width, 17))
        title.setToolTip_(item.title)
        body.addSubview_(title)
        detail, height = _wrapping(item.detail, text_width, _small(), secondary=True)
        height = min(height, 32 if compact else 64)
        detail.setFrame_(NSMakeRect(34, y + 18, text_width, height))
        detail.setToolTip_(item.detail)
        body.addSubview_(detail)
        if compact and item.action:
            # On Home the whole row acts, so the card needs no button column.
            action = NSButton.buttonWithTitle_target_action_("", self.target, "attention:")
            action.setBordered_(False)
            action.setTransparent_(True)
            action.setTag_(index)
            action.setFrame_(NSMakeRect(0, y - 4, width, HOME_ROW))
            action.setToolTip_(item.action_title)
            body.addSubview_(action)

    def _draw_home_calendar(self) -> float:
        """Home's small calendar: the next due dates, a click opens the note or Blackboard."""
        page = self.on_deadlines()
        from datetime import datetime

        today = datetime.now().astimezone().date()
        rows = deadlines.upcoming_rows(page, HOME_DEADLINE_ROWS)
        key = ("calendar", rows, today)
        if key == getattr(self, "_drawn_home_calendar", None):
            return self._home_heights[1]
        self._drawn_home_calendar = key
        body = self.calendar_body
        for view in list(body.subviews()):
            view.removeFromSuperview()
        self.home_deadline_targets = []
        self._card_heading(body, T_HOME_CALENDAR)
        y = 46
        if not rows:
            empty, height = _wrapping(page.message or T_NO_DEADLINES, RIGHT_W - 36, _small(), secondary=True)
            empty.setFrame_(NSMakeRect(18, y, RIGHT_W - 36, height))
            body.addSubview_(empty)
            y += height + 14
        for row in rows:
            title = _label(row.title, 12, bold=True)
            title.setFrame_(NSMakeRect(18, y, RIGHT_W - 36, 17))
            title.setToolTip_(row.title)
            body.addSubview_(title)
            detail = _label(f"{deadlines.when_text(row, today)} · {row.course}", _small(), secondary=True)
            detail.setFrame_(NSMakeRect(18, y + 18, RIGHT_W - 36, 15))
            detail.setToolTip_(row.course)
            body.addSubview_(detail)
            button = NSButton.buttonWithTitle_target_action_("", self.target, "openHomeDeadline:")
            button.setBordered_(False)
            button.setTransparent_(True)
            button.setTag_(len(self.home_deadline_targets))
            self.home_deadline_targets.append(row.target)
            button.setFrame_(NSMakeRect(0, y - 4, RIGHT_W, HOME_ROW - 8))
            body.addSubview_(button)
            y += HOME_ROW - 8
        y = self._card_footer(body, y + 4, T_OPEN_CALENDAR, "showCalendar:")
        return max(y, 120)

    def _layout_overview(self) -> None:
        """Left: the status card and the last files; right: notifications and the next due dates."""
        status = self.status
        page_height = self.pages[OVERVIEW].frame().size.height
        top = HEADER
        if status.update_banner is not None:
            self.overview_update_banner[0].setFrame_(NSMakeRect(PAD, top, INNER, UPDATE_BANNER_HEIGHT))
            top += UPDATE_BANNER_HEIGHT + GAP
        self._layout_status_card()
        self.status_card.setFrame_(NSMakeRect(PAD, top, LEFT_W, STATUS_H))
        self.status_card.contentView().setFrame_(NSMakeRect(0, 0, LEFT_W, STATUS_H))
        recent_top = top + STATUS_H + GAP
        # A short window still shows the heading and some files; "Tümünü gör" needs room of its own.
        height = max(page_height - recent_top - PAD, 52)
        self.recent_card.setFrame_(NSMakeRect(PAD, recent_top, LEFT_W, height))
        self.recent_all.setHidden_(height < 110)
        notify_height = self._draw_home_notifications()
        calendar_height = self._draw_home_calendar()
        self._home_heights = (notify_height, calendar_height)
        x = PAD + LEFT_W + GAP
        for card, body, y, card_height in ((self.notify_card, self.notify_body, top, notify_height),
                                           (self.calendar_card, self.calendar_body, top + notify_height + GAP,
                                            calendar_height)):
            card.setFrame_(NSMakeRect(x, y, RIGHT_W, card_height))
            card.contentView().setFrame_(NSMakeRect(0, 0, RIGHT_W, card_height))
            body.setFrame_(NSMakeRect(0, 0, RIGHT_W, card_height))

    def _layout_status_card(self) -> None:
        """The state symbol or, while files change, the illustration; the words beside it."""
        status = self.status
        syncing = bool(status.scene)
        self.scene_view.setHidden_(not syncing)
        self.state_icon.setHidden_(syncing)
        x = 18 + (SCENE_W if syncing else ICON_W) + 8
        width = LEFT_W - x - 18
        self.state_title.setFrame_(NSMakeRect(x, 20, width, 28))
        self.state_detail.setFrame_(NSMakeRect(x, 54, width, 16))
        has_message = bool(status.account.message)
        self.account_message.setHidden_(not has_message)
        self.account_message.setFrame_(NSMakeRect(18, 82, LEFT_W - 36, 16))
        home = status.home
        symbol, tint = STATE_SYMBOLS.get(home.kind, STATE_SYMBOLS[STATE_SYNCED])
        self.state_icon.setImage_(_symbol_image(symbol, 38))
        self.state_icon.setContentTintColor_(getattr(NSColor, tint)())
        self.home_action.setHidden_(not home.action)
        if home.action:
            self.home_action.setTitle_(home.action_title)

    def _animate(self) -> None:
        """Run an illustration while it is in view and the window is open; stop it otherwise."""
        if self.status.scene and self.state.open and self.state.section == OVERVIEW:
            self.scene_view.start()
        else:
            self.scene_view.stop()
        if self.status.form.past_running and self.state.open and self.state.section == GENERAL:
            self.past_scene.start()
        else:
            self.past_scene.stop()

    def _build_activity(self, page) -> None:
        self._header(page, T_NAV_ACTIVITY)
        # Drive's table: Ad, Boyut, Durum.
        top = HEADER + 4
        for title, x, width, align in ((T_NAME, PAD + 20, 300, None), (T_SIZE, PAD + INNER - 230, 90, "right"),
                                       (T_STATUS, PAD + INNER - 120, 100, "center")):
            head = _label(title, _small(), bold=True, secondary=True)
            head.setFrame_(NSMakeRect(x, top, width, 16))
            if align == "right":
                head.setAlignment_(NSTextAlignmentRight)
            elif align == "center":
                head.setAlignment_(NSTextAlignmentCenter)
            page.addSubview_(head)
        self.activity_card = _card(NSMakeRect(PAD, top + 24, INNER, HEIGHT - top - 24 - PAD))
        self.activity_card.setAutoresizingMask_(NSViewHeightSizable)
        content = self.activity_card.contentView()
        content.setAutoresizingMask_(NSViewHeightSizable)
        height = self.activity_card.frame().size.height
        self.activity_scroll, _ = _scroll(NSMakeRect(0, 0, INNER, height), 1)
        content.addSubview_(self.activity_scroll)
        page.addSubview_(self.activity_card)

    def refresh_activity(self) -> None:
        rows = self.status.activity
        if rows == self._drawn_activity:
            return
        self._drawn_activity = rows
        width, row_height = INNER, 60
        document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, width, max(len(rows) * row_height, 56)))
        if not rows:
            empty = _label(T_ACTIVITY_EMPTY, secondary=True)
            empty.setFrame_(NSMakeRect(20, 18, width - 40, 17))
            document.addSubview_(empty)
        for index, row in enumerate(rows):
            y = index * row_height
            if index:
                line = NSBox.alloc().initWithFrame_(NSMakeRect(20, y, width - 40, 1))
                line.setBoxType_(NSBoxSeparator)
                document.addSubview_(line)
            icon = NSImageView.alloc().initWithFrame_(NSMakeRect(20, y + 14, 32, 32))
            icon.setImage_(file_icon(row.name))
            document.addSubview_(icon)
            name = _label(row.name, 13)
            name.setFrame_(NSMakeRect(64, y + 11, width - 330, 17))
            name.setToolTip_(row.name)
            document.addSubview_(name)
            detail = _label(f"{row.status} · {row.detail}", _small(), secondary=True)
            detail.setFrame_(NSMakeRect(64, y + 31, width - 330, 15))
            detail.setToolTip_(f"{row.status} · {row.detail}")
            document.addSubview_(detail)
            size = _label(row.size, 13, secondary=True)
            size.setAlignment_(NSTextAlignmentRight)
            size.setFrame_(NSMakeRect(width - 230, y + 21, 90, 17))
            document.addSubview_(size)
            check = NSImageView.alloc().initWithFrame_(NSMakeRect(width - 90, y + 20, 20, 20))
            check.setImage_(_symbol_image("checkmark", 14))
            check.setContentTintColor_(NSColor.systemGreenColor())
            document.addSubview_(check)
            button = NSButton.buttonWithTitle_target_action_("", self.target, "openActivity:")
            button.setBordered_(False)
            button.setTransparent_(True)
            button.setTag_(index)
            button.setToolTip_(row.name)
            button.setFrame_(NSMakeRect(0, y, width, row_height))
            document.addSubview_(button)
        self.activity_scroll.setDocumentView_(document)

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
        elif section == ACTIVITY:
            self.refresh_activity()
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
        # Home
        self.overview_title.setStringValue_(status.overview_title)
        self.sync_button.setTitle_(status.sync_title)
        self.sync_button.setEnabled_(status.sync_enabled)
        self.state_title.setStringValue_(status.home.title)
        self.state_detail.setStringValue_(status.home.detail)
        self.state_detail.setToolTip_(status.home.detail)
        self.account_message.setStringValue_(status.account.message)
        self.account_message.setToolTip_(status.account.message or None)
        self.account_message.setTextColor_(NSColor.systemOrangeColor() if status.account.warning
                                           else NSColor.secondaryLabelColor())
        self._layout_overview()
        self._animate()
        self._draw_recent()
        self.refresh_calendar()
        self.refresh_activity()
        self.refresh_announcements()
        if self.state.section == COURSES:
            self.refresh_courses()  # a sync may have found another course
        # The buttons at the top right: Duraklat / Devam et, Ayarlar and the account.
        for view in self.topbar:
            view.setHidden_(not status.shows_account)
        paused = status.paused
        self.pause_button.setImage_(_symbol_image("play.circle.fill" if paused else "pause.circle", 24))
        self.pause_button.setContentTintColor_(NSColor.controlAccentColor() if paused
                                               else NSColor.secondaryLabelColor())
        self.pause_button.setEnabled_(status.pause_enabled)
        self.pause_button.setToolTip_(status.pause_title)
        self.pause_button.setAccessibilityLabel_(status.pause_title)
        card = status.account
        self.avatar_text.setStringValue_(card.initials)
        self.avatar.setFillColor_((NSColor.systemOrangeColor() if card.warning else NSColor.controlAccentColor())
                                  .colorWithAlphaComponent_(0.18))
        self.avatar_button.setToolTip_(card.title)
        self.avatar_button.setAccessibilityLabel_(card.title)
        count = len(status.attention)
        self.nav_items[ANNOUNCEMENTS][3].setStringValue_(str(count) if count else "")
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
        width = LEFT_W
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
        attention = self.status.attention
        if rows == self._drawn_announcements and attention == self._drawn_attention:
            return
        self._drawn_announcements, self._drawn_attention = rows, attention
        document = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 1))
        y = 0
        # Drive's notifications on top: what needs the student (sign in again, an update, a failed sync).
        if attention:
            heading = _label(T_NEEDS_ATTENTION, 15, bold=True)
            heading.setFrame_(NSMakeRect(4, y, INNER - 8, 22))
            document.addSubview_(heading)
            y += 32
            for index, item in enumerate(attention):
                card = _card(NSMakeRect(0, y, INNER, 74), warning=item.warning)
                document.addSubview_(card)
                self._attention_row(card.contentView(), 16, item, index, INNER, compact=False)
                y += 74 + 12
            y += 8
        if not rows:
            empty, height = _wrapping(announcements.T_EMPTY, INNER - 40, secondary=True)
            empty.setFrame_(NSMakeRect(20, y + 16, INNER - 40, height))
            document.addSubview_(empty)
            y += height + 32
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
