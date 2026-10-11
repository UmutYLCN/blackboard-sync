"""The sync illustration on Genel bakış (Tk): papers flying from a cloud into a folder.

The shapes and their motion come from ``menubar/sync_scene.py``, shared with
the AppKit window; this class draws them on a ``Canvas`` and redraws on
``after`` while it animates. Tk has no transparency, so faded colours are mixed
with the canvas background; on a dark background it uses the dark palette.
With "Show animations in Windows" turned off it draws the still picture and
schedules nothing.
"""

import sys
import time

from blackboard_sync.menubar import sync_scene as scene

FALLBACK_BACKGROUND = "#f0f0f0"  # SystemButtonFace


def reduce_motion():
    """Whether Windows' animations are off (Settings → Accessibility → Visual effects)."""
    if sys.platform != "win32":
        return False
    import ctypes

    enabled = ctypes.c_int(1)
    if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):  # SPI_GETCLIENTAREAANIMATION
        return not enabled.value
    return False


def background_of(widget):
    """The ttk theme's background inside a ``LabelFrame`` as "#rrggbb" (SystemButtonFace on Windows)."""
    try:
        from tkinter import ttk

        style = ttk.Style(widget)
        name = style.lookup("TLabelframe", "background") or style.lookup("TFrame", "background") or "SystemButtonFace"
        red, green, blue = widget.winfo_rgb(name)
        return f"#{red // 256:02x}{green // 256:02x}{blue // 256:02x}"
    except Exception:  # unknown colour, or no display
        return FALLBACK_BACKGROUND


def is_dark(color):
    red, green, blue = (int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue < 128


def rounded(left, top, right, bottom, radius):
    """Points of a rounded rectangle for ``create_polygon(..., smooth=True)``."""
    return [left + radius, top, right - radius, top, right, top, right, top + radius,
            right, bottom - radius, right, bottom, right - radius, bottom, left + radius, bottom,
            left, bottom, left, bottom - radius, left, top + radius, left, top]


class SyncScene:
    """A canvas of ``width`` x ``height`` with the illustration; ``start()`` / ``stop()`` run the motion."""

    def __init__(self, parent, width, height, background=None):
        import tkinter as tk

        self.width, self.height = width, height
        self.background = background or FALLBACK_BACKGROUND
        self.canvas = tk.Canvas(parent, width=width, height=height, highlightthickness=0, borderwidth=0,
                                background=self.background)
        self.palette = scene.DARK if is_dark(self.background) else scene.LIGHT
        self.running = False
        self.job = None
        self.still = False
        self.started = time.monotonic()

    def start(self):
        """Animate (or draw the still picture with animations off); nothing happens if it runs already."""
        self.still = reduce_motion()
        if self.still:
            self.stop()
        elif not self.running:
            self.running = True
            self.started = time.monotonic()
            self.job = self.canvas.after(int(scene.FRAME_SECONDS * 1000), self.tick)
        self.draw()

    def stop(self):
        self.running = False
        if self.job is not None:
            self.canvas.after_cancel(self.job)
            self.job = None

    def tick(self):
        if not self.running:
            return
        self.job = self.canvas.after(int(scene.FRAME_SECONDS * 1000), self.tick)
        if self.canvas.winfo_ismapped():
            self.draw()

    def mix(self, color, alpha=1.0):
        return scene.blend(color, self.background, alpha)

    def draw(self):
        canvas, palette = self.canvas, self.palette
        canvas.delete("all")
        width = canvas.winfo_width() or self.width
        height = canvas.winfo_height() or self.height
        if width <= 1:  # not laid out yet
            width, height = self.width, self.height
        size, left, top = scene.fit(width, height)
        seconds = time.monotonic() - self.started

        def at(x, y):
            return left + x * size, top + y * size

        def box(rect, radius, color):
            x0, y0 = at(rect[0], rect[1])
            x1, y1 = at(rect[2], rect[3])
            canvas.create_polygon(rounded(x0, y0, x1, y1, radius * size), smooth=True, fill=color, outline="")

        for x, y, alpha in scene.trail(seconds, self.still):
            cx, cy = at(x, y)
            r = 2 * size
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.mix(palette.accent, alpha), outline="")

        box(scene.FOLDER_TAB, 4, palette.folder_back)
        box(scene.FOLDER_BACK, scene.CORNER, palette.folder_back)

        for paper in scene.papers(seconds, self.still):
            points = [value for x, y in scene.paper_outline(paper) for value in at(x, y)]
            canvas.create_polygon(points, fill=self.mix(palette.paper, paper.alpha),
                                  outline=self.mix(palette.paper_edge, paper.alpha), width=max(1, 1.4 * size))
            for start, end in scene.paper_lines(paper):
                canvas.create_line(*at(*start), *at(*end), fill=self.mix(palette.paper_line, paper.alpha),
                                   width=max(1, 1.6 * size), capstyle="round")

        # The cloud over the papers: they come out from behind it.
        for x, y, radius in scene.CLOUD_PUFFS:
            x0, y0 = at(x - radius, y - radius)
            x1, y1 = at(x + radius, y + radius)
            canvas.create_oval(x0, y0, x1, y1, fill=palette.cloud, outline="")
        box(scene.CLOUD_BASE, (scene.CLOUD_BASE[3] - scene.CLOUD_BASE[1]) / 2, palette.cloud)

        box(scene.FOLDER_FRONT, scene.CORNER, palette.folder)
        glow = scene.landing_glow(seconds, self.still)
        left_edge, top_edge, right_edge, _bottom = scene.FOLDER_FRONT
        box((left_edge + 8, top_edge + 7, right_edge - 8, top_edge + 10), 1.5,
            scene.blend(palette.accent, palette.folder, 0.35 + 0.65 * glow))
