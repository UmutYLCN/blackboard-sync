from __future__ import annotations

import sys

import pytest

from blackboard_sync.windows import theme


def test_apps_use_light_theme_defaults_safely():
    assert theme.apps_use_light_theme(None)
    assert theme.apps_use_light_theme(1)
    assert not theme.apps_use_light_theme(0)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows UI runtime")
def test_real_theme_controls_in_both_appearance_modes(monkeypatch):
    """Exercise Tcl layouts and image assets that fake widgets cannot validate."""
    import tkinter as tk
    from tkinter import ttk
    from ttkbootstrap import Style

    root = tk.Tk()
    root.withdraw()
    try:
        for light in (True, False):
            monkeypatch.setattr(theme, "windows_uses_light_theme", lambda: light)
            theme.apply_theme(root)
            frame = ttk.LabelFrame(root, text="Calendar")
            frame.pack()
            controls = [
                ttk.Button(frame, text="Sync now"),
                ttk.Button(frame, text="Sign in", style="Accent.TButton"),
                ttk.Button(frame, text="Disconnect", style="Danger.TButton"),
                ttk.Button(frame, text="View all", style="Toolbutton"),
                ttk.Radiobutton(frame, text="Home", style="Navigation.TRadiobutton"),
                ttk.Entry(frame),
                ttk.Combobox(frame, values=("English", "Türkçe"), state="readonly"),
                ttk.Checkbutton(frame, text="Start at login"),
                ttk.Scrollbar(frame),
            ]
            for widget in controls:
                widget.pack()
            root.update_idletasks()
            assert all(widget.winfo_reqheight() > 0 for widget in controls)
            style = ttk.Style(root)
            assert style.lookup("Navigation.TRadiobutton", "background", ("selected",)) != style.lookup(
                "Navigation.TRadiobutton", "background"
            )
            for widget in controls:
                widget.state(["disabled"])
            root.update_idletasks()
            assert all(widget.instate(["disabled"]) for widget in controls)
            frame.destroy()
    finally:
        root.destroy()
        Style.instance = None
