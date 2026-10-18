"""A shared light/dark visual theme for the Windows Tk interface."""

from __future__ import annotations

LIGHT = {
    "window": "#f3f5f8",
    "surface": "#ffffff",
    "surface_hover": "#edf2f8",
    "text": "#202b3c",
    "muted": "#667386",
    "border": "#dce2eb",
    "accent": "#2864c5",
    "accent_text": "#ffffff",
    "accent_hover": "#1f55ad",
    "accent_soft": "#e8f0fc",
    "danger": "#b42332",
}

DARK = {
    "window": "#171b22",
    "surface": "#202630",
    "surface_hover": "#2a3340",
    "text": "#edf1f7",
    "muted": "#a1adbd",
    "border": "#394352",
    "accent": "#8ab4f8",
    "accent_text": "#172132",
    "accent_hover": "#a8c7fa",
    "accent_soft": "#2b3a50",
    "danger": "#ff8585",
}


def apps_use_light_theme(value: int | None) -> bool:
    """Translate Windows' AppsUseLightTheme registry value to a theme mode."""
    return value != 0


def windows_uses_light_theme() -> bool:
    """Read the user's Windows app appearance preference; default to light."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return apps_use_light_theme(value)
    except (ImportError, OSError):
        return True


def apply_theme(root):
    """Install a flat, accessible ttk theme before any app windows are built."""
    from ttkbootstrap import Style

    light = windows_uses_light_theme()
    colors = LIGHT if light else DARK
    style = Style(theme="flatly" if light else "darkly", default_button="neutral")
    root.configure(background=colors["window"])

    style.configure(".", font=("Segoe UI", 10))
    style.configure("TFrame", background=colors["window"])
    style.configure("TLabel", background=colors["window"], foreground=colors["text"])
    style.configure("Muted.TLabel", foreground=colors["muted"])
    style.configure("TLabelframe", background=colors["surface"], bordercolor=colors["border"],
                     borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=colors["surface"], foreground=colors["text"],
                     font=("Segoe UI", 10, "bold"))
    style.configure("TButton", background=colors["surface"], foreground=colors["text"],
                     bordercolor=colors["border"], padding=(12, 7), font=("Segoe UI", 10))
    style.map("TButton", background=[("disabled", colors["window"]),
                                     ("pressed", colors["accent_soft"]),
                                     ("active", colors["surface_hover"])],
              foreground=[("disabled", colors["muted"])])
    style.configure("Accent.TButton", background=colors["accent"], foreground=colors["accent_text"],
                     bordercolor=colors["accent"], padding=(14, 8), font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("disabled", colors["surface_hover"]),
                                             ("pressed", colors["accent_hover"]),
                                             ("active", colors["accent_hover"])],
              foreground=[("disabled", colors["muted"])])
    style.configure("Danger.TButton", foreground=colors["danger"])
    style.map("Danger.TButton", foreground=[("disabled", colors["muted"]),
                                             ("active", colors["danger"])])
    style.configure("Navigation.TRadiobutton", background=colors["window"], foreground=colors["muted"],
                     padding=(12, 9), anchor="w", font=("Segoe UI", 10))
    style.map("Navigation.TRadiobutton",
              background=[("selected", colors["accent_soft"]), ("active", colors["surface_hover"])],
              foreground=[("selected", colors["accent"]), ("active", colors["text"])])
    style.configure("Toolbutton", background=colors["surface"], foreground=colors["accent"],
                     padding=(4, 3), borderwidth=0)
    style.map("Toolbutton", background=[("pressed", colors["accent_soft"]),
                                         ("active", colors["surface_hover"])])
    # Sidebar choices act as navigation rows, without a radio indicator.
    style.layout("Navigation.TRadiobutton", style.layout("Toolbutton"))
    style.configure("TEntry", fieldbackground=colors["surface"], foreground=colors["text"],
                     insertcolor=colors["text"], bordercolor=colors["border"], padding=(9, 7))
    style.map("TEntry", bordercolor=[("focus", colors["accent"])],
              fieldbackground=[("disabled", colors["window"])])
    style.configure("TCombobox", fieldbackground=colors["surface"], foreground=colors["text"],
                     bordercolor=colors["border"], padding=(8, 6), arrowsize=12)
    style.map("TCombobox", fieldbackground=[("disabled", colors["window"]),
                                             ("readonly", colors["surface"])],
              foreground=[("disabled", colors["muted"])],
              bordercolor=[("focus", colors["accent"])])
    style.configure("TCheckbutton", background=colors["surface"], foreground=colors["text"],
                     padding=(3, 4))
    style.map("TCheckbutton", background=[("active", colors["surface"])],
              foreground=[("disabled", colors["muted"])])
    style.configure("TSeparator", background=colors["border"])
    return colors
