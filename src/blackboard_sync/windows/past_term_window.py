"""Small native dialog; term selection and job decisions belong to AppModel."""

from blackboard_sync.menubar.model import T_PAST_TITLE, T_PAST_NOTE, T_PAST_LOADING, T_PAST_EMPTY


class PastTermWindow:
    def __init__(self, root, on_submit, on_close):
        import tkinter as tk
        from tkinter import ttk

        self.on_submit, self.on_close = on_submit, on_close
        self.window = window = tk.Toplevel(root)
        window.title(T_PAST_TITLE)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Dönem (eski dönem)").pack(anchor="w")
        self.term = tk.StringVar()
        self.dropdown = ttk.Combobox(frame, textvariable=self.term, state="disabled", width=58)
        self.dropdown.pack(fill="x", pady=(6, 10))
        ttk.Label(frame, text=T_PAST_NOTE).pack(anchor="w")
        self.status = ttk.Label(frame, text=T_PAST_LOADING, wraplength=480)
        self.status.pack(anchor="w", pady=10)
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        ttk.Button(buttons, text="Vazgeç", command=self.close).pack(side="left", padx=8)
        self.download = ttk.Button(buttons, text="İndir", command=self.submit, state="disabled")
        self.download.pack(side="left")
        window.lift()

    def update(self, names, message=""):
        self.dropdown.configure(values=names, state="readonly" if names else "disabled")
        self.term.set(names[0] if names else "")
        self.status.configure(text=message or ("" if names else T_PAST_EMPTY))
        self.download.configure(state="normal" if names else "disabled")

    def submit(self):
        if self.on_submit(self.term.get()):
            self.close()

    def close(self):
        self.window.destroy()
        self.on_close()

    def set_enabled(self, enabled):
        self.download.configure(state="normal" if enabled else "disabled")
