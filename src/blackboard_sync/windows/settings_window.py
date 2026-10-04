"""Resizable native Tk settings form, using the shared validation model."""

from blackboard_sync.menubar import settings_form as form
from blackboard_sync.menubar.model import T_AUTOSTART

INTRO = ("Ders dosyalarınız her saat bu bilgisayara indirilir. Okulunuzun Blackboard "
         "adresini ve dosyaların kaydedileceği klasörü kontrol edin, sonra “Giriş yap” "
         "ile Blackboard'a girin.")


class SettingsWindow:
    def __init__(self, root, values, first_run, on_submit, on_close):
        import tkinter as tk
        from tkinter import ttk, filedialog

        self.window = window = tk.Toplevel(root)
        window.title(form.T_TITLE_FIRST_RUN if first_run else form.T_TITLE)
        window.minsize(560, 360)
        window.columnconfigure(0, weight=1)
        self.on_close = on_close
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=20)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        self.url = tk.StringVar(value=values.base_url)
        self.dest = tk.StringVar(value=values.dest)
        self.autostart = tk.BooleanVar(value=values.autostart)
        row = 0
        if first_run:
            ttk.Label(frame, text=INTRO, wraplength=520).grid(row=row, columnspan=2, sticky="w", pady=(0, 16))
            row += 1
        self.fields = {}
        for key, label, variable, hint in (
            ("base_url", form.T_URL_LABEL, self.url, form.T_URL_HINT),
            ("dest", form.T_DEST_LABEL, self.dest, form.T_DEST_HINT),
        ):
            ttk.Label(frame, text=label).grid(row=row, columnspan=2, sticky="w")
            entry = ttk.Entry(frame, textvariable=variable, width=65)
            entry.grid(row=row + 1, column=0, sticky="ew", pady=4)
            self.fields[key] = entry
            if key == "dest":
                def choose():
                    folder = filedialog.askdirectory(parent=window, title=form.T_CHOOSE_FOLDER_MESSAGE)
                    if folder:
                        self.dest.set(folder)
                ttk.Button(frame, text=form.T_CHOOSE_FOLDER, command=choose).grid(row=row + 1, column=1, padx=(8, 0))
            ttk.Label(frame, text=hint, wraplength=520).grid(row=row + 2, columnspan=2, sticky="w", pady=(0, 12))
            row += 3
        ttk.Checkbutton(frame, text=T_AUTOSTART, variable=self.autostart).grid(row=row, columnspan=2, sticky="w")
        self.error = ttk.Label(frame, foreground="#b00020", wraplength=520)
        self.error.grid(row=row + 1, columnspan=2, sticky="w", pady=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=row + 2, columnspan=2, sticky="e")
        def save(login):
            error = on_submit(form.FormValues(self.url.get(), self.dest.get(), self.autostart.get()), login)
            if error:
                message, field = error
                self.error.configure(text=message)
                self.fields.get(field, self.fields["base_url"]).focus_set()
            else:
                self.close()
        for label, callback in ((form.T_CANCEL, self.close), (form.T_SAVE, lambda: save(False)),
                                (form.T_LOGIN, lambda: save(True))):
            ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=4)
        self.show()

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self):
        self.window.destroy()
        self.on_close()
