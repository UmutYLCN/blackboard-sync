"""Resizable native Tk settings form, using the shared validation and status model."""

from blackboard_sync import deleted
from blackboard_sync.menubar import settings_form as form

INTRO = form.intro_first_run("bu bilgisayara")
# Buttons whose title follows the app's state keep one width (in characters).
ACTION_WIDTH = 24


class SettingsWindow:
    def __init__(self, root, values, status, first_run, on_submit, on_action, on_close,
                 on_missing=lambda: [], on_deleted_action=lambda action, keys: None,
                 on_past_term=lambda name: None):
        import tkinter as tk
        from tkinter import ttk, filedialog

        self.window = window = tk.Toplevel(root)
        window.title(form.T_TITLE_FIRST_RUN if first_run else form.T_TITLE)
        window.minsize(560, 480)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.status = status
        window.protocol("WM_DELETE_WINDOW", self.close)
        self.on_missing, self.on_deleted_action = on_missing, on_deleted_action
        self.on_past_term = on_past_term
        self.selection = deleted.DeletedSelection()
        self.notebook = ttk.Notebook(window)
        self.notebook.grid(sticky="nsew")
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="Genel")
        self.deleted_frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.deleted_frame, text=deleted.T_TAB)
        frame.columnconfigure(0, weight=1)
        self.url = tk.StringVar(value=values.base_url)
        self.dest = tk.StringVar(value=values.dest)
        self.autostart = tk.BooleanVar(value=values.autostart)
        self.check_updates = tk.BooleanVar(value=values.check_updates)
        self.interval = tk.StringVar(value=form.interval_title(values.sync_interval_minutes))
        self.past_term = tk.StringVar(value="")
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

        section(form.T_SECTION_PAST_TERMS)
        self.past_dropdown = ttk.Combobox(frame, textvariable=self.past_term, state="disabled")
        self.past_dropdown.grid(row=row, column=0, sticky="ew", pady=4)
        self.past_button = ttk.Button(frame, text=form.T_PAST_DOWNLOAD, width=ACTION_WIDTH,
                                      command=self.download_past_term, state="disabled")
        self.past_button.grid(row=row, column=1, sticky="e", padx=(8, 0))
        row += 1
        place(ttk.Label(frame, text=form.T_PAST_NOTE, wraplength=520))
        self.past_label = ttk.Label(frame, wraplength=520)
        place(self.past_label, pady=(0, 8))

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
        self.uninstall_button = ttk.Button(frame, text=form.T_UNINSTALL, width=ACTION_WIDTH,
                                           command=lambda: self.on_action("uninstall"))
        self.uninstall_button.grid(row=row, column=1, sticky="e", padx=(8, 0))
        row += 1

        self.error = ttk.Label(frame, foreground="#b00020", wraplength=520)
        place(self.error, pady=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, columnspan=2, sticky="e")
        for label, callback in ((form.T_CANCEL, self.close), (form.T_SAVE, lambda: self.submit(False))):
            ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=4)
        self._build_deleted()
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self.refresh_deleted())
        self.update_status(status)
        self.show()

    def update_status(self, status):
        self.status = status
        self.account_label.configure(text=status.account,
                                     foreground="#b00020" if status.account_warning else "")
        for button, title, enabled in (
            (self.account_button, status.account_title, status.account_enabled),
            (self.update_button, status.update_title, status.update_enabled),
        ):
            button.configure(text=title, state="normal" if enabled else "disabled")
        self.version_label.configure(text=status.version)
        self.uninstall_button.configure(state="normal" if status.uninstall_enabled else "disabled")
        terms = list(status.past_terms)
        self.past_dropdown.configure(values=terms, state="readonly" if terms else "disabled")
        if self.past_term.get() not in terms:
            self.past_term.set(terms[0] if terms else "")
        self.past_button.configure(state="normal" if status.past_enabled else "disabled")
        self.past_label.configure(text=status.past_message)
        self.deleted_result.configure(text=status.deleted_message)
        self.refresh_deleted()

    def _build_deleted(self):
        import tkinter as tk
        from tkinter import ttk

        frame = self.deleted_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=deleted.T_HINT, wraplength=520).grid(row=0, column=0, columnspan=2,
                                                                 sticky="ew", pady=(0, 12))
        self.canvas = tk.Canvas(frame, highlightthickness=0, height=360)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.rows_frame = ttk.Frame(self.canvas)
        child = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(child, width=e.width))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta / 120), "units"))
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=12)
        self.select_all_button = ttk.Button(buttons, text=deleted.T_SELECT_ALL, command=self.select_all)
        self.select_all_button.pack(side="left", padx=(0, 8))
        self.refetch_button = ttk.Button(buttons, command=lambda: self.deleted_action("refetch"))
        self.refetch_button.pack(side="left", padx=(0, 8))
        self.dismiss_button = ttk.Button(buttons, text=deleted.T_DISMISS, command=lambda: self.deleted_action("dismiss"))
        self.dismiss_button.pack(side="left")
        self.deleted_result = ttk.Label(frame, wraplength=520)
        self.deleted_result.grid(row=3, column=0, columnspan=2, sticky="w")
        self.checks = {}
        self._drawn_rows = None

    def refresh_deleted(self):
        from tkinter import ttk, BooleanVar

        rows = self.on_missing()
        self.selection.refresh(rows)
        if rows != self._drawn_rows:
            for widget in self.rows_frame.winfo_children():
                widget.destroy()
            self.checks = {}
            group = None
            if not rows:
                ttk.Label(self.rows_frame, text=deleted.T_EMPTY).pack(anchor="w", pady=12)
            for row in rows:
                if group != (row.term, row.course):
                    group = (row.term, row.course)
                    ttk.Label(self.rows_frame, text=f"{row.term} / {row.course}",
                              wraplength=490, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 4))
                variable = BooleanVar(value=row.key in self.selection.selected)
                entry = ttk.Frame(self.rows_frame)
                entry.pack(anchor="w", fill="x")
                check = ttk.Checkbutton(entry, variable=variable,
                                        command=lambda k=row.key, v=variable: self.checked(k, v.get()))
                check.pack(side="left", anchor="n")
                ttk.Label(entry, text=row.name, wraplength=450).pack(side="left", anchor="w")
                ttk.Label(self.rows_frame, text=row.folder, wraplength=480).pack(anchor="w", padx=24, pady=(0, 8))
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
        enabled = self.status.refetch_enabled
        self.select_all_button.configure(state="normal" if enabled and self.selection.rows else "disabled")
        self.refetch_button.configure(text=self.status.refetch_title,
                                      state="normal" if enabled and self.selection.keys() else "disabled")
        self.dismiss_button.configure(state="normal" if enabled and self.selection.keys() else "disabled")
        for _, check in self.checks.values():
            check.configure(state="normal" if enabled else "disabled")

    def deleted_action(self, action):
        keys = self.selection.keys()
        if not keys or not self.status.refetch_enabled:
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
        if name and self.status.past_enabled:
            self.on_past_term(name)

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
        self.refresh_deleted()
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
