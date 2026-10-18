"""The Tk window's rounded buttons: their geometry, colors and clicks (no display needed)."""

from types import SimpleNamespace

from blackboard_sync.windows import pill_button
from blackboard_sync.windows.pill_button import (
    ACCENT,
    GLYPH_WIDTH,
    NEUTRAL,
    PILL_HEIGHT,
    PILL_PADDING,
    PillButton,
    capsule_boxes,
    pill_colors,
    pill_width,
)

from .test_windows import fake_tk


def test_the_width_is_the_title_and_padding_on_both_sides():
    assert pill_width(40) == 40 + 2 * PILL_PADDING
    assert pill_width(40.2) == 41 + 2 * PILL_PADDING  # a part of a pixel counts as a whole one
    assert pill_width(0) == 2 * PILL_PADDING


def test_the_capsule_is_two_circles_and_a_rectangle():
    left, middle, right = capsule_boxes(0, 0, 120, PILL_HEIGHT)
    radius = PILL_HEIGHT // 2
    assert left == (0, 0, PILL_HEIGHT, PILL_HEIGHT) and right == (120 - PILL_HEIGHT, 0, 120, PILL_HEIGHT)
    assert middle == (radius, 0, 120 - radius, PILL_HEIGHT)  # joins the circles' centers
    # Inset by 2 px (the focus ring), the ends stay round: a circle is as wide as it is high.
    left, middle, right = capsule_boxes(2, 2, 118, PILL_HEIGHT - 2)
    assert left[2] - left[0] == left[3] - left[1] == PILL_HEIGHT - 4 == right[2] - right[0]


def test_colors_follow_the_state():
    for palette in (NEUTRAL, ACCENT):
        assert pill_colors(palette, True, False, False) == (palette["fill"], palette["ink"])
        assert pill_colors(palette, True, True, False) == (palette["hover"], palette["ink"])
        assert pill_colors(palette, True, True, True) == (palette["pressed"], palette["ink"])
        assert pill_colors(palette, False, True, True) == (palette["off_fill"], palette["off_ink"])
    assert NEUTRAL["fill"] != ACCENT["fill"]


def make(monkeypatch, tmp_path, **kwargs):
    """A button on the fake Tk, and the fills it has drawn so far."""
    fake_tk(monkeypatch, tmp_path)
    import sys

    canvas_type = sys.modules["tkinter"].Canvas
    drawn = []  # one entry per capsule: the fills of the shapes it is made of
    shapes = []

    def shape(self, *a, **kw):
        shapes.append(kw["fill"])
        if len(shapes) % 3 == 0:
            drawn.append({"fill": shapes[-1], "rings": list(shapes[-3:])})

    monkeypatch.setattr(canvas_type, "create_oval", shape, raising=False)
    monkeypatch.setattr(canvas_type, "create_rectangle", shape, raising=False)
    clicks = []
    button = PillButton(None, kwargs.pop("text", "Sync now"), lambda: clicks.append("click"), **kwargs)
    return button, clicks, drawn


def release(button, x=10, y=10):
    button.canvas.bindings["<ButtonPress-1>"](None)
    button.canvas.bindings["<ButtonRelease-1>"](SimpleNamespace(x=x, y=y))


def test_it_is_as_wide_as_its_title(monkeypatch, tmp_path):
    button, _, _ = make(monkeypatch, tmp_path)
    assert button.width == pill_width(len("Sync now") * GLYPH_WIDTH)  # no display to measure on
    assert button.canvas.options["width"] == button.width and button.canvas.options["height"] == PILL_HEIGHT
    button.configure(text="Syncing…")
    assert button.width == pill_width(len("Syncing…") * GLYPH_WIDTH) and button.options["text"] == "Syncing…"
    button.configure(text="Sync now", state="normal")
    assert button.width == pill_width(len("Sync now") * GLYPH_WIDTH)


def test_a_click_inside_runs_the_command(monkeypatch, tmp_path):
    button, clicks, _ = make(monkeypatch, tmp_path)
    release(button)
    assert clicks == ["click"]
    release(button, x=button.width + 5)  # the pointer left before it was released
    release(button, y=-1)
    assert clicks == ["click"]


def test_the_keyboard_works_too(monkeypatch, tmp_path):
    button, clicks, _ = make(monkeypatch, tmp_path)
    button.canvas.bindings["<Return>"](None)
    button.canvas.bindings["<space>"](None)
    assert clicks == ["click", "click"]


def test_a_disabled_button_ignores_clicks_and_fades(monkeypatch, tmp_path):
    button, clicks, drawn = make(monkeypatch, tmp_path)
    button.configure(state="disabled")
    assert not button.enabled
    release(button)
    button.canvas.bindings["<Return>"](None)
    assert clicks == []
    assert drawn[-1]["fill"] == NEUTRAL["off_fill"] and button.canvas.options["cursor"] == "arrow"
    button.configure(state="normal")
    assert drawn[-1]["fill"] == NEUTRAL["fill"] and button.canvas.options["cursor"] == "hand2"
    release(button)
    assert clicks == ["click"]


def test_hover_press_and_focus_change_the_drawing(monkeypatch, tmp_path):
    button, _, drawn = make(monkeypatch, tmp_path, accent=True)
    assert drawn[-1]["fill"] == ACCENT["fill"]
    button.canvas.bindings["<Enter>"](None)
    assert drawn[-1]["fill"] == ACCENT["hover"]
    button.canvas.bindings["<ButtonPress-1>"](None)
    assert drawn[-1]["fill"] == ACCENT["pressed"]
    button.canvas.bindings["<Leave>"](None)
    assert drawn[-1]["fill"] == ACCENT["fill"]
    button.canvas.bindings["<FocusIn>"](None)
    # A ring: the capsule in the focus color, the real one drawn inside it.
    assert drawn[-2]["fill"] == pill_button.FOCUS and drawn[-1]["fill"] == ACCENT["fill"]
    button.canvas.bindings["<FocusOut>"](None)
    assert drawn[-1]["fill"] == ACCENT["fill"] and drawn[-2]["fill"] != pill_button.FOCUS


def test_it_is_placed_like_any_widget(monkeypatch, tmp_path):
    button, _, _ = make(monkeypatch, tmp_path)
    button.pack(side="left")
    assert button.canvas.packed
    button.pack_forget()
    assert not button.canvas.packed
    button.grid(row=0, column=0)
    assert not button.canvas.removed
    button.destroy()
    assert button.canvas.destroyed
