"""Resizable native Tk settings form, using the shared validation and status model."""

from blackboard_sync.menubar import settings_form as form

INTRO = form.intro_first_run("bu bilgisayara")
# Buttons whose title follows the app's state keep one width (in characters).
ACTION_WIDTH = 24


class SettingsWindow:
    def __init__(self, root, values, status, first_run, on_submit, on_action, on_close):
        import tkinter as tk
        from tkinter import ttk, filedialog

        self.window = window = tk.Toplevel(root)
        window.title(form.T_TITLE_FIRST_RUN if first_run else form.T_TITLE)
        window.minsize(560, 480)
        window.columnconfigure(0, weight=1)
        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.status = status
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=20)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        self.url = tk.StringVar(value=values.base_url)
        self.dest = tk.StringVar(value=values.dest)
        self.autostart = tk.BooleanVar(value=values.autostart)
        self.check_updates = tk.BooleanVar(value=values.check_updates)
        self.interval = tk.StringVar(value=form.interval_title(values.sync_interval_minutes))
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
            place(ttk.Label(frame, text=text, font=("Segoe UI", 11, "bold")), pady=(0, 6))

        def action_row(label, command):
            """A label on the left and a fixed-width button on the right."""
            nonlocal row
            label.grid(row=row, column=0, sticky="w", pady=(0, 12))
            button = ttk.Button(frame, width=ACTION_WIDTH, command=command)
            button.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=(0, 12))
            row += 1
            return button

        if first_run:
            intro = form.intro_first_run("bu bilgisayara", values.sync_interval_minutes)
            place(ttk.Label(frame, text=intro, wraplength=520), pady=(0, 16))
        self.fields = {}

        section(form.T_SECTION_ACCOUNT)
        place(ttk.Label(frame, text=form.T_URL_LABEL))
        self.fields["base_url"] = ttk.Entry(frame, textvariable=self.url, width=65)
        self.fields["base_url"].grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        row += 1
        place(ttk.Label(frame, text=form.T_URL_HINT, wraplength=520), pady=(0, 8))
        self.account_label = ttk.Label(frame, wraplength=300)
        self.account_button = action_row(self.account_label, self.account_pressed)

        section(form.T_SECTION_FOLDER)
        place(ttk.Label(frame, text=form.T_DEST_LABEL))
        self.fields["dest"] = ttk.Entry(frame, textvariable=self.dest, width=65)
        self.fields["dest"].grid(row=row, column=0, sticky="ew", pady=4)

        def choose():
            folder = filedialog.askdirectory(parent=window, title=form.T_CHOOSE_FOLDER_MESSAGE)
            if folder:
                self.dest.set(folder)
        ttk.Button(frame, text=form.T_CHOOSE_FOLDER, command=choose).grid(row=row, column=1, padx=(8, 0))
        row += 1
        place(ttk.Label(frame, text=form.T_DEST_HINT, wraplength=520), pady=(0, 8))
        self.refetch_button = action_row(ttk.Label(frame, text=form.T_REFETCH_HINT, wraplength=300),
                                         lambda: self.on_action("refetch"))

        section(form.T_SECTION_GENERAL)
        place(ttk.Checkbutton(frame, text=form.T_AUTOSTART, variable=self.autostart), pady=(0, 8))
        interval_row = ttk.Frame(frame)
        ttk.Label(interval_row, text=form.T_INTERVAL_LABEL + ":").pack(side="left", padx=(0, 8))
        ttk.Combobox(
            interval_row, textvariable=self.interval, state="readonly", width=20,
            values=[title for _, title in form.INTERVAL_OPTIONS],
        ).pack(side="left")
        place(interval_row, pady=(0, 12))

        section(form.T_SECTION_UPDATES)
        place(ttk.Checkbutton(frame, text=form.T_CHECK_UPDATES, variable=self.check_updates), pady=(0, 8))
        self.version_label = ttk.Label(frame)
        self.update_button = action_row(self.version_label, lambda: self.on_action(self.status.update_action))

        self.error = ttk.Label(frame, foreground="#b00020", wraplength=520)
        place(self.error, pady=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, columnspan=2, sticky="e")
        for label, callback in ((form.T_CANCEL, self.close), (form.T_SAVE, lambda: self.submit(False))):
            ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=4)
        self.update_status(status)
        self.show()

    def update_status(self, status):
        self.status = status
        self.account_label.configure(text=status.account,
                                     foreground="#b00020" if status.account_warning else "")
        for button, title, enabled in (
            (self.account_button, status.account_title, status.account_enabled),
            (self.refetch_button, status.refetch_title, status.refetch_enabled),
            (self.update_button, status.update_title, status.update_enabled),
        ):
            button.configure(text=title, state="normal" if enabled else "disabled")
        self.version_label.configure(text=status.version)

    def account_pressed(self):
        if self.status.account_action == "login":
            self.submit(True)  # sign in with the address in the field
        else:
            self.on_action(self.status.account_action)

    def submit(self, login):
        minutes = next((m for m, title in form.INTERVAL_OPTIONS if title == self.interval.get()), 60)
        values = form.FormValues(
            self.url.get(), self.dest.get(), self.autostart.get(), self.check_updates.get(), minutes
        )
        error = self.on_submit(values, login)
        if error:
            message, field = error
            self.error.configure(text=message)
            self.fields.get(field, self.fields["base_url"]).focus_set()
        else:
            self.close()

    def show(self):
        window = self.window
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

    def close(self):
        self.window.destroy()
        self.on_close()


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
    ttk.Label(frame, text=form.T_DEST_CHANGE_TITLE, font=("Segoe UI", 11, "bold")).grid(sticky="w", pady=(0, 8))
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
