"""Drive's rounded buttons for the Tk windows: "Sync now", "Sign in", "View all".

ttk buttons cannot have round corners, so a ``PillButton`` is a Canvas that draws a capsule with
the title in it. It takes ``text``, ``state`` and ``command`` through ``configure`` like a ttk
button and is placed with ``pack``/``grid`` on the same object. The macOS window has the same
buttons (``menubar/main_window._PillButton``): a bold title with 20 px of padding on each side;
neutral gray for the status card's own button, the accent tint for "View all".
"""

PILL_HEIGHT = 34
PILL_PADDING = 20  # between the capsule's end and the title, on each side
FONT = ("Segoe UI", 10, "bold")
GLYPH_WIDTH = 7  # px per character when the text cannot be measured (no display)

# fill: resting, hover and pressed; ink: the title. The "off" colors are for a disabled button.
NEUTRAL = {"fill": "#e6e8ec", "hover": "#dadde3", "pressed": "#cdd1d9", "ink": "#1f2937",
           "off_fill": "#eef0f3", "off_ink": "#9aa2ae"}
ACCENT = {"fill": "#dce7f5", "hover": "#cfdff3", "pressed": "#bed3ee", "ink": "#1f5fae",
          "off_fill": "#e8eef6", "off_ink": "#8fa6c4"}
FOCUS = "#1f5fae"
DARK_NEUTRAL = {"fill": "#303742", "hover": "#394350", "pressed": "#475569", "ink": "#f3f4f6",
                "off_fill": "#262d37", "off_ink": "#909aa8"}
DARK_ACCENT = {"fill": "#263f67", "hover": "#31517e", "pressed": "#3c6090", "ink": "#b6d0fa",
               "off_fill": "#293444", "off_ink": "#859ab8"}
DARK_FOCUS = "#8ab4f8"


def pill_width(text_width: float) -> int:
    """The capsule's width for a title ``text_width`` px wide."""
    return int(text_width + 0.999) + 2 * PILL_PADDING


def capsule_boxes(x0: int, y0: int, x1: int, y1: int) -> tuple[tuple, tuple, tuple]:
    """(left circle, middle rectangle, right circle) bounding boxes that together make a capsule."""
    r = (y1 - y0) // 2
    return (x0, y0, x0 + 2 * r, y1), (x0 + r, y0, x1 - r, y1), (x1 - 2 * r, y0, x1, y1)


def pill_colors(palette: dict, enabled: bool, hovered: bool, pressed: bool) -> tuple[str, str]:
    """(fill, ink) for the button's state."""
    if not enabled:
        return palette["off_fill"], palette["off_ink"]
    return palette["pressed" if pressed else "hover" if hovered else "fill"], palette["ink"]


class PillButton:
    def __init__(self, parent, text: str = "", command=None, accent: bool = False, background: str | None = None):
        import tkinter as tk

        from blackboard_sync.windows.sync_scene_view import background_of, is_dark

        self.options = {"text": text, "state": "normal", "command": command}
        self.hovered = self.pressed = self.focused = False
        self.width = pill_width(len(text) * GLYPH_WIDTH)
        canvas_background = background or background_of(parent)
        dark = is_dark(canvas_background)
        self.palette = (DARK_ACCENT if dark else ACCENT) if accent else (DARK_NEUTRAL if dark else NEUTRAL)
        self.focus_color = DARK_FOCUS if dark else FOCUS
        self.canvas = tk.Canvas(parent, height=PILL_HEIGHT, width=self.width, highlightthickness=0, borderwidth=0,
                                background=canvas_background, cursor="hand2", takefocus=1)
        for sequence, handler in (
            ("<Enter>", lambda _e: self._set(hovered=True)),
            ("<Leave>", lambda _e: self._set(hovered=False, pressed=False)),
            ("<ButtonPress-1>", lambda _e: self._set(pressed=True)),
            ("<ButtonRelease-1>", self._released),
            ("<FocusIn>", lambda _e: self._set(focused=True)),
            ("<FocusOut>", lambda _e: self._set(focused=False)),
            ("<Return>", lambda _e: self.invoke()),
            ("<space>", lambda _e: self.invoke()),
        ):
            self.canvas.bind(sequence, handler)
        self.draw()

    @property
    def enabled(self) -> bool:
        return self.options["state"] != "disabled"

    def configure(self, **options) -> None:
        """``text``, ``state`` ("normal" or "disabled") and ``command``, like a ttk button."""
        changed = False
        for key in ("text", "state", "command"):
            if key in options and options[key] != self.options[key]:
                self.options[key] = options[key]
                changed = True
        if changed:
            self.draw()

    def invoke(self) -> None:
        command = self.options["command"]
        if self.enabled and command is not None:
            command()

    def _set(self, **flags) -> None:
        for name, value in flags.items():
            setattr(self, name, value)
        self.draw()

    def _released(self, event) -> None:
        was_pressed, self.pressed = self.pressed, False
        self.draw()
        inside = 0 <= getattr(event, "x", 0) <= self.width and 0 <= getattr(event, "y", 0) <= PILL_HEIGHT
        if was_pressed and inside:
            self.invoke()

    def draw(self) -> None:
        canvas, text = self.canvas, self.options["text"]
        fill, ink = pill_colors(self.palette, self.enabled, self.hovered, self.pressed)
        canvas.delete("all")
        # The width comes from the title as the canvas lays it out.
        probe = canvas.create_text(0, 0, text=text, font=FONT, anchor="nw")
        box = canvas.bbox(probe)
        canvas.delete(probe)
        self.width = pill_width(box[2] - box[0] if box else len(text) * GLYPH_WIDTH)
        canvas.configure(width=self.width, cursor="hand2" if self.enabled else "arrow")
        if self.focused:  # a ring: the capsule in the focus color, the real one inset by 2 px
            self._capsule(0, 0, self.width, PILL_HEIGHT, self.focus_color)
            self._capsule(2, 2, self.width - 2, PILL_HEIGHT - 2, fill)
        else:
            self._capsule(0, 0, self.width, PILL_HEIGHT, fill)
        canvas.create_text(self.width / 2, PILL_HEIGHT / 2, text=text, font=FONT, fill=ink)

    def _capsule(self, x0: int, y0: int, x1: int, y1: int, color: str) -> None:
        left, middle, right = capsule_boxes(x0, y0, x1, y1)
        self.canvas.create_oval(*left, fill=color, outline=color)
        self.canvas.create_oval(*right, fill=color, outline=color)
        self.canvas.create_rectangle(*middle, fill=color, outline=color)

    def pack(self, **options) -> None:
        self.canvas.pack(**options)

    def pack_forget(self) -> None:
        self.canvas.pack_forget()

    def grid(self, **options) -> None:
        self.canvas.grid(**options)

    def destroy(self) -> None:
        self.canvas.destroy()
