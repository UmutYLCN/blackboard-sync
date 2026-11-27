"""The main window (Tk), laid out like Google Drive's: Başlangıç / Home, Sync activity, Announcements,
Dersler, Takvim and Ayarlar.

What the window shows and means lives in ``menubar/main_window_model.py`` and
``menubar/settings_form.py``, shared with macOS; this module only lays out Tk
widgets and reports clicks; ``sync_scene_view.py`` draws the sync illustration.
Closing only hides the window: the tray icon, the
timers and a running job go on, and the taskbar button leaves with the window.
"""

import base64
import io
import logging
import sys
from pathlib import Path

from blackboard_sync import (ai_launcher, announcements, courses, deadlines, runtime, schools, term_confirm, updater,
                             uninstall)
from . import package
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar import settings_form as form
from blackboard_sync.i18n import is_rtl, tr
from blackboard_sync.menubar.model import T_RECENT_EMPTY
from blackboard_sync.windows.pill_button import PillButton
from blackboard_sync.windows.school_search import SchoolSearch
from blackboard_sync.windows.sync_scene_view import SyncScene, background_of, is_dark, rounded
from blackboard_sync.windows.theme import course_badge_colors

log = logging.getLogger(__name__)

REOPEN_WHERE = tr("the Start menu")
WIDTH, HEIGHT = 940, 640  # the window's fixed size when the work area has room
MIN_WIDTH = 760
SIDEBAR = 200
# Buttons whose title follows the app's state keep one width (in characters).
ACTION_WIDTH = 24
WRAP = 600
# Title bar and borders Windows draws around the window (pixels).
CHROME = 40
TITLE_FONT = ("Segoe UI", 16, "bold")
HEADING_FONT = ("Segoe UI", 11, "bold")
BOLD_FONT = ("Segoe UI", 10, "bold")
# Home's state symbol and its colour.
HOME_SYMBOLS = {
    main.STATE_SYNCED: ("✓", "#236b45"),
    main.STATE_PAUSED: ("⏸", "#6b7280"),
    main.STATE_ATTENTION: ("!", "#d98200"),
    main.STATE_ERROR: ("!", "#d98200"),
}
WARNING = "#b00020"
MUTED = "#5f6b7a"
RUNNING = "#1f6fb2"
AVATAR = 34  # the account button at the top right
AVATAR_FILL, AVATAR_WARNING_FILL, AVATAR_TEXT = "#dce7f5", "#fbe3cf", "#1b2a44"
COMPACT_SCENE = (120, 70)  # in Home's status card while a sync runs
# Settings: a card of rows per section, like the macOS page. A row has its title and description on
# the left and its control on the right; the on/off settings are check boxes (Tk has no switch).
ROW_WRAP = 360  # the left text of a row wraps here first, then at the width the window leaves it
ROW_MIN_WRAP = 120
NOTEBOOKLM_WRAP = 420  # Home's NotebookLM card
AI_LOGO_SIZE = 24  # the logos on the AI card's buttons
AI_CURRENT_BORDER = "#2563eb"  # around the tool used last
DANGER_BORDER = "#d9534f"
# In the Microsoft Store build the Store owns updates and removal: no check box, no buttons.
PACKAGED_HIDDEN_ROWS = ("check_updates",)
# Which attributes of the window hold a row's control, its title and its description.
ROW_ATTRIBUTES = {
    "account": ("account_button", "account_label", None),
    "interval": ("interval_dropdown", None, None),
    "language": ("language_dropdown", None, None),
    "ai_terminal": ("ai_terminal_dropdown", None, None),
    "update": ("update_button", "version_label", None),
    "uninstall": ("uninstall_button", None, None),
}


class SettingsRowViews:
    """The widgets of one Settings row, so the app's state can reach them by the row's key."""

    def __init__(self, title, detail, control):
        self.title, self.detail, self.control = title, detail, control


def work_area(window=None):
    """(left, top, width, height) of the screen above the taskbar; ``window`` (Tk) is the fallback's source."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    if window is None:
        return 0, 0, 1280, 752
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight() - 48


def icon_path():
    """The app's icon for the title bar and the taskbar button (not Tk's feather)."""
    if runtime.is_frozen():
        return sys.executable  # the installed exe carries the icon
    return str(Path(__file__).resolve().parents[3] / "assets" / "icon" / "app.ico")


def scrolling(canvas, inner):
    """Show ``inner`` in ``canvas`` at the canvas's width, scrolling vertically."""
    child = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(child, width=e.width))


def right_justify(widget) -> None:
    """Arabic reads right to left: each label in a grid moves to the right side of its cell.

    The ttk style ends a label's lines on the right (theme.apply_theme); this places the labels.
    """
    for child in widget.winfo_children():
        if child.winfo_class() == "TLabel":
            sticky = str((child.grid_info() or {}).get("sticky", ""))
            if "w" in sticky and "e" not in sticky:
                child.grid_configure(sticky=sticky.replace("w", "e"))
        right_justify(child)


def wheel_steps(delta):
    """Lines to scroll for one mouse-wheel event; a touchpad's small deltas still move."""
    return int(-delta / 120) or (-1 if delta > 0 else 1)


def _badge_trailing_text(course_title: str, when: str, available_px: float) -> str:
    """Format "Title · Date" after a badge, truncating a long title with an ellipsis."""
    if not course_title:
        return when
    suffix = f" · {when}" if when else ""
    full = f"{course_title}{suffix}"
    if available_px <= 0:
        return full
    try:
        from tkinter import font as tkfont

        measure = tkfont.nametofont("TkDefaultFont").measure
    except Exception:
        measure = lambda text: len(text) * 7
    if measure(full) <= available_px:
        return full
    budget = available_px - measure(suffix)
    if budget <= measure("…"):
        return when or "…"
    clipped = course_title
    while len(clipped) > 1 and measure(clipped.rstrip() + "…") > budget:
        clipped = clipped[:-1]
    return f"{clipped.rstrip()}…{suffix}"


def _logo_image(master, key: str, dark: bool):
    """The tool's logo as a Tk image; None where it cannot be drawn (the button shows the name)."""
    try:
        import tkinter as tk
        from PIL import Image

        with Image.open(ai_launcher.logo_path(key, dark)) as picture:
            small = picture.convert("RGBA").resize((AI_LOGO_SIZE, AI_LOGO_SIZE), Image.LANCZOS)
        data = io.BytesIO()
        small.save(data, "PNG")
        return tk.PhotoImage(master=master, data=base64.b64encode(data.getvalue()))
    except Exception:
        log.warning("Could not draw the %s logo", key, exc_info=True)
        return None


class Tooltip:
    """``text`` under a widget while the pointer is over it (Tk has no tooltips of its own)."""

    def __init__(self, widget, text: str = ""):
        self.widget, self.text, self.window = widget, text, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)
        widget.bind("<ButtonPress>", self.hide)

    def show(self, _event=None):
        if self.window is not None or not self.text:
            return
        import tkinter as tk
        from tkinter import ttk

        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        below = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window.wm_geometry(f"+{self.widget.winfo_rootx()}+{below}")
        ttk.Label(self.window, text=self.text, padding=(6, 3), relief="solid", borderwidth=1).pack()

    def hide(self, _event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


class MainWindow:
    def __init__(self, root, values, status, on_submit, on_action, on_close, on_values=None,
                 on_open=lambda path: None, on_courses=lambda: (),
                 on_course_toggle=lambda course_id, enabled: None,
                 on_section=lambda section: None, on_deadlines=deadlines.DeadlinePage,
                 on_deadline=lambda target: None, recent_seen=None, on_seen=lambda: None,
                 on_announcements=lambda: (), on_open_announcement=lambda row: None,
                 on_reveal=lambda path: None):
        import tkinter as tk
        from tkinter import ttk

        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.on_section = on_section
        self.on_deadlines, self.on_deadline = on_deadlines, on_deadline
        self._drawn_deadlines = None
        self.recent_seen, self.on_seen = recent_seen, on_seen
        self._recent_after = None
        self._recent_entries = []
        self.on_values = on_values or (lambda: self.saved)
        self.on_open, self.on_courses = on_open, on_courses
        self.on_course_toggle = on_course_toggle
        self.on_announcements, self.on_open_announcement = on_announcements, on_open_announcement
        self.on_reveal = on_reveal
        self.state = main.WindowState()
        self.status = status
        self.saved = values
        self.error = ""
        self._drawn_courses = None
        self._drawn_recent = None
        self._drawn_home_notifications = None
        self._drawn_home_calendar = None
        self._drawn_activity = None
        self.school_searches = []
        self._drawn_announcements = None
        self._loading = False

        self.window = window = tk.Toplevel(root)
        window.withdraw()  # shown by show(), once it has its size
        window.title(main.T_WINDOW_TITLE)
        try:
            window.iconbitmap(icon_path())
        except Exception:  # no icon resource: Tk's own icon is fine
            log.debug("Could not set the window icon", exc_info=True)
        window.columnconfigure(1, weight=1)
        window.rowconfigure(0, weight=1)
        window.protocol("WM_DELETE_WINDOW", self.close)
        if self.recent_seen is not None:
            window.bind("<Unmap>", self._recent_unmapped)
            window.bind("<Map>", self._recent_mapped)
            window.bind("<FocusOut>", self._recent_focus_out)

        # The form's values; Başlangıç and Genel share them.
        self.url = tk.StringVar(value=values.base_url)
        self.dest = tk.StringVar(value=values.dest)
        self.autostart = tk.BooleanVar(value=values.autostart)
        self.check_updates = tk.BooleanVar(value=values.check_updates)
        self.auto_relogin = tk.BooleanVar(value=values.auto_relogin)
        self.notebooklm_auto = tk.BooleanVar(value=values.notebooklm_auto)
        self.ai_terminal = tk.StringVar(value="")
        self.ai_resume = tk.BooleanVar(value=values.ai_resume)
        self._terminal_choices = ()
        self._terminal_initial_title = ""
        self.interval = tk.StringVar(value=form.interval_title(values.sync_interval_minutes))
        self.language = tk.StringVar(value=form.language_title(values.language))
        self.section_var = tk.StringVar(value=main.OVERVIEW)

        self._build_sidebar(window)
        self.pages = {}
        for name, build in (("start", self._build_start), (main.OVERVIEW, self._build_overview),
                            (main.ACTIVITY, self._build_activity),
                            (main.CALENDAR, self._build_calendar),
                            (main.ANNOUNCEMENTS, self._build_announcements),
                            (main.GENERAL, self._build_general), (main.COURSES, self._build_courses)):
            page = ttk.Frame(window, padding=(24, 20, 24, 16))
            page.grid(row=0, column=1, sticky="nsew")
            page.grid_remove()
            self.pages[name] = page
            build(page)
        for variable in (self.url, self.dest, self.autostart, self.check_updates, self.interval, self.language,
                         self.auto_relogin, self.notebooklm_auto, self.ai_terminal, self.ai_resume):
            variable.trace_add("write", lambda *_args: self.changed())
        # The wheel scrolls the section in view wherever the pointer is; over a
        # list it scrolls too instead of changing the choice.
        window.bind("<MouseWheel>", self.wheel)
        for combobox in (self.interval_dropdown, self.language_dropdown, self.ai_terminal_dropdown):
            combobox.bind("<MouseWheel>", lambda e: self.wheel(e) or "break")
        self._build_topbar(window)
        self.update_status(status)
        self.set_values(values)
        self._show_section()
        if is_rtl():
            right_justify(window)

    # -- layout --------------------------------------------------------------
    def _build_sidebar(self, window):
        from tkinter import ttk

        bar = ttk.Frame(window, padding=(14, 18, 14, 16), width=SIDEBAR)
        bar.grid(row=0, column=0, sticky="ns")
        bar.rowconfigure(3 + len(main.NAV_SECTIONS), weight=1)
        ttk.Label(bar, text=main.T_WINDOW_TITLE, font=HEADING_FONT).grid(row=0, column=0, sticky="w", pady=(0, 14))
        # Drive's "Open Drive folder": the one big button above the sections.
        ttk.Button(bar, text=main.T_OPEN_FOLDER, command=lambda: self.on_action("folder")).grid(
            row=2, column=0, sticky="ew", ipady=6, pady=(0, 14))
        self.nav = {}
        for row, section in enumerate(main.NAV_SECTIONS, start=3):
            button = ttk.Radiobutton(bar, style="Navigation.TRadiobutton", variable=self.section_var, value=section,
                                     width=22, command=lambda s=section: self.select(s))
            button.grid(row=row, column=0, sticky="ew", pady=2)
            self.nav[section] = button

    def _build_topbar(self, window):
        """Duraklat / Devam et, Ayarlar and the account: buttons at the top right of every page."""
        import tkinter as tk
        from tkinter import ttk

        bar = ttk.Frame(window)
        self.topbar = bar
        self.pause_button = ttk.Button(bar, text="⏸", width=3, command=lambda: self.on_action("pause"))
        self.pause_button.pack(side="left", padx=(0, 6))
        self.gear_button = ttk.Button(bar, text="⚙", width=3, command=lambda: self.select(main.GENERAL))
        self.gear_button.pack(side="left", padx=(0, 6))
        # The account (initials) only shows who is signed in; Ayarlar has Sign in / Sign out.
        self.avatar = tk.Canvas(bar, width=AVATAR, height=AVATAR, highlightthickness=0, borderwidth=0,
                                background=background_of(window))
        self.avatar.pack(side="left")
        bar.place(relx=1.0, x=-24, y=14, anchor="ne")
        bar.lift()

    def _header(self, page, title, row=0):
        from tkinter import ttk

        label = ttk.Label(page, text=title, font=TITLE_FONT)
        label.grid(row=row, column=0, sticky="w", pady=(0, 12))
        return label

    def _scroll_area(self, page, row):
        """A vertically scrolling frame in ``page``; returns (canvas, frame)."""
        import tkinter as tk
        from tkinter import ttk

        canvas = tk.Canvas(page, highlightthickness=0, background=background_of(page))
        canvas.grid(row=row, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=row, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        frame = ttk.Frame(canvas)
        scrolling(canvas, frame)
        page.rowconfigure(row, weight=1)
        page.columnconfigure(0, weight=1)
        return canvas, frame

    def _build_start(self, page):
        from tkinter import ttk

        self.start_update_banner = self._build_update_banner(page, 0)
        self.start_license_banner = self._build_license_banner(page, 1)
        self.start_canvas, frame = self._scroll_area(page, 2)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=main.T_START_TITLE, font=TITLE_FONT, wraplength=WRAP).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text=main.T_START_INTRO, foreground=MUTED, wraplength=WRAP).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 20))
        steps = ttk.Frame(frame)
        steps.grid(row=2, column=0, sticky="nw", padx=(0, 24))
        for number, (title, text) in enumerate(main.START_STEPS):
            ttk.Label(steps, text=str(number + 1), font=BOLD_FONT, width=2, anchor="center").grid(
                row=2 * number, column=0, sticky="nw")
            ttk.Label(steps, text=title, font=BOLD_FONT).grid(row=2 * number, column=1, sticky="w")
            ttk.Label(steps, text=text, foreground=MUTED, wraplength=260).grid(
                row=2 * number + 1, column=1, sticky="w", pady=(2, 14))
        ttk.Label(steps, text=main.reopen_hint(REOPEN_WHERE), foreground=MUTED, wraplength=280).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

        card = ttk.LabelFrame(frame, text=main.T_START_FORM, padding=16)
        card.grid(row=2, column=1, sticky="new")
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=form.T_URL_LABEL).grid(row=0, column=0, columnspan=2, sticky="w")
        self.start_fields = {"base_url": ttk.Combobox(card, textvariable=self.url, width=40,
                                                       values=schools.suggestions())}
        self.start_fields["base_url"].grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        self.school_searches.append(SchoolSearch(self.window, self.start_fields["base_url"], self.url))
        ttk.Label(card, text=form.T_DEST_LABEL).grid(row=2, column=0, columnspan=2, sticky="w")
        self.start_fields["dest"] = ttk.Entry(card, textvariable=self.dest)
        self.start_fields["dest"].grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(card, text=form.T_CHOOSE_FOLDER, command=self.choose_folder).grid(row=3, column=1, padx=(8, 0))
        ttk.Label(card, text=form.T_DEST_ROOT_NOTE, foreground=MUTED, wraplength=300).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Checkbutton(card, text=form.T_AUTOSTART, variable=self.autostart).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.start_button = ttk.Button(card, style="Accent.TButton",
                                       command=lambda: self.submit(self.status.start_login))
        self.start_button.grid(row=6, column=0, columnspan=2, sticky="ew")
        self.start_message = ttk.Label(card, wraplength=300)
        self.start_message.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_update_banner(self, page, row):
        from tkinter import ttk

        card = ttk.LabelFrame(page, padding=(16, 14))
        card.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        card.columnconfigure(0, weight=1)
        title = ttk.Label(card, font=HEADING_FONT, wraplength=WRAP - 160)
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=main.T_UPDATE_INTRO, wraplength=WRAP - 160).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        button = ttk.Button(card, style="Accent.TButton", default="active", width=14,
                            command=lambda: self.on_action(self.status.form.update_action))
        button.grid(row=0, column=1, rowspan=2, padx=(16, 0))
        return card, title, button

    def _build_license_banner(self, page, row):
        from tkinter import ttk

        card = ttk.LabelFrame(page, padding=(16, 12))
        card.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        card.columnconfigure(0, weight=1)
        title = ttk.Label(card, font=HEADING_FONT, wraplength=WRAP - 200)
        title.grid(row=0, column=0, sticky="w")
        detail = ttk.Label(card, wraplength=WRAP - 200)
        detail.grid(row=1, column=0, sticky="w", pady=(2, 0))
        notice = ttk.Label(card, foreground=WARNING, wraplength=WRAP - 200)
        notice.grid(row=2, column=0, sticky="w", pady=(4, 0))
        buttons = ttk.Frame(card)
        buttons.grid(row=0, column=1, rowspan=3, sticky="e", padx=(16, 0))
        buy = ttk.Button(buttons, style="Accent.TButton",
                         command=lambda: self.on_action(main.LICENSE_BUY_ACTION))
        buy.pack(side="left")
        restore = ttk.Button(buttons, command=lambda: self.on_action(main.LICENSE_RESTORE_ACTION))
        restore.pack(side="left", padx=(8, 0))
        card.grid_remove()
        return card, title, detail, notice, buy, restore

    def _draw_license_banner(self, view, data):
        box, title, detail, notice, buy, restore = view
        if data is None:
            box.grid_remove()
            return
        title.configure(text=data.title)
        if data.title:
            title.grid()
        else:
            title.grid_remove()
        detail.configure(text=data.detail, foreground=MUTED if data.kind == main.LICENSE_TRIAL else "")
        notice.configure(text=data.notice)
        if data.notice:
            notice.grid()
        else:
            notice.grid_remove()
        buy.configure(text=data.buy_title, state="normal" if data.buy_enabled else "disabled")
        restore.pack_forget()
        if data.restore_action:
            restore.configure(text=data.restore_title, state="normal" if data.restore_enabled else "disabled")
            restore.pack(side="left", padx=(8, 0))
        box.grid()

    def window_handle(self):
        """The Win32 HWND for modal Store purchase dialogs (``IInitializeWithWindow``)."""
        for getter in (lambda: int(str(self.window.wm_frame()), 16), lambda: int(self.window.winfo_id())):
            try:
                hwnd = getter()
                if hwnd:
                    return hwnd
            except Exception:
                continue
        return None

    def _build_overview(self, page):
        from tkinter import ttk

        # Home's header: a greeting, and under it one line about the next due dates (hidden without any).
        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.overview_title = ttk.Label(header, font=TITLE_FONT)
        self.overview_title.grid(row=0, column=0, sticky="w")
        self.overview_subtitle = ttk.Label(header, foreground=MUTED)
        self.overview_subtitle.grid(row=1, column=0, sticky="w")
        self.overview_subtitle.grid_remove()
        # Everything under the header scrolls: the window cannot grow to show what does not fit,
        # and the buttons at the top right stay clear of it.
        outer = page
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)
        self.overview_holder = ttk.Frame(outer)
        self.overview_holder.grid(row=1, column=0, sticky="nsew")
        self.overview_canvas, page = self._scroll_area(self.overview_holder, 0)
        self.update_required_frame = ttk.LabelFrame(outer, padding=(24, 36))
        self.update_required_frame.grid(row=1, column=0, sticky="nsew")
        self.update_required_frame.rowconfigure(0, weight=1)
        self.update_required_frame.rowconfigure(5, weight=1)
        self.update_required_frame.columnconfigure(0, weight=1)
        self.update_required_title = ttk.Label(
            self.update_required_frame, font=TITLE_FONT, wraplength=440, justify="center"
        )
        self.update_required_title.grid(row=1, column=0, pady=(0, 8))
        self.update_required_detail = ttk.Label(
            self.update_required_frame, foreground=MUTED, wraplength=440, justify="center"
        )
        self.update_required_detail.grid(row=2, column=0, pady=(0, 8))
        self.update_required_notice = ttk.Label(
            self.update_required_frame, foreground=WARNING, wraplength=440, justify="center"
        )
        self.update_required_notice.grid(row=3, column=0, pady=(0, 8))
        self.update_required_notice.grid_remove()
        self.update_required_button = ttk.Button(
            self.update_required_frame,
            style="Accent.TButton",
            padding=(16, 4),
            command=lambda: self.on_action(main.REQUIRED_UPDATE_ACTION),
        )
        self.update_required_button.grid(row=4, column=0, pady=(8, 0))
        self.update_required_frame.grid_remove()
        page.columnconfigure(0, weight=3, uniform="home")
        page.columnconfigure(1, weight=2, uniform="home")
        self.overview_license_banner = self._build_license_banner(page, 0)
        self.overview_update_banner = self._build_update_banner(page, 1)
        background = background_of(page)

        # Left: Drive's status card: the state in words, the last files and "View all".
        left = ttk.Frame(page)
        left.grid(row=2, column=0, rowspan=2, sticky="new", padx=(0, 12))
        status = ttk.LabelFrame(left, padding=(14, 12))
        status.pack(fill="x")
        self._build_notebooklm_card(left)
        self._build_ai_card(left)
        status.columnconfigure(1, weight=1)
        self.state_icon = ttk.Label(status, font=("Segoe UI", 20), width=2, anchor="center")
        self.state_icon.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        self.scene = SyncScene(status, *COMPACT_SCENE, background=background)
        self.scene.canvas.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        self.state_title = ttk.Label(status, font=("Segoe UI Light", 20))
        self.state_title.grid(row=0, column=1, sticky="sw")
        self.state_detail = ttk.Label(status, foreground=MUTED, wraplength=320)
        self.state_detail.grid(row=1, column=1, sticky="nw")
        buttons = ttk.Frame(status)
        buttons.grid(row=0, column=2, rowspan=2, sticky="ne")
        # Drive's pills: gray for the card's own buttons, tinted for "View all".
        self.sync_button = PillButton(buttons, command=lambda: self.on_action("sync"))
        self.sync_button.pack(side="left")
        self.home_action = PillButton(buttons, command=lambda: self.on_action(self.status.home.action))
        self.home_action.pack(side="left", padx=(8, 0))
        # A note or the last error, the one thing the title and its line have no room for.
        self.account_message = ttk.Label(status, wraplength=420)
        self.account_message.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        # The last files: a click opens one, "⋮" offers to show it in its folder.
        self.recent_body = ttk.Frame(status)
        self.recent_body.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        self.recent_canvas, self.recent_frame = self._scroll_area(self.recent_body, 0)
        self.recent_canvas.configure(height=main.HOME_RECENT_ROWS * 52)
        footer = ttk.Frame(status)
        footer.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        footer.columnconfigure(1, weight=1)
        PillButton(footer, main.T_VIEW_ALL, lambda: self.select(main.ACTIVITY), accent=True).grid(
            row=0, column=0, sticky="w")
        self.recent_count = ttk.Label(footer, foreground=MUTED)
        self.recent_count.grid(row=0, column=1, sticky="e")

        # Right: what needs attention, then the next due dates.
        self.notify_frame = ttk.LabelFrame(page, text=main.T_HOME_ANNOUNCEMENTS, padding=(14, 8))
        self.notify_frame.grid(row=2, column=1, sticky="new", pady=(0, 12))
        self.calendar_frame = ttk.LabelFrame(page, text=main.T_HOME_CALENDAR, padding=(14, 8))
        self.calendar_frame.grid(row=3, column=1, sticky="new")

    def _build_notebooklm_card(self, parent):
        """Under the status card: the same card as the WebView2 page and macOS, in plain Tk."""
        from tkinter import ttk

        card = ttk.LabelFrame(parent, text=main.T_NOTEBOOKLM, padding=(14, 8))
        card.pack(fill="x", pady=(12, 0))
        card.columnconfigure(0, weight=1)
        self.notebooklm_detail = ttk.Label(card, foreground=MUTED, wraplength=NOTEBOOKLM_WRAP)
        self.notebooklm_detail.grid(row=0, column=0, sticky="w")
        self.notebooklm_secondary = ttk.Label(card, foreground=MUTED, wraplength=NOTEBOOKLM_WRAP)
        self.notebooklm_secondary.grid(row=1, column=0, sticky="w")
        self.notebooklm_warning_counts = ttk.Label(card, foreground=WARNING, wraplength=NOTEBOOKLM_WRAP)
        self.notebooklm_warning_counts.grid(row=2, column=0, sticky="w")
        self.notebooklm_notice = ttk.Label(card, foreground=WARNING, wraplength=NOTEBOOKLM_WRAP)
        self.notebooklm_notice.grid(row=3, column=0, sticky="w")
        self.notebooklm_bar = ttk.Progressbar(card, maximum=1.0)
        self.notebooklm_bar.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        buttons = ttk.Frame(card)
        buttons.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.notebooklm_button = PillButton(buttons, command=lambda: self.on_action(self.status.notebooklm.action))
        self.notebooklm_button.pack(side="left")
        self.notebooklm_open = PillButton(buttons, main.T_NOTEBOOKLM_OPEN, lambda: self.on_action("notebooklm_open"))
        self.notebooklm_open.pack(side="left", padx=(8, 0))

    def _draw_notebooklm_card(self):
        card = self.status.notebooklm
        for label, text in ((self.notebooklm_detail, card.detail), (self.notebooklm_secondary, card.secondary),
                            (self.notebooklm_warning_counts, card.warning_counts),
                            (self.notebooklm_notice, card.notice)):
            label.configure(text=text)
            if text:
                label.grid()
            else:
                label.grid_remove()
        self.notebooklm_detail.configure(foreground=WARNING if card.warning else MUTED)
        bar = self.notebooklm_bar
        if not card.running:
            bar.stop()
            bar.grid_remove()
        else:
            bar.grid()
            if card.progress is None:
                bar.configure(mode="indeterminate")
                bar.start(40)
            else:
                bar.stop()
                bar.configure(mode="determinate", value=card.progress)
        self.notebooklm_button.configure(text=card.action_title, state="normal" if card.enabled else "disabled")
        self.notebooklm_open.pack_forget()
        if card.open_action:
            self.notebooklm_open.pack(side="left", padx=(8, 0))

    def _build_ai_card(self, parent):
        """Under the NotebookLM card: the same AI study session card as macOS and WebView2, in plain Tk."""
        import tkinter as tk
        from tkinter import ttk

        card = ttk.LabelFrame(parent, text=main.T_AI_TITLE, padding=(14, 8))
        card.pack(fill="x", pady=(12, 0))
        card.columnconfigure(0, weight=1)
        self.ai_card_frame = card
        self.ai_detail = ttk.Label(card, foreground=MUTED, wraplength=NOTEBOOKLM_WRAP)
        self.ai_detail.grid(row=0, column=0, sticky="w")
        # A button per tool (shown while it is installed), in a frame whose border marks the one used last.
        self.ai_row = ttk.Frame(card)
        self.ai_row.grid(row=1, column=0, sticky="w", pady=(8, 0))
        background = background_of(card)
        dark = is_dark(background)
        self.ai_tools, self.ai_images = {}, []
        for key, tool in ai_launcher.TOOLS.items():
            border = tk.Frame(self.ai_row, highlightthickness=2, highlightbackground=background,
                              highlightcolor=background)
            image = _logo_image(border, key, dark)
            picture = {"image": image, "compound": "image"} if image is not None else {}
            button = ttk.Button(border, text=tool.name,
                                command=lambda k=key: self.on_action(main.AI_OPEN_PREFIX + k), **picture)
            button.pack()
            self.ai_images.append(image)  # Tk drops an image that nothing holds on to
            self.ai_tools[key] = (border, button, Tooltip(button), background)
        buttons = ttk.Frame(card)
        buttons.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.ai_button = PillButton(buttons, command=lambda: self.status.ai.action and self.on_action(self.status.ai.action))
        self.ai_button.pack(side="left")
        self.ai_secondary = PillButton(
            buttons, command=lambda: self.status.ai.secondary_action and self.on_action(self.status.ai.secondary_action))
        self.ai_secondary.pack(side="left", padx=(8, 0))

    def _draw_ai_card(self):
        card = self.status.ai
        self.ai_card_frame.configure(text=card.title)
        self.ai_detail.configure(text=card.detail, foreground=WARNING if card.warning else MUTED)
        state = "normal" if card.tools_enabled else "disabled"
        shown = {tool.key: tool for tool in card.tools}
        for border, *_ in self.ai_tools.values():
            border.pack_forget()
        for key, (border, button, tooltip, background) in self.ai_tools.items():
            tool = shown.get(key)
            if tool is None:
                continue
            tooltip.text = tool.label
            button.configure(state=state)
            color = AI_CURRENT_BORDER if tool.current else background
            border.configure(highlightbackground=color, highlightcolor=color)
            border.pack(side="left", padx=(0, 6))
        if shown:
            self.ai_row.grid()
        else:
            self.ai_row.grid_remove()
        self.ai_button.configure(text=card.action_title, state="normal" if card.enabled else "disabled")
        self.ai_button.pack_forget()
        self.ai_secondary.pack_forget()
        if card.action:
            self.ai_button.pack(side="left")
        if card.secondary_action:
            self.ai_secondary.configure(text=card.secondary_title,
                                        state="normal" if card.secondary_enabled else "disabled")
            self.ai_secondary.pack(side="left", padx=(8, 0))

    def _draw_home_cards(self):
        """Home's Announcements and Yaklaşan teslimler cards."""
        from datetime import datetime
        from tkinter import ttk

        rows = tuple(self.on_announcements()[:main.HOME_ANNOUNCEMENT_ROWS])
        colors = tuple(main.course_color_index(self.status.course_colors, row.course_code) for row in rows)
        key = ("announcements", rows, colors)
        if key != self._drawn_home_notifications:
            self._drawn_home_notifications = key
            for child in self.notify_frame.winfo_children():
                child.destroy()
            if not rows:
                ttk.Label(self.notify_frame, text=announcements.T_EMPTY, foreground=MUTED, wraplength=240).pack(
                    anchor="w")
            for row, color in zip(rows, colors):
                ttk.Button(self.notify_frame, text=row.title, style="Toolbutton",
                           command=lambda item=row: self.on_open_announcement(item)).pack(anchor="w")
                self._course_detail(self.notify_frame, row.detail, row.course_code, row.date, color, wrap=240,
                                    course_title=main.course_name_without_code(row.course, row.course_code)).pack(
                    anchor="w", padx=(4, 0), pady=(0, 6))
            if rows:
                PillButton(self.notify_frame, main.T_VIEW_ALL, lambda: self.select(main.ANNOUNCEMENTS),
                           accent=True).pack(anchor="w", pady=(6, 0))
        page = self.on_deadlines()
        today = datetime.now().astimezone().date()
        rows = deadlines.upcoming_rows(page, main.HOME_DEADLINE_ROWS)
        colors = tuple(main.course_color_index(self.status.course_colors, row.course_code) for row in rows)
        key = ("calendar", rows, today, colors)
        if key != self._drawn_home_calendar:
            self._drawn_home_calendar = key
            for child in self.calendar_frame.winfo_children():
                child.destroy()
            if not rows:
                ttk.Label(self.calendar_frame, text=page.message or main.T_NO_DEADLINES, foreground=MUTED,
                          wraplength=240).pack(anchor="w")
            for row, color in zip(rows, colors):
                ttk.Button(self.calendar_frame, text=row.title, style="Toolbutton",
                           command=lambda target=row.target: self.on_deadline(target)).pack(anchor="w")
                when = deadlines.when_text(row, today)
                self._course_detail(self.calendar_frame, f"{when} · {row.course}", row.course_code,
                                    when, color, wrap=240,
                                    course_title=main.course_name_without_code(row.course, row.course_code)).pack(
                    anchor="w", padx=(4, 0), pady=(0, 6))
            PillButton(self.calendar_frame, main.T_OPEN_CALENDAR, lambda: self.select(main.CALENDAR),
                       accent=True).pack(anchor="w", pady=(6, 0))

    def _course_detail(self, parent, detail, code, when, color, wrap=0, course_title=""):
        import tkinter as tk
        from tkinter import ttk

        if not code or color is None:
            return ttk.Label(parent, text=detail, style="Muted.TLabel", wraplength=wrap)
        row = ttk.Frame(parent)
        background = background_of(row, "TFrame")
        fill, ink = course_badge_colors(color, light=not is_dark(background))
        badge = tk.Canvas(row, background=background, highlightthickness=0, borderwidth=0)
        text = badge.create_text(6, 2, text=code, fill=ink, anchor="nw", font=("Segoe UI Semibold", 11))
        left, top, right, bottom = badge.bbox(text) or (0, 0, len(code) * 8, 15)
        width, height = right - left + 12, bottom - top + 4
        badge.configure(width=width, height=height)
        shape = badge.create_polygon(rounded(0, 0, width, height, 6), smooth=True, fill=fill)
        badge.tag_lower(shape, text)
        badge.pack(side="left")
        trailing = _badge_trailing_text(course_title, when, max(0, wrap - width - 6) if wrap else 0)
        if trailing:
            label_kwargs = {"wraplength": max(1, wrap - width - 6)} if (wrap and not course_title) else {}
            ttk.Label(row, text=trailing, style="Muted.TLabel", **label_kwargs).pack(side="left", padx=(6, 0))
        return row

    def _build_activity(self, page):
        from tkinter import ttk

        self._header(page, main.T_NAV_ACTIVITY)
        card = ttk.LabelFrame(page, padding=(14, 12))
        card.grid(row=1, column=0, sticky="nsew")
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        card.rowconfigure(3, weight=1)
        # Drive's header: the state in words over the table.
        self.activity_icon = ttk.Label(card, font=("Segoe UI", 20), width=2, anchor="center")
        self.activity_icon.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        self.activity_title = ttk.Label(card, font=("Segoe UI Light", 20))
        self.activity_title.grid(row=0, column=1, sticky="sw")
        self.activity_detail = ttk.Label(card, foreground=MUTED)
        self.activity_detail.grid(row=1, column=1, sticky="nw")
        head = ttk.Frame(card)
        head.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 4))
        head.columnconfigure(0, weight=1)
        for column, (title, width) in enumerate(((main.T_NAME, None), (main.T_SIZE, 10), (main.T_STATUS, 6))):
            ttk.Label(head, text=title, foreground=MUTED, font=BOLD_FONT, width=width or 1).grid(
                row=0, column=column, sticky="w" if column == 0 else "e", padx=(8, 0))
        ttk.Label(head, text="", width=3).grid(row=0, column=3)
        body = ttk.Frame(card)
        body.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.activity_canvas, self.activity_frame = self._scroll_area(body, 0)
        self.activity_frame.columnconfigure(0, weight=1)

    def refresh_activity(self):
        from tkinter import ttk

        rows = self.status.activity
        if rows == self._drawn_activity:
            return
        self._drawn_activity = rows
        for child in self.activity_frame.winfo_children():
            child.destroy()
        if not rows:
            ttk.Label(self.activity_frame, text=main.T_ACTIVITY_EMPTY, foreground=MUTED).pack(anchor="w", pady=8)
        for row in rows:
            self._file_row(self.activity_frame, row.name, row.kind, row.status, row.size, row.path, activity=row)

    def _build_announcements(self, page):
        from tkinter import ttk

        self._header(page, announcements.T_TAB)
        ttk.Label(page, text=announcements.T_HINT, foreground=MUTED, wraplength=WRAP).grid(
            row=1, column=0, sticky="w", pady=(0, 14))
        self.announcements_canvas, self.announcements_frame = self._scroll_area(page, 2)

    def _build_general(self, page):
        """Settings: sections (a small title over a card of rows) on one scrolling page."""
        from tkinter import ttk

        self._header(page, main.T_NAV_GENERAL)
        self.form_canvas, frame = self._scroll_area(page, 1)
        frame.configure(padding=(0, 0, 16, 8))
        frame.columnconfigure(0, weight=1)
        self.fields = {}
        self.settings_rows = {}
        self.update_button = self.uninstall_button = None
        packaged = package.is_packaged()
        row = 0
        for section in form.settings_sections(notebooklm=True, auto_relogin=True):
            if section.key == form.SECTION_CALENDAR:
                continue  # Connection controls currently macOS/CLI only.
            if packaged and section.danger:
                continue  # the Store removes the app; the Updates card says so
            row = self._build_section(frame, section, row, packaged)

        # Only while something is not saved (or saving failed): the reason, Vazgeç and Kaydet.
        self.button_bar = bar = ttk.Frame(page, padding=(0, 10, 0, 0))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.error_label = ttk.Label(bar, wraplength=WRAP - 200)
        self.error_label.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text=form.T_CANCEL, command=self.discard).grid(row=0, column=1, padx=4)
        ttk.Button(bar, text=form.T_SAVE, command=lambda: self.submit(False)).grid(row=0, column=2, padx=(4, 0))
        self.window.bind("<Escape>", lambda _e: self.discard() if self.bar_visible() else None)

    def _build_section(self, frame, section, row, packaged):
        """A section's title, its card of rows and its note; returns the next free grid row."""
        from tkinter import ttk

        title = ttk.Label(frame, text=section.title, font=HEADING_FONT,
                          foreground=WARNING if section.danger else "")
        title.grid(row=row, column=0, sticky="w", pady=(0 if row == 0 else 16, 4))
        outer, card = self._card(frame, section.danger)
        outer.grid(row=row + 1, column=0, sticky="ew")
        definitions = [r for r in section.rows if not (packaged and r.key in PACKAGED_HIDDEN_ROWS)]
        notes = ()
        if packaged and section.key == form.SECTION_UPDATES:
            notes = (updater.STORE_UPDATES, uninstall.STORE_REMOVAL)
        for index, definition in enumerate(definitions):
            if index:
                ttk.Separator(card, orient="horizontal").grid(row=2 * index - 1, column=0, sticky="ew")
            self._settings_row(card, 2 * index, definition, packaged, section.danger)
        for offset, note in enumerate(notes, start=len(definitions)):
            ttk.Separator(card, orient="horizontal").grid(row=2 * offset - 1, column=0, sticky="ew")
            ttk.Label(card, text=note, wraplength=WRAP, padding=(0, 10)).grid(row=2 * offset, column=0, sticky="w")
        row += 2
        if section.footer:
            ttk.Label(frame, text=section.footer, foreground=MUTED, wraplength=WRAP).grid(
                row=row, column=0, sticky="w", pady=(4, 0))
            row += 1
        return row

    def _card(self, frame, danger):
        """(what is placed on the page, where the rows go): a bordered frame, red for the Danger zone."""
        import tkinter as tk
        from tkinter import ttk

        if danger:
            outer = tk.Frame(frame, highlightthickness=1, highlightbackground=DANGER_BORDER,
                             background=background_of(frame))
            inner = ttk.Frame(outer, padding=(14, 0))
            inner.pack(fill="both", expand=True)
        else:
            outer = inner = ttk.LabelFrame(frame, padding=(14, 0))
        inner.columnconfigure(0, weight=1)
        return outer, inner

    def _settings_row(self, card, grid_row, definition, packaged, danger):
        """One row: title and description on the left, the control (and a second one) on the right."""
        from tkinter import ttk

        key = definition.key
        frame = ttk.Frame(card, padding=(0, 10))
        frame.grid(row=grid_row, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        text = ttk.Frame(frame)
        text.grid(row=0, column=0, sticky="ew")
        text.columnconfigure(0, weight=1)
        title = ttk.Label(text, text=definition.title, wraplength=ROW_WRAP)
        title.grid(row=0, column=0, sticky="w")
        detail = None
        if definition.detail:
            detail = ttk.Label(text, text=definition.detail, foreground=MUTED, wraplength=ROW_WRAP)
            detail.grid(row=1, column=0, sticky="w")

        def rewrap(event):  # a narrow window gives the text less room: it wraps there instead of being cut off
            for label in (title, detail):
                if label is not None:
                    label.configure(wraplength=max(ROW_MIN_WRAP, event.width))

        text.bind("<Configure>", rewrap)
        control = None if (packaged and key == "update") else self._row_control(frame, definition, danger)
        if control is not None:
            control.grid(row=0, column=2, sticky="e", padx=(16, 0))
        if definition.control == form.CONTROL_FIELD:
            self.fields[key] = control
            if definition.button:
                ttk.Button(frame, text=definition.button, command=self.choose_folder).grid(
                    row=0, column=3, padx=(8, 0))
        self.settings_rows[key] = SettingsRowViews(title, detail, control)
        for attribute, widget in zip(ROW_ATTRIBUTES.get(key, ()), (control, title, detail)):
            if attribute:
                setattr(self, attribute, widget)

    def _row_control(self, frame, definition, danger):
        """The row's own control, not yet placed."""
        from tkinter import ttk

        key, kind = definition.key, definition.control
        variables = {"base_url": self.url, "dest": self.dest, "autostart": self.autostart,
                     "check_updates": self.check_updates, "interval": self.interval, "language": self.language,
                     "auto_relogin": self.auto_relogin,
                     "notebooklm_auto": self.notebooklm_auto, "ai_terminal": self.ai_terminal,
                     "ai_resume": self.ai_resume}
        if kind == form.CONTROL_FIELD:
            if key == "base_url":  # typing a school's name lists the matching schools
                box = ttk.Combobox(frame, textvariable=variables[key], width=34, values=schools.suggestions())
                self.school_searches.append(SchoolSearch(self.window, box, variables[key]))
                return box
            return ttk.Entry(frame, textvariable=variables[key], width=26 if definition.button else 34)
        if kind == form.CONTROL_POPUP:
            choices = {"interval": [title for _, title in form.INTERVAL_OPTIONS],
                       "language": [name for _, name in form.LANGUAGE_OPTIONS]}.get(key, [])
            return ttk.Combobox(frame, textvariable=variables[key], width=24, values=choices,
                                state="readonly" if choices else "disabled")
        if kind == form.CONTROL_SWITCH:
            return ttk.Checkbutton(frame, variable=variables[key])
        commands = {"account": self.account_pressed,
                    "update": lambda: self.on_action(self.status.form.update_action),
                    "uninstall": lambda: self.on_action("uninstall"),
                    "notebooklm_disconnect": lambda: self.on_action("notebooklm_disconnect")}
        style = self._danger_button_style() if danger else None
        options = {"style": style} if style else {}
        return ttk.Button(frame, text=definition.button, width=ACTION_WIDTH, command=commands[key], **options)

    def _danger_button_style(self):
        """A ttk style with red text for Uninstall; None where styles cannot be made (the default look)."""
        try:
            from tkinter import ttk

            ttk.Style(self.window).configure("Danger.TButton", foreground=WARNING)
            return "Danger.TButton"
        except Exception:
            return None

    def _apply_row_state(self, key, state):
        """Show what changes while the app runs: texts, the button title, enabled and the warning color."""
        row = self.settings_rows.get(key)
        if row is None:
            return
        if state.title is not None:
            row.title.configure(text=state.title)
        row.title.configure(foreground=WARNING if state.warning else "")
        if state.detail is not None and row.detail is not None:
            row.detail.configure(text=state.detail)
        if row.control is None:
            return
        if state.button is not None:
            row.control.configure(text=state.button)
        enabled_state = "readonly" if key in ("interval", "language", "ai_terminal") else "normal"
        row.control.configure(state=enabled_state if state.enabled else "disabled")

    def _build_courses(self, page):
        from tkinter import ttk

        self._header(page, main.T_NAV_COURSES)
        ttk.Label(page, text=courses.T_HINT, wraplength=WRAP).grid(row=1, column=0, columnspan=2, sticky="w",
                                                                  pady=(0, 6))
        ttk.Label(page, text=courses.T_UNTICK_HINT, foreground=MUTED, wraplength=WRAP).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.courses_canvas, self.courses_frame = self._scroll_area(page, 3)
        self.courses_canvas.configure(background=background_of(page))

    def fit(self):
        """The fixed size, but never taller than the work area; centred in it."""
        window = self.window
        window.update_idletasks()
        left, top, width, height = work_area(window)
        total = form.window_height(HEIGHT, CHROME, height)
        inner_width = min(WIDTH, max(MIN_WIDTH, width - 40))
        x = left + max(0, (width - inner_width) // 2)
        y = top + max(0, (height - total) // 2)
        window.geometry(f"{inner_width}x{total - CHROME}+{x}+{y}")
        window.resizable(False, False)

    def wheel(self, event):
        if self.visible_page() == main.OVERVIEW and self.status.update_required is not None:
            return
        canvas = {"start": self.start_canvas, main.OVERVIEW: self.overview_canvas,
                  main.ACTIVITY: self.activity_canvas,
                  main.CALENDAR: self.calendar_canvas,
                  main.ANNOUNCEMENTS: self.announcements_canvas,
                  main.GENERAL: self.form_canvas, main.COURSES: self.courses_canvas}[self.visible_page()]
        steps = wheel_steps(event.delta)
        # Over Home's file list the list scrolls first, then the page.
        if canvas is self.overview_canvas and str(getattr(event, "widget", "")).startswith(f"{self.recent_canvas}."):
            first, last = self.recent_canvas.yview()
            if (last < 1) if steps > 0 else (first > 0):
                canvas = self.recent_canvas
        first, last = canvas.yview()
        if first > 0 or last < 1:  # a section that fits stays put
            canvas.yview_scroll(steps, "units")

    # -- behaviour ------------------------------------------------------------
    def show(self, section=None):
        """Open the window (or bring it forward) on ``section``; see ``WindowState.show``."""
        opening = not self.state.open
        self.state.show(section)
        self._show_section()
        self.refresh_courses()
        self._animate()
        window = self.window
        if opening:
            self.fit()
        window.deiconify()
        window.lift()
        # Windows keeps a new window behind the active one (the installer,
        # Explorer); topmost for a moment brings it in front of them.
        window.attributes("-topmost", True)
        window.after(1000, self.release_topmost)
        window.focus_force()
        if self.recent_seen is not None and self._recent_after is None:
            self._recent_after = window.after(250, self._recent_tick)

    def release_topmost(self):
        try:
            self.window.attributes("-topmost", False)
        except Exception:  # closed meanwhile
            pass

    def select(self, section):
        self.state.select(section)
        self._show_section()
        self._animate()
        self.on_section(section)

    def visible_page(self):
        section = self.state.section
        if section == main.OVERVIEW and self.status.update_required is not None:
            return main.OVERVIEW
        return "start" if section == main.OVERVIEW and self.status.first_run else section

    def _show_section(self):
        self._hide_school_lists()
        visible = self.visible_page()
        if self.recent_seen is not None:
            if self.state.open and visible == main.OVERVIEW and self.status.update_required is None:
                self.recent_seen.show()
            else:
                self.recent_seen.hide()
        for name, page in self.pages.items():
            if name == visible:
                page.grid()
            else:
                page.grid_remove()
        self.section_var.set(self.state.section)
        if self.state.section == main.COURSES:
            self.refresh_courses()
        elif self.state.section == main.ACTIVITY:
            self.refresh_activity()
        elif self.state.section == main.CALENDAR:
            self.refresh_calendar()
        elif self.state.section == main.ANNOUNCEMENTS:
            self.refresh_announcements()

    def values(self):
        minutes = next((m for m, title in form.INTERVAL_OPTIONS if title == self.interval.get()), 60)
        if not self._terminal_choices or self.ai_terminal.get() == self._terminal_initial_title:
            ai_terminal = self.saved.ai_terminal
        else:
            picked = next((k for k, name in self._terminal_choices if name == self.ai_terminal.get()),
                          self.saved.ai_terminal)
            detected = self.status.form.ai_terminals
            if self.saved.ai_terminal == "" and detected and picked == ai_launcher.system_terminal(detected):
                ai_terminal = ""
            else:
                ai_terminal = picked
        return form.FormValues(self.url.get(), self.dest.get(), self.autostart.get(),
                               self.check_updates.get(), minutes, form.language_code(self.language.get()),
                               self.auto_relogin.get(), self.notebooklm_auto.get(), ai_terminal, self.ai_resume.get())

    def _hide_school_lists(self):
        for search in self.school_searches:
            search.hide()

    def set_values(self, values):
        """Show ``values`` as what is saved: the bar goes away."""
        self._hide_school_lists()
        self.saved = values
        self._loading = True
        try:
            self.url.set(values.base_url)
            self.dest.set(values.dest)
            self.autostart.set(values.autostart)
            self.check_updates.set(values.check_updates)
            self.auto_relogin.set(values.auto_relogin)
            self.notebooklm_auto.set(values.notebooklm_auto)
            self.ai_resume.set(values.ai_resume)
            self.interval.set(form.interval_title(values.sync_interval_minutes))
            self.language.set(form.language_title(values.language))
            self._set_terminal_from_values(values)
        finally:
            self._loading = False
        self.show_error("")

    def _set_terminal_from_values(self, values):
        detected = self.status.form.ai_terminals
        if self._terminal_choices and detected:
            used = ai_launcher.resolve_terminal(values.ai_terminal, detected)
            title = dict(self._terminal_choices)[used]
        else:
            title = ""
        self._terminal_initial_title = title
        self.ai_terminal.set(title)

    def _refresh_terminal_dropdown(self, form_status):
        choices = form.ai_terminal_choices(form_status.ai_terminals, self.saved.ai_terminal)
        current_title = self.ai_terminal.get()
        dirty = bool(self._terminal_choices) and current_title != self._terminal_initial_title
        if choices != self._terminal_choices:
            self._terminal_choices = choices
            self.ai_terminal_dropdown.configure(values=[name for _, name in choices])
        if not choices:
            self._terminal_initial_title = ""
            loading, self._loading = self._loading, True
            try:
                self.ai_terminal.set("")
            finally:
                self._loading = loading
            return
        names = dict(choices)
        used = ai_launcher.resolve_terminal(self.saved.ai_terminal, form_status.ai_terminals)
        expected = names[used]
        self._terminal_initial_title = expected
        if not dirty or current_title not in names.values():
            loading, self._loading = self._loading, True
            try:
                self.ai_terminal.set(expected)
            finally:
                self._loading = loading

    def changed(self):
        if self._loading:
            return
        self.error = ""
        self._layout_bar()

    def bar_visible(self):
        return main.has_changes(self.saved, self.values()) or bool(self.error)

    def _layout_bar(self):
        if self.bar_visible():
            self.button_bar.grid()
        else:
            self.button_bar.grid_remove()
        self.error_label.configure(text=self.error or main.T_UNSAVED,
                                   foreground=WARNING if self.error else MUTED)

    def show_error(self, message):
        self.error = message
        self._layout_bar()
        self._draw_start_message()

    def _draw_start_message(self):
        self.start_message.configure(text=self.error or self.status.start_message,
                                     foreground=WARNING if self.error else MUTED)

    def discard(self):
        """Vazgeç: back to what is saved."""
        self.set_values(self.on_values())

    def update_status(self, status):
        first_run_changed = (
            status.first_run != self.status.first_run
            or (status.update_required is None) != (self.status.update_required is None)
        )
        self.status = status
        self.nav[main.OVERVIEW].configure(text=status.overview_title)
        self.nav[main.ACTIVITY].configure(text=main.T_NAV_ACTIVITY)
        self.nav[main.ANNOUNCEMENTS].configure(text=announcements.T_TAB)
        self.nav[main.CALENDAR].configure(text=deadlines.T_TAB)
        self.nav[main.COURSES].configure(text=self.courses_nav_title(self._drawn_courses or ()))
        if first_run_changed:
            self._show_section()
        # Store builds never offer the GitHub updater, even with stale state.
        banner = status.update_banner if updater.enabled() else None
        for box, title, button in (self.start_update_banner, self.overview_update_banner):
            if banner is None:
                box.grid_remove()
            else:
                title.configure(text=banner.title)
                button.configure(text=banner.button_title, state="normal" if banner.enabled else "disabled")
                box.grid()
        self._draw_license_banner(self.overview_license_banner, status.license)
        self._draw_license_banner(
            self.start_license_banner,
            status.license if status.license and status.license.kind == main.LICENSE_EXPIRED else None,
        )
        if status.update_required is not None:
            req = status.update_required
            self.overview_holder.grid_remove()
            self.update_required_title.configure(text=req.title)
            self.update_required_detail.configure(text=req.detail)
            self.update_required_notice.configure(text=req.notice)
            if req.notice:
                self.update_required_notice.grid()
            else:
                self.update_required_notice.grid_remove()
            self.update_required_button.configure(
                text=req.button_title, state="normal" if req.enabled else "disabled"
            )
            self.update_required_frame.grid()
        else:
            self.update_required_frame.grid_remove()
            self.overview_holder.grid()
        # Başlangıç
        self.start_button.configure(text=status.start_title, state="normal" if status.start_enabled else "disabled")
        self._draw_start_message()
        # Home
        card = status.account
        self.overview_title.configure(text=status.home_heading or status.overview_title)
        self.overview_subtitle.configure(text=status.home_subtitle)
        if status.home_subtitle:
            self.overview_subtitle.grid()
        else:
            self.overview_subtitle.grid_remove()
        self.sync_button.configure(text=status.sync_title, state="normal" if status.sync_enabled else "disabled")
        home = status.home
        symbol, color = HOME_SYMBOLS.get(home.kind, HOME_SYMBOLS[main.STATE_SYNCED])
        for icon, title, detail in ((self.state_icon, self.state_title, self.state_detail),
                                    (self.activity_icon, self.activity_title, self.activity_detail)):
            title.configure(text=home.title)
            detail.configure(text=home.detail)
            icon.configure(text=symbol, foreground=color)
        if status.scene:
            self.state_icon.grid_remove()
            self.scene.canvas.grid()
        else:
            self.scene.canvas.grid_remove()
            self.state_icon.grid()
        # At most one button: what the state asks for (Sign in), else "Sync now". Paused has none:
        # the top bar's play button resumes, as in Drive.
        self.home_action.pack_forget()
        self.sync_button.pack_forget()
        if home.action:
            self.home_action.configure(text=home.action_title)
            self.home_action.pack(side="left")
        elif home.shows_sync:
            self.sync_button.pack(side="left")
        self.account_message.configure(text=card.message, foreground=WARNING if card.warning else MUTED)
        if card.message:
            self.account_message.grid()
        else:
            self.account_message.grid_remove()
        self._animate()
        self._draw_recent()
        self._draw_notebooklm_card()
        self._draw_ai_card()
        self._draw_home_cards()
        self.refresh_calendar()
        self.refresh_activity()
        self.refresh_announcements()
        if self.state.section == main.COURSES:
            self.refresh_courses()  # a sync may have found another course
        # The buttons at the top right: Duraklat / Devam et, Ayarlar and the account.
        if status.shows_account:
            self.topbar.place(relx=1.0, x=-24, y=14, anchor="ne")
            self.topbar.lift()
        else:
            self.topbar.place_forget()
        self.pause_button.configure(text="▶" if status.paused else "⏸",
                                    state="normal" if status.pause_enabled else "disabled")
        self.avatar.delete("all")
        self.avatar.create_oval(1, 1, AVATAR - 1, AVATAR - 1, outline="",
                                fill=AVATAR_WARNING_FILL if card.warning else AVATAR_FILL)
        self.avatar.create_text(AVATAR / 2, AVATAR / 2, text=card.initials, font=BOLD_FONT,
                                fill=WARNING if card.warning else AVATAR_TEXT)
        # Genel
        form_status = status.form
        self._refresh_terminal_dropdown(form_status)
        for key, state in form.row_states(form_status).items():
            if key.startswith("google_calendar"):
                continue
            self._apply_row_state(key, state)
        self._apply_row_state("notebooklm_disconnect", form.notebooklm_disconnect_state(form_status))
        self._animate()
        self.refresh_announcements()

    def _build_calendar(self, page):
        from tkinter import ttk

        self._header(page, deadlines.T_TAB)
        ttk.Label(page, text=deadlines.T_HINT, wraplength=WRAP).grid(row=1, column=0, sticky="w", pady=(0, 16))
        self.calendar_canvas, self.calendar_body = self._scroll_area(page, 2)
        self.calendar_canvas.configure(background=background_of(page))

    def refresh_calendar(self):
        from tkinter import ttk

        data = self.on_deadlines()
        colors = tuple(
            tuple(main.course_color_index(self.status.course_colors, row.course_code) for row in day.rows)
            for day in data.days
        )
        if (data, colors) == self._drawn_deadlines:
            return
        self._drawn_deadlines = (data, colors)
        for child in self.calendar_body.winfo_children():
            child.destroy()
        if data.message:
            ttk.Label(self.calendar_body, text=data.message, wraplength=WRAP).pack(anchor="w", pady=(0, 12))
        if not data.days:
            ttk.Label(self.calendar_body, text=deadlines.T_EMPTY).pack(anchor="w", pady=12)
        section = None
        for day, day_colors in zip(data.days, colors):
            if day.past != section:
                section = day.past
                ttk.Label(self.calendar_body, text=deadlines.T_PAST if day.past else deadlines.T_UPCOMING,
                          font=HEADING_FONT).pack(anchor="w", pady=(8, 12))
                if day.past:
                    ttk.Label(self.calendar_body, text=deadlines.T_PAST_HINT, wraplength=WRAP).pack(
                        anchor="w", pady=(0, 12))
            card = ttk.LabelFrame(self.calendar_body, text=day.title, padding=(16, 10))
            card.pack(fill="x", pady=(0, 14))
            card.columnconfigure(1, weight=1)
            for index, (row, color) in enumerate(zip(day.rows, day_colors)):
                ttk.Label(card, text=row.time, font=BOLD_FONT, width=7).grid(
                    row=index * 2, column=0, rowspan=2, sticky="nw", padx=(0, 12), pady=(4, 12))
                ttk.Button(card, text=row.title, command=lambda target=row.target: self.on_deadline(target)).grid(
                    row=index * 2, column=1, sticky="ew", pady=(2, 0))
                self._course_detail(card, row.course, row.course_code, "", color, wrap=WRAP - 80,
                                    course_title=main.course_name_without_code(row.course, row.course_code)).grid(
                    row=index * 2 + 1, column=1, sticky="w", pady=(2, 12))

    def _animate(self):
        """Run an illustration while it is in view and the window is open; stop it otherwise."""
        if (self.status.scene and self.state.open and self.state.section == main.OVERVIEW
                and self.status.update_required is None):
            self.scene.start()
        else:
            self.scene.stop()

    def _draw_recent(self):
        rows = self.status.recent
        self.recent_count.configure(text=main.recent_count(rows))
        if rows == self._drawn_recent:
            return
        self._drawn_recent = rows
        self._recent_entries = []
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        from tkinter import ttk

        if not rows:
            ttk.Label(self.recent_frame, text=T_RECENT_EMPTY, foreground=MUTED).pack(anchor="w", pady=8)
        for row in rows[:main.HOME_RECENT_ROWS]:
            entry = self._file_row(self.recent_frame, row.name, row.kind, row.detail, None, row.path, recent=row)
            self._recent_entries.append((entry, row))

    def _file_row(self, parent, name, kind, detail, size, path, recent=None, activity=None):
        """Drive's file row: kind, name with a line under it, (size), ✓ (or YENİ) and "⋮"."""
        import tkinter as tk
        from tkinter import ttk

        entry = ttk.Frame(parent, padding=(0, 6))
        entry.pack(anchor="w", fill="x")
        entry.columnconfigure(1, weight=1)
        ttk.Label(entry, text=kind or "•", width=5, anchor="center", font=BOLD_FONT,
                  foreground=MUTED).grid(row=0, column=0, rowspan=2, padx=(0, 10))
        # A click opens the file in its own application.
        ttk.Button(entry, text=name, style="Toolbutton", command=lambda: self.on_open(path)).grid(
            row=0, column=1, sticky="w")
        if recent:
            metadata = self._course_detail(entry, detail, recent.course_code, recent.when, recent.color)
        elif activity is not None:
            metadata = self._course_detail(entry, detail, activity.course_code, activity.status, activity.color,
                                           wrap=WRAP - 120, course_title=activity.course_title)
        else:
            metadata = ttk.Label(entry, text=detail, foreground=MUTED)
        metadata.grid(row=1, column=1, sticky="w", padx=(4, 0))
        column = 2
        if size is not None:
            ttk.Label(entry, text=size, foreground=MUTED, width=10, anchor="e").grid(
                row=0, column=column, rowspan=2, padx=(8, 0))
            column += 1
        if recent and recent.is_new:
            pill = tk.Canvas(entry, width=52, height=22, highlightthickness=0,
                             background=background_of(entry))
            pill.grid(row=0, column=column, rowspan=2, padx=(8, 0))
            pill.create_oval(0, 0, 22, 22, fill="#2563eb", outline="")
            pill.create_oval(30, 0, 52, 22, fill="#2563eb", outline="")
            pill.create_rectangle(11, 0, 41, 22, fill="#2563eb", outline="")
            pill.create_text(26, 11, text=main.T_NEW, fill="#ffffff", font=("Segoe UI", 9, "bold"))
        else:
            ttk.Label(entry, text="✓", foreground="#236b45", font=BOLD_FONT, width=4, anchor="center").grid(
                row=0, column=column, rowspan=2, padx=(8, 0))
        more = ttk.Button(entry, text="⋮", width=2, style="Toolbutton")
        more.configure(command=lambda: self.show_file_menu(more, path))
        more.grid(row=0, column=column + 1, rowspan=2, padx=(4, 0))
        return entry

    def show_file_menu(self, widget, path):
        """The "⋮" of a file row: open it, or show it in its folder."""
        import tkinter as tk

        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label=main.T_OPEN_FILE, command=lambda: self.on_open(path))
        menu.add_command(label=main.T_SHOW_IN_FOLDER, command=lambda: self.on_reveal(path))
        try:
            menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _recent_unmapped(self, event):
        if event.widget == self.window:
            self.recent_seen.hide()

    def _recent_mapped(self, event):
        if event.widget == self.window:
            self._show_section()
            self.on_section(self.state.section)

    def _recent_focus_out(self, _event):
        focus = self.window.focus_displayof()
        if focus is None or focus.winfo_toplevel() != self.window:
            self.recent_seen.reset_exposure()

    def observe_recent(self):
        focus = self.window.focus_displayof()
        active = (self.state.open and self.visible_page() == main.OVERVIEW
                  and self.status.update_required is None
                  and self.window.state() == "normal" and focus is not None
                  and focus.winfo_toplevel() == self.window)
        visible = []
        if active and self.recent_canvas.winfo_viewable():
            top = max(self.recent_canvas.winfo_rooty(), self.window.winfo_rooty())
            bottom = min(self.recent_canvas.winfo_rooty() + self.recent_canvas.winfo_height(),
                         self.window.winfo_rooty() + self.window.winfo_height())
            visible = [(row.path, row.at) for entry, row in self._recent_entries
                       if entry.winfo_rooty() < bottom and entry.winfo_rooty() + entry.winfo_height() > top]
        if self.recent_seen.observe(visible, active):
            self.on_seen()

    def _recent_tick(self):
        self._recent_after = None
        if self.state.open:
            self.observe_recent()
            self._recent_after = self.window.after(250, self._recent_tick)

    def _stop_recent_tracking(self):
        if self._recent_after is not None:
            self.window.after_cancel(self._recent_after)
            self._recent_after = None
        if self.recent_seen is not None:
            self.recent_seen.hide()
    def refresh_announcements(self):
        from tkinter import ttk

        rows = self.on_announcements()
        colors = tuple(main.course_color_index(self.status.course_colors, row.course_code) for row in rows)
        if (rows, colors) == self._drawn_announcements:
            return
        self._drawn_announcements = (rows, colors)
        for widget in self.announcements_frame.winfo_children():
            widget.destroy()
        if not rows:
            ttk.Label(self.announcements_frame, text=announcements.T_EMPTY,
                      foreground=MUTED, wraplength=WRAP).pack(anchor="w", pady=12)
        for row, color in zip(rows, colors):
            card = ttk.LabelFrame(self.announcements_frame, padding=14)
            card.pack(fill="x", pady=(0, 10))
            detail = self._course_detail(card, row.detail, row.course_code, row.date, color, wrap=WRAP - 60,
                                         course_title=main.course_name_without_code(row.course, row.course_code))
            detail.pack(anchor="w")
            title = ttk.Label(card, text=row.title, font=BOLD_FONT, wraplength=WRAP - 60)
            title.pack(anchor="w", pady=4)
            clickable = [card, detail, *detail.winfo_children(), title]
            if row.preview:
                preview = ttk.Label(card, text=row.preview, wraplength=WRAP - 60)
                preview.pack(anchor="w")
                clickable.append(preview)
            for widget in clickable:
                widget.bind("<Button-1>", lambda _event, item=row: self.on_open_announcement(item))
            ttk.Button(card, text=announcements.T_OPEN,
                       command=lambda item=row: self.on_open_announcement(item)).pack(anchor="e", pady=(8, 0))

    def refresh_courses(self):
        """Draw Dersler again when the course list or a choice changed."""
        from tkinter import ttk, BooleanVar

        rows = self.on_courses()
        self.nav[main.COURSES].configure(text=self.courses_nav_title(rows))
        if rows == self._drawn_courses:
            return
        self._drawn_courses = rows
        for widget in self.courses_frame.winfo_children():
            widget.destroy()
        if not rows:
            ttk.Label(self.courses_frame, text=courses.T_EMPTY).pack(anchor="w", pady=12)
        for row in rows:
            variable = BooleanVar(value=row.enabled)
            entry = ttk.Frame(self.courses_frame, padding=(0, 4))
            entry.pack(anchor="w", fill="x")
            ttk.Checkbutton(entry, variable=variable,
                            command=lambda c=row.id, v=variable: self.toggle_course(c, v.get())).pack(
                side="left", anchor="n")
            text = ttk.Frame(entry)
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=main.course_title(row), font=BOLD_FONT if row.enabled else None,
                      foreground="" if row.enabled else MUTED, wraplength=WRAP - 60).pack(anchor="w")
            ttk.Label(text, text=main.course_detail(row), foreground=MUTED, wraplength=WRAP - 60).pack(anchor="w")
        note = courses.termless_hint(rows)
        if note:
            ttk.Label(self.courses_frame, text=note, foreground=MUTED, wraplength=WRAP - 60).pack(
                anchor="w", pady=(8, 0))

    @staticmethod
    def courses_nav_title(rows):
        return main.T_NAV_COURSES

    def toggle_course(self, course_id, enabled):
        self.on_course_toggle(course_id, enabled)
        self.refresh_courses()

    def account_pressed(self):
        if self.status.form.account_action == "login":
            self.submit(True)  # sign in with the address in the field
        else:
            self.on_action(self.status.form.account_action)

    def choose_folder(self):
        from tkinter import filedialog

        folder = filedialog.askdirectory(parent=self.window, title=form.T_CHOOSE_FOLDER_MESSAGE)
        if folder:
            self.dest.set(folder)

    def submit(self, login):
        """Save the form (Kaydet, or before signing in); the window stays open either way."""
        error = self.on_submit(self.values(), login)
        if error is None:
            self.set_values(self.on_values())
            return
        message, field = error
        self.show_error(message)
        fields = self.start_fields if self.visible_page() == "start" else self.fields
        fields.get(field, fields["base_url"]).focus_set()

    def close(self):
        """Hide the window: unsaved edits are dropped, the app keeps running in the tray."""
        self.window.withdraw()
        self.state.closed()
        self._stop_recent_tracking()
        self._animate()
        self.set_values(self.on_values())
        self.on_close()

    def destroy(self):
        self.state.closed()
        self._stop_recent_tracking()
        self._animate()
        self.window.destroy()


def ask_dest_choice(parent, old, new, files):
    """Ask what happens to the files in ``old``; a ``DEST_CHOICES`` key, or None for "Vazgeç".

    Modal over ``parent``. "Taşı" has the focus, so Enter moves; Escape and
    closing the window cancel the save.
    """
    import tkinter as tk
    from tkinter import ttk

    dialog = tk.Toplevel(parent)
    dialog.title(form.T_DEST_CHANGE_TITLE)
    dialog.transient(parent)
    dialog.resizable(False, False)
    answer = []

    def choose(choice):
        answer.append(choice)
        dialog.destroy()

    frame = ttk.Frame(dialog, padding=20)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text=form.T_DEST_CHANGE_TITLE, font=HEADING_FONT).grid(sticky="w", pady=(0, 8))
    ttk.Label(frame, text=form.dest_change_message(old, new, files), wraplength=480,
              justify="left").grid(sticky="w", pady=(0, 16))
    buttons = ttk.Frame(frame)
    buttons.grid(sticky="e")
    first = None
    for choice, title in form.DEST_CHOICES:
        button = ttk.Button(buttons, text=title, command=lambda c=choice: choose(c))
        button.pack(side="left", padx=4)
        first = first or button
    ttk.Button(buttons, text=form.T_CANCEL, command=dialog.destroy).pack(side="left", padx=4)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Return>", lambda _e: choose(form.DEST_CHOICES[0][0]))
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    first.focus_set()
    dialog.grab_set()
    dialog.wait_window()
    return answer[0] if answer else None


FIRST_COURSES_VISIBLE = 12  # more courses than this scroll


def ask_first_courses(parent, card):
    """The card before the first download at a school (``term_confirm``): the ids left ticked, or None."""
    import tkinter as tk
    from tkinter import ttk

    rows = term_confirm.card_rows(card)
    dialog = tk.Toplevel(parent)
    dialog.title(term_confirm.T_TITLE)
    dialog.transient(parent)
    dialog.resizable(False, False)
    answer = []
    frame = ttk.Frame(dialog, padding=20)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text=term_confirm.T_TITLE, font=("Segoe UI", 12, "bold")).grid(sticky="w", pady=(0, 8))
    ttk.Label(frame, text=term_confirm.card_message(card), wraplength=480,
              justify="left").grid(sticky="w", pady=(0, 12))
    holder = ttk.Frame(frame)
    holder.grid(sticky="nsew")
    canvas = tk.Canvas(holder, width=480, highlightthickness=0)
    inner = ttk.Frame(canvas)
    ticked = {}
    for course_id, label in rows:
        ticked[course_id] = tk.BooleanVar(dialog, value=True)
        ttk.Checkbutton(inner, text=label, variable=ticked[course_id]).pack(anchor="w", pady=2)
    canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.update_idletasks()
    canvas.configure(height=min(inner.winfo_reqheight(), 26 * FIRST_COURSES_VISIBLE),
                     scrollregion=(0, 0, inner.winfo_reqwidth(), inner.winfo_reqheight()))
    canvas.pack(side="left", fill="both", expand=True)
    if len(rows) > FIRST_COURSES_VISIBLE:
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")

    def confirm():
        answer.append({course_id for course_id, var in ticked.items() if var.get()})
        dialog.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(sticky="e", pady=(16, 0))
    later = ttk.Button(buttons, text=term_confirm.T_NOT_NOW, command=dialog.destroy)
    later.pack(side="left", padx=4)
    ok = ttk.Button(buttons, text=term_confirm.T_CONFIRM, command=confirm)
    ok.pack(side="left", padx=4)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    ok.focus_set()
    dialog.grab_set()
    dialog.wait_window()
    return answer[0] if answer else None


def ask_uninstall(parent, dest):
    from blackboard_sync import uninstall
    import tkinter as tk
    from tkinter import ttk

    dialog = tk.Toplevel(parent)
    dialog.title(uninstall.TITLE)
    dialog.transient(parent)
    dialog.resizable(False, False)
    answer = []
    delete_files = tk.BooleanVar(dialog, value=False)

    def confirm():
        answer.append(delete_files.get())
        dialog.destroy()

    frame = ttk.Frame(dialog, padding=20)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text=uninstall.MESSAGE, wraplength=480, justify="left").grid(sticky="w", pady=(0, 16))
    path = ttk.Label(frame, text=tr("The folder whose files go to the Recycle Bin:") + f"\n{dest}",
                     wraplength=480, justify="left")

    def toggled():
        if delete_files.get():
            path.grid(row=2, column=0, sticky="w", pady=12)
        else:
            path.grid_remove()

    ttk.Checkbutton(frame, text=uninstall.CHECKBOX, variable=delete_files,
                    command=toggled).grid(row=1, column=0, sticky="w")
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text=tr("Uninstall"), command=confirm).pack(side="left", padx=4)
    cancel = ttk.Button(buttons, text=form.T_CANCEL, command=dialog.destroy)
    cancel.pack(side="left", padx=4)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    cancel.focus_set()
    dialog.grab_set()
    dialog.wait_window()
    return answer[0] if answer else None
