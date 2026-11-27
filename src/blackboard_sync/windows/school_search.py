"""Only the matching schools under the school address field (the Tk fallback window).

While the student types, a list opens under the field without taking the keyboard focus; arrows and
Enter or a click pick a school. The field's arrow lists the matches, or every school for an empty
field or a saved address.
"""

from __future__ import annotations

from blackboard_sync import schools

VISIBLE_ROWS = 8


class SchoolSearch:
    def __init__(self, window, combobox, variable):
        self.window, self.combobox, self.variable = window, combobox, variable
        self.listbox = None  # made on the first match
        self.matches: list[str] = []
        self.index = 0
        self.typed = ""  # the text the list answers
        combobox.configure(postcommand=self.fill_dropdown)
        for event, handler in (("<KeyPress>", self.key_press), ("<KeyRelease>", self.key_release),
                               ("<FocusOut>", self.hide)):
            combobox.bind(event, handler)

    def _names(self) -> list[str]:
        return [school.name for school in schools.search(self.variable.get())]

    def fill_dropdown(self):
        """The arrow was pressed: its own list takes this one's place."""
        self.hide()
        self.combobox.configure(values=self._names() or schools.suggestions())

    def key_press(self, event):
        # The text before this key, so that key_release can tell typing from moving around.
        self.typed = self.variable.get()
        if not self.matches:
            return None
        if event.keysym in ("Down", "Up"):
            self.select(self.index + (1 if event.keysym == "Down" else -1))
        elif event.keysym in ("Return", "KP_Enter"):
            self.choose(self.index)
        elif event.keysym == "Escape":
            self.hide()
        else:
            return None
        return "break"  # not the combobox's own list, nor the window's Escape

    def key_release(self, _event=None):
        if self.variable.get() != self.typed:
            self.typed = self.variable.get()
            self.show()

    def show(self):
        matches = self._names()
        if not matches:
            self.hide()
            return
        if self.listbox is None:
            self._build()
        self.matches = matches
        self.listbox.delete(0, "end")
        for name in matches:
            self.listbox.insert("end", name)
        self.listbox.configure(height=min(len(matches), VISIBLE_ROWS))
        self.listbox.place(in_=self.combobox, x=0, rely=1.0, y=2, relwidth=1.0)
        self.listbox.lift()
        self.select(0)

    def _build(self):
        import tkinter as tk
        from tkinter import ttk

        style = ttk.Style(self.window)
        self.listbox = tk.Listbox(
            self.window, exportselection=False, activestyle="none", takefocus=0, relief="solid", borderwidth=1,
            highlightthickness=0, font=("Segoe UI", 10),
            background=style.lookup("TCombobox", "fieldbackground") or "white",
            foreground=style.lookup("TCombobox", "foreground") or "black")
        self.listbox.bind("<Button-1>", self.clicked)
        self.listbox.bind("<MouseWheel>", self.wheel)

    def select(self, index):
        self.index = min(max(index, 0), len(self.matches) - 1)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(self.index)
        self.listbox.see(self.index)

    def clicked(self, event):
        self.choose(self.listbox.nearest(event.y))
        return "break"  # the field keeps the focus

    def wheel(self, event):
        self.listbox.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"  # the page behind stays put

    def choose(self, index):
        """Put the school's name in the field (``normalize_base_url`` turns it into the address)."""
        if not 0 <= index < len(self.matches):
            return
        name = self.matches[index]
        self.hide()
        self.typed = name
        self.variable.set(name)
        self.combobox.icursor("end")

    def hide(self, _event=None):
        self.matches = []
        if self.listbox is not None:
            self.listbox.place_forget()
