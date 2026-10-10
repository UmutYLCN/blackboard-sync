"""The main window (Tk): a sidebar with Başlangıç / Genel bakış, Genel and Silinenler.

What the window shows and means lives in ``menubar/main_window_model.py`` and
``menubar/settings_form.py``, shared with macOS; this module only lays out Tk
widgets and reports clicks. Closing only hides the window: the tray icon, the
timers and a running job go on, and the taskbar button leaves with the window.
"""

import logging
import sys
from pathlib import Path

from blackboard_sync import __version__, deleted, runtime
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar import settings_form as form
from blackboard_sync.menubar.model import T_RECENT, T_RECENT_EMPTY

log = logging.getLogger(__name__)

REOPEN_WHERE = "Başlat menüsünden"
WIDTH, HEIGHT = 940, 640  # what it opens with when the work area has room
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
WARNING = "#b00020"
MUTED = "#5f6b7a"


def work_area(window):
    """(left, top, width, height) of the screen above the taskbar."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
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


def wheel_steps(delta):
    """Lines to scroll for one mouse-wheel event; a touchpad's small deltas still move."""
    return int(-delta / 120) or (-1 if delta > 0 else 1)


class MainWindow:
    def __init__(self, root, values, status, on_submit, on_action, on_close, on_values=None,
                 on_open=lambda path: None, on_missing=lambda: [],
                 on_deleted_action=lambda action, keys: None, on_past_term=lambda name: None):
        import tkinter as tk
        from tkinter import ttk

        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.on_values = on_values or (lambda: self.saved)
        self.on_open, self.on_missing = on_open, on_missing
        self.on_deleted_action, self.on_past_term = on_deleted_action, on_past_term
        self.state = main.WindowState()
        self.selection = deleted.DeletedSelection()
        self.status = status
        self.saved = values
        self.error = ""
        self.checks = {}
        self._drawn_rows = None
        self._drawn_recent = None
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

        # The form's values; Başlangıç and Genel share them.
        self.url = tk.StringVar(value=values.base_url)
        self.dest = tk.StringVar(value=values.dest)
        self.autostart = tk.BooleanVar(value=values.autostart)
        self.check_updates = tk.BooleanVar(value=values.check_updates)
        self.interval = tk.StringVar(value=form.interval_title(values.sync_interval_minutes))
        self.past_term = tk.StringVar(value="")
        self.section_var = tk.StringVar(value=main.OVERVIEW)

        self._build_sidebar(window)
        self.pages = {}
        for name, build in (("start", self._build_start), (main.OVERVIEW, self._build_overview),
                            (main.GENERAL, self._build_general), (main.DELETED, self._build_deleted)):
            page = ttk.Frame(window, padding=(24, 20, 24, 16))
            page.grid(row=0, column=1, sticky="nsew")
            page.grid_remove()
            self.pages[name] = page
            build(page)
        for variable in (self.url, self.dest, self.autostart, self.check_updates, self.interval):
            variable.trace_add("write", lambda *_args: self.changed())
        # The wheel scrolls the section in view wherever the pointer is; over a
        # list it scrolls too instead of changing the choice.
        window.bind("<MouseWheel>", self.wheel)
        for combobox in (self.past_dropdown, self.interval_dropdown):
            combobox.bind("<MouseWheel>", lambda e: self.wheel(e) or "break")
        self.update_status(status)
        self.set_values(values)
        self._show_section()

    # -- layout --------------------------------------------------------------
    def _build_sidebar(self, window):
        from tkinter import ttk

        bar = ttk.Frame(window, padding=(14, 18, 14, 16), width=SIDEBAR)
        bar.grid(row=0, column=0, sticky="ns")
        bar.rowconfigure(5, weight=1)
        ttk.Label(bar, text=main.T_WINDOW_TITLE, font=HEADING_FONT).grid(row=0, column=0, sticky="w")
        ttk.Label(bar, text=__version__, foreground=MUTED).grid(row=1, column=0, sticky="w", pady=(0, 18))
        self.nav = {}
        for row, section in enumerate(main.SECTIONS, start=2):
            button = ttk.Radiobutton(bar, style="Toolbutton", variable=self.section_var, value=section,
                                     width=22, command=lambda s=section: self.select(s))
            button.grid(row=row, column=0, sticky="ew", pady=2)
            self.nav[section] = button
        self.sidebar_account = ttk.Label(bar, font=BOLD_FONT, wraplength=SIDEBAR - 28)
        self.sidebar_account.grid(row=6, column=0, sticky="sw")

    def _header(self, page, title, row=0):
        from tkinter import ttk

        label = ttk.Label(page, text=title, font=TITLE_FONT)
        label.grid(row=row, column=0, sticky="w", pady=(0, 12))
        return label

    def _scroll_area(self, page, row):
        """A vertically scrolling frame in ``page``; returns (canvas, frame)."""
        import tkinter as tk
        from tkinter import ttk

        canvas = tk.Canvas(page, highlightthickness=0)
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

        self.start_canvas, frame = self._scroll_area(page, 0)
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
        self.start_fields = {"base_url": ttk.Entry(card, textvariable=self.url, width=40)}
        self.start_fields["base_url"].grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        ttk.Label(card, text=form.T_DEST_LABEL).grid(row=2, column=0, columnspan=2, sticky="w")
        self.start_fields["dest"] = ttk.Entry(card, textvariable=self.dest)
        self.start_fields["dest"].grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(card, text=form.T_CHOOSE_FOLDER, command=self.choose_folder).grid(row=3, column=1, padx=(8, 0))
        ttk.Label(card, text=form.T_DEST_ROOT_NOTE, foreground=MUTED, wraplength=300).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Checkbutton(card, text=form.T_AUTOSTART, variable=self.autostart).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.start_button = ttk.Button(card, command=lambda: self.submit(self.status.start_login))
        self.start_button.grid(row=6, column=0, columnspan=2, sticky="ew")
        self.start_message = ttk.Label(card, wraplength=300)
        self.start_message.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_overview(self, page):
        from tkinter import ttk

        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        header = ttk.Frame(page)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.overview_title = self._header(header, "")
        ttk.Button(header, text=main.T_OPEN_FOLDER, command=lambda: self.on_action("folder")).grid(
            row=0, column=1, padx=(8, 0), pady=(0, 12))
        self.sync_button = ttk.Button(header, width=ACTION_WIDTH, command=lambda: self.on_action("sync"))
        self.sync_button.grid(row=0, column=2, padx=(8, 0), pady=(0, 12))

        account = ttk.LabelFrame(page, padding=(14, 10))
        account.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        account.columnconfigure(1, weight=1)
        self.avatar = ttk.Label(account, font=HEADING_FONT, width=3, anchor="center")
        self.avatar.grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 12))
        self.account_title = ttk.Label(account, font=HEADING_FONT)
        self.account_title.grid(row=0, column=1, sticky="w")
        self.account_detail = ttk.Label(account, foreground=MUTED)
        self.account_detail.grid(row=1, column=1, sticky="w")
        self.account_message = ttk.Label(account, wraplength=WRAP - 160)
        self.account_message.grid(row=2, column=1, sticky="w")
        self.badge = ttk.Label(account, foreground="#236b45", font=BOLD_FONT)
        self.badge.grid(row=0, column=2, rowspan=3, sticky="e")
        self.login_button = ttk.Button(account, command=lambda: self.on_action("login"))
        self.login_button.grid(row=0, column=3, rowspan=3, sticky="e", padx=(12, 0))

        recent = ttk.LabelFrame(page, text=T_RECENT, padding=(14, 8))
        recent.grid(row=2, column=0, columnspan=2, sticky="nsew")
        recent.columnconfigure(0, weight=1)
        recent.rowconfigure(1, weight=1)
        self.recent_count = ttk.Label(recent, foreground=MUTED)
        self.recent_count.grid(row=0, column=0, sticky="e")
        self.recent_canvas, self.recent_frame = self._scroll_area(recent, 1)

    def _build_general(self, page):
        from tkinter import ttk

        self._header(page, main.T_NAV_GENERAL)
        self.form_canvas, frame = self._scroll_area(page, 1)
        frame.configure(padding=(0, 0, 16, 8))
        frame.columnconfigure(0, weight=1)
        row = 0

        def place(widget, **options):
            nonlocal row
            widget.grid(row=row, column=0, columnspan=2, sticky="w", **options)
            row += 1
            return widget

        def section(text):
            nonlocal row
            if row:
                ttk.Separator(frame, orient="horizontal").grid(row=row, columnspan=2, sticky="ew", pady=(4, 10))
                row += 1
            place(ttk.Label(frame, text=text, font=HEADING_FONT), pady=(0, 6))

        def action_row(label, command):
            """A label on the left and a fixed-width button on the right."""
            nonlocal row
            label.grid(row=row, column=0, sticky="w", pady=(0, 12))
            button = ttk.Button(frame, width=ACTION_WIDTH, command=command)
            button.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=(0, 12))
            row += 1
            return button

        self.fields = {}
        section(form.T_SECTION_ACCOUNT)
        place(ttk.Label(frame, text=form.T_URL_LABEL))
        self.fields["base_url"] = ttk.Entry(frame, textvariable=self.url, width=65)
        self.fields["base_url"].grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        row += 1
        place(ttk.Label(frame, text=form.T_URL_HINT, foreground=MUTED, wraplength=WRAP), pady=(0, 8))
        self.account_label = ttk.Label(frame, wraplength=WRAP - 220)
        self.account_button = action_row(self.account_label, self.account_pressed)

        section(form.T_SECTION_FOLDER)
        place(ttk.Label(frame, text=form.T_DEST_LABEL))
        self.fields["dest"] = ttk.Entry(frame, textvariable=self.dest, width=65)
        self.fields["dest"].grid(row=row, column=0, sticky="ew", pady=4)
        ttk.Button(frame, text=form.T_CHOOSE_FOLDER, command=self.choose_folder).grid(row=row, column=1, padx=(8, 0))
        row += 1
        place(ttk.Label(frame, text=form.T_DEST_HINT, foreground=MUTED, wraplength=WRAP), pady=(0, 8))

        section(form.T_SECTION_PAST_TERMS)
        self.past_dropdown = ttk.Combobox(frame, textvariable=self.past_term, state="disabled")
        self.past_dropdown.grid(row=row, column=0, sticky="ew", pady=4)
        self.past_button = ttk.Button(frame, text=form.T_PAST_DOWNLOAD, width=ACTION_WIDTH,
                                      command=self.download_past_term, state="disabled")
        self.past_button.grid(row=row, column=1, sticky="e", padx=(8, 0))
        row += 1
        place(ttk.Label(frame, text=form.T_PAST_NOTE, foreground=MUTED, wraplength=WRAP))
        self.past_label = ttk.Label(frame, wraplength=WRAP)
        place(self.past_label, pady=(0, 8))

        section(form.T_SECTION_GENERAL)
        place(ttk.Checkbutton(frame, text=form.T_AUTOSTART, variable=self.autostart), pady=(0, 8))
        interval_row = ttk.Frame(frame)
        ttk.Label(interval_row, text=form.T_INTERVAL_LABEL + ":").pack(side="left", padx=(0, 8))
        self.interval_dropdown = ttk.Combobox(
            interval_row, textvariable=self.interval, state="readonly", width=20,
            values=[title for _, title in form.INTERVAL_OPTIONS],
        )
        self.interval_dropdown.pack(side="left")
        place(interval_row, pady=(0, 12))

        section(form.T_SECTION_UPDATES)
        place(ttk.Checkbutton(frame, text=form.T_CHECK_UPDATES, variable=self.check_updates), pady=(0, 8))
        self.version_label = ttk.Label(frame)
        self.update_button = action_row(self.version_label, lambda: self.on_action(self.status.form.update_action))
        self.uninstall_button = ttk.Button(frame, text=form.T_UNINSTALL, width=ACTION_WIDTH,
                                           command=lambda: self.on_action("uninstall"))
        self.uninstall_button.grid(row=row, column=1, sticky="e", padx=(8, 0))
        row += 1

        # Only while something is not saved (or saving failed): the reason, Vazgeç and Kaydet.
        self.button_bar = bar = ttk.Frame(page, padding=(0, 10, 0, 0))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.error_label = ttk.Label(bar, wraplength=WRAP - 200)
        self.error_label.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text=form.T_CANCEL, command=self.discard).grid(row=0, column=1, padx=4)
        ttk.Button(bar, text=form.T_SAVE, command=lambda: self.submit(False)).grid(row=0, column=2, padx=(4, 0))
        self.window.bind("<Escape>", lambda _e: self.discard() if self.bar_visible() else None)

    def _build_deleted(self, page):
        from tkinter import ttk

        self._header(page, main.T_NAV_DELETED)
        ttk.Label(page, text=deleted.T_HINT, foreground=MUTED, wraplength=WRAP).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.select_all_button = ttk.Button(page, text=deleted.T_SELECT_ALL, command=self.select_all)
        self.select_all_button.grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.canvas, self.rows_frame = self._scroll_area(page, 3)
        buttons = ttk.Frame(page)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 4))
        self.dismiss_button = ttk.Button(buttons, text=deleted.T_DISMISS, command=lambda: self.deleted_action("dismiss"))
        self.dismiss_button.pack(side="left", padx=(0, 8))
        self.refetch_button = ttk.Button(buttons, command=lambda: self.deleted_action("refetch"))
        self.refetch_button.pack(side="left")
        self.deleted_result = ttk.Label(page, wraplength=WRAP)
        self.deleted_result.grid(row=5, column=0, columnspan=2, sticky="w")

    def fit(self):
        """Open at the default size, but never taller than the work area; centred in it."""
        window = self.window
        window.update_idletasks()
        left, top, width, height = work_area(window)
        total = form.window_height(HEIGHT, CHROME, height)
        inner_width = min(WIDTH, max(MIN_WIDTH, width - 40))
        window.minsize(MIN_WIDTH, min(form.MIN_WINDOW_HEIGHT, total) - CHROME)
        x = left + max(0, (width - inner_width) // 2)
        y = top + max(0, (height - total) // 2)
        window.geometry(f"{inner_width}x{total - CHROME}+{x}+{y}")

    def wheel(self, event):
        canvas = {"start": self.start_canvas, main.OVERVIEW: self.recent_canvas,
                  main.GENERAL: self.form_canvas, main.DELETED: self.canvas}[self.visible_page()]
        first, last = canvas.yview()
        if first > 0 or last < 1:  # a section that fits stays put
            canvas.yview_scroll(wheel_steps(event.delta), "units")

    # -- behaviour ------------------------------------------------------------
    def show(self, section=None):
        """Open the window (or bring it forward) on ``section``; see ``WindowState.show``."""
        opening = not self.state.open
        self.state.show(section)
        self._show_section()
        self.refresh_deleted()
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

    def release_topmost(self):
        try:
            self.window.attributes("-topmost", False)
        except Exception:  # closed meanwhile
            pass

    def select(self, section):
        self.state.select(section)
        self._show_section()

    def visible_page(self):
        section = self.state.section
        return "start" if section == main.OVERVIEW and self.status.first_run else section

    def _show_section(self):
        visible = self.visible_page()
        for name, page in self.pages.items():
            if name == visible:
                page.grid()
            else:
                page.grid_remove()
        self.section_var.set(self.state.section)
        if self.state.section == main.DELETED:
            self.refresh_deleted()

    def values(self):
        minutes = next((m for m, title in form.INTERVAL_OPTIONS if title == self.interval.get()), 60)
        return form.FormValues(self.url.get(), self.dest.get(), self.autostart.get(),
                               self.check_updates.get(), minutes)

    def set_values(self, values):
        """Show ``values`` as what is saved: the bar goes away."""
        self._loading = True
        try:
            self.url.set(values.base_url)
            self.dest.set(values.dest)
            self.autostart.set(values.autostart)
            self.check_updates.set(values.check_updates)
            self.interval.set(form.interval_title(values.sync_interval_minutes))
        finally:
            self._loading = False
        self.saved = values
        self.show_error("")

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
        first_run_changed = status.first_run != self.status.first_run
        self.status = status
        self.nav[main.OVERVIEW].configure(text=status.overview_title)
        self.nav[main.GENERAL].configure(text=main.T_NAV_GENERAL)
        self.sidebar_account.configure(text=status.account.title)
        if first_run_changed:
            self._show_section()
        # Başlangıç
        self.start_button.configure(text=status.start_title, state="normal" if status.start_enabled else "disabled")
        self._draw_start_message()
        # Genel bakış
        card = status.account
        self.overview_title.configure(text=status.overview_title)
        self.sync_button.configure(text=status.sync_title, state="normal" if status.sync_enabled else "disabled")
        self.avatar.configure(text=card.initials, foreground=WARNING if card.warning else "")
        self.account_title.configure(text=card.title)
        self.account_detail.configure(text=card.detail)
        self.account_message.configure(text=card.message, foreground=WARNING if card.warning else MUTED)
        self.badge.configure(text=card.badge)
        if card.action_title:
            self.login_button.configure(text=card.action_title, state="normal" if card.action_enabled else "disabled")
            self.login_button.grid()
        else:
            self.login_button.grid_remove()
        self._draw_recent()
        # Genel
        form_status = status.form
        self.account_label.configure(text=form_status.account,
                                     foreground=WARNING if form_status.account_warning else "")
        for button, title, enabled in (
            (self.account_button, form_status.account_title, form_status.account_enabled),
            (self.update_button, form_status.update_title, form_status.update_enabled),
        ):
            button.configure(text=title, state="normal" if enabled else "disabled")
        self.version_label.configure(text=form_status.version)
        self.uninstall_button.configure(state="normal" if form_status.uninstall_enabled else "disabled")
        terms = list(form_status.past_terms)
        self.past_dropdown.configure(values=terms, state="readonly" if terms else "disabled")
        if self.past_term.get() not in terms:
            self.past_term.set(terms[0] if terms else "")
        self.past_button.configure(state="normal" if form_status.past_enabled else "disabled")
        self.past_label.configure(text=form_status.past_message)
        # Silinenler
        self.deleted_result.configure(text=form_status.deleted_message)
        self.refresh_deleted()

    def _draw_recent(self):
        from tkinter import ttk

        rows = self.status.recent
        self.recent_count.configure(text=main.recent_count(rows))
        if rows == self._drawn_recent:
            return
        self._drawn_recent = rows
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        if not rows:
            ttk.Label(self.recent_frame, text=T_RECENT_EMPTY, foreground=MUTED).pack(anchor="w", pady=8)
        for row in rows:
            entry = ttk.Frame(self.recent_frame, padding=(0, 6))
            entry.pack(anchor="w", fill="x")
            ttk.Label(entry, text=row.kind or "•", width=5, anchor="center", font=BOLD_FONT,
                      foreground=MUTED).pack(side="left", padx=(0, 10))
            text = ttk.Frame(entry)
            text.pack(side="left", fill="x", expand=True)
            # A click opens the file in its own application.
            ttk.Button(text, text=row.name, style="Toolbutton",
                       command=lambda path=row.path: self.on_open(path)).pack(anchor="w")
            ttk.Label(text, text=row.detail, foreground=MUTED).pack(anchor="w", padx=(4, 0))

    def refresh_deleted(self):
        from tkinter import ttk, BooleanVar

        rows = self.on_missing()
        self.selection.refresh(rows)
        title = main.T_NAV_DELETED + (f" ({len(rows)})" if rows else "")
        self.nav[main.DELETED].configure(text=title)
        if rows != self._drawn_rows:
            for widget in self.rows_frame.winfo_children():
                widget.destroy()
            self.checks = {}
            if not rows:
                ttk.Label(self.rows_frame, text=deleted.T_EMPTY).pack(anchor="w", pady=12)
            for row in rows:
                variable = BooleanVar(value=row.key in self.selection.selected)
                entry = ttk.Frame(self.rows_frame, padding=(0, 4))
                entry.pack(anchor="w", fill="x")
                check = ttk.Checkbutton(entry, variable=variable,
                                        command=lambda k=row.key, v=variable: self.checked(k, v.get()))
                check.pack(side="left", anchor="n")
                text = ttk.Frame(entry)
                text.pack(side="left", fill="x", expand=True)
                ttk.Label(text, text=row.name, wraplength=WRAP - 60).pack(anchor="w")
                ttk.Label(text, text=main.deleted_detail(row), foreground=MUTED,
                          wraplength=WRAP - 60).pack(anchor="w")
                self.checks[row.key] = (variable, check)
            self._drawn_rows = rows
        self.update_deleted_buttons()

    def checked(self, key, checked):
        self.selection.select(key, checked)
        self.update_deleted_buttons()

    def select_all(self):
        self.selection.select_all()
        for variable, _ in self.checks.values():
            variable.set(True)
        self.update_deleted_buttons()

    def update_deleted_buttons(self):
        enabled = self.status.form.refetch_enabled
        self.select_all_button.configure(state="normal" if enabled and self.selection.rows else "disabled")
        self.refetch_button.configure(text=self.status.form.refetch_title,
                                      state="normal" if enabled and self.selection.keys() else "disabled")
        self.dismiss_button.configure(state="normal" if enabled and self.selection.keys() else "disabled")
        for _, check in self.checks.values():
            check.configure(state="normal" if enabled else "disabled")

    def deleted_action(self, action):
        keys = self.selection.keys()
        if not keys or not self.status.form.refetch_enabled:
            return
        error = self.on_deleted_action(action, keys)
        self.refresh_deleted()
        if error:
            self.deleted_result.configure(text=error)
        elif action == "dismiss":
            self.deleted_result.configure(text="Seçilen dosyalar listeden kaldırıldı.")

    def download_past_term(self):
        """Start the one-time download of the term picked in Eski dönemler; the window stays open."""
        name = self.past_term.get()
        if name and self.status.form.past_enabled:
            self.on_past_term(name)

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
        self.set_values(self.on_values())
        self.on_close()

    def destroy(self):
        self.state.closed()
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
    path = ttk.Label(frame, text=f"Geri Dönüşüm Kutusu'na taşınacak dosyaların klasörü:\n{dest}",
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
    ttk.Button(buttons, text="Kaldır", command=confirm).pack(side="left", padx=4)
    cancel = ttk.Button(buttons, text="Vazgeç", command=dialog.destroy)
    cancel.pack(side="left", padx=4)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    cancel.focus_set()
    dialog.grab_set()
    dialog.wait_window()
    return answer[0] if answer else None
