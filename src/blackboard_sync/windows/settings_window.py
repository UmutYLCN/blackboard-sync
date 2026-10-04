"""Resizable native Tk settings form, using the shared validation and status model."""

from blackboard_sync.menubar import settings_form as form

INTRO = ("Ders dosyalarınız her saat bu bilgisayara indirilir. Okulunuzun Blackboard "
         "adresini ve dosyaların kaydedileceği klasörü kontrol edin, sonra “Giriş yap” "
         "ile Blackboard'a girin.")
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
            place(ttk.Label(frame, text=INTRO, wraplength=520), pady=(0, 16))
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
        place(ttk.Checkbutton(frame, text=form.T_AUTOSTART, variable=self.autostart), pady=(0, 12))

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
        values = form.FormValues(self.url.get(), self.dest.get(), self.autostart.get(), self.check_updates.get())
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
