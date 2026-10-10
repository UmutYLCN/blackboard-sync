"""The illustration on Genel bakış while a sync runs, without any GUI code.

Sheets of paper leave a cloud, fly in an arc and drop into a folder, one after
another, so the student sees that files are on their way. Both windows draw
the same shapes from here: ``main_window.py`` with AppKit (an ``NSView``) and
``windows/main_window.py`` on a Tk ``Canvas``. Coordinates are in a fixed
``WIDTH`` x ``HEIGHT`` design box with y growing downwards; a view scales the box
to fit and keeps it centred.

With reduce motion (macOS) or animations turned off (Windows) the papers stand
still along the arc: the same picture, without movement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WIDTH, HEIGHT = 240.0, 140.0
PERIOD = 2.4  # seconds one paper takes from the cloud into the folder
PAPERS = 3
FRAME_SECONDS = 1 / 30
STILL_PHASES = (0.22, 0.5, 0.8)

# The app's palette.
NAVY, CYAN, MUTED = "#0b1425", "#50ddf4", "#a9b8cd"

# (centre x, centre y, radius) of the cloud's puffs, and the rounded base under them.
CLOUD_PUFFS = ((54.0, 60.0, 19.0), (78.0, 46.0, 26.0), (103.0, 60.0, 18.0))
CLOUD_BASE = (35.0, 58.0, 121.0, 79.0)  # left, top, right, bottom
# The folder: its back with the tab, then the front the papers drop behind.
FOLDER_TAB = (152.0, 66.0, 178.0, 78.0)
FOLDER_BACK = (152.0, 72.0, 214.0, 120.0)
FOLDER_FRONT = (147.0, 86.0, 219.0, 124.0)
CORNER = 6.0
PAPER_SIZE = (22.0, 28.0)
# The text lines on a paper: (y offset from its centre, length), each starting at x = PAPER_LINE_X.
PAPER_LINES = ((-6.0, 12.0), (0.0, 12.0), (6.0, 7.0))
PAPER_LINE_X = -6.0
# The arc: a quadratic Bézier from inside the cloud, over the gap, into the folder.
ARC = ((86.0, 62.0), (130.0, 4.0), (183.0, 100.0))
TRAIL = 7  # small dots along the arc


@dataclass(frozen=True)
class Palette:
    cloud: str  # opaque: the papers pass behind it
    folder_back: str
    folder: str
    paper: str
    paper_edge: str
    paper_line: str
    accent: str


LIGHT = Palette(cloud="#d4dce6", folder_back="#2a3a57", folder=NAVY,
                paper="#ffffff", paper_edge=CYAN, paper_line=MUTED, accent=CYAN)
DARK = Palette(cloud="#4d535c", folder_back="#1d3150", folder="#2b4670",
               paper="#eef4fb", paper_edge=CYAN, paper_line=MUTED, accent=CYAN)


@dataclass(frozen=True)
class Paper:
    x: float  # centre, in design units
    y: float
    angle: float  # degrees, clockwise on screen
    scale: float
    alpha: float


def smoothstep(u: float) -> float:
    return u * u * (3 - 2 * u)


def arc_point(u: float) -> tuple[float, float]:
    (x0, y0), (x1, y1), (x2, y2) = ARC
    a, b, c = (1 - u) ** 2, 2 * (1 - u) * u, u * u
    return a * x0 + b * x1 + c * x2, a * y0 + b * y1 + c * y2


def paper_at(phase: float) -> Paper:
    """The paper ``phase`` (0..1) of the way along: it fades in, tilts over and lands."""
    u = smoothstep(phase)
    x, y = arc_point(u)
    alpha = min(1.0, phase / 0.15)
    return Paper(x, y, angle=-14 + 22 * u, scale=0.82 + 0.18 * math.sin(math.pi * min(u, 1.0)), alpha=alpha)


def phases(seconds: float, still: bool = False) -> tuple[float, ...]:
    if still:
        return STILL_PHASES
    base = (seconds / PERIOD) % 1.0
    return tuple((base + index / PAPERS) % 1.0 for index in range(PAPERS))


def papers(seconds: float, still: bool = False) -> tuple[Paper, ...]:
    """The papers to draw at ``seconds``, the one closest to the folder last (on top).

    Draw them over the folder's back but under its front and under the cloud:
    they come out from behind the cloud and drop into the folder.
    """
    return tuple(paper_at(phase) for phase in sorted(phases(seconds, still)))


def trail(seconds: float, still: bool = False) -> tuple[tuple[float, float, float], ...]:
    """(x, y, alpha) of the dots along the arc; a soft pulse runs from the cloud to the folder."""
    dots = []
    for index in range(TRAIL):
        u = (index + 1) / (TRAIL + 1)
        x, y = arc_point(u)
        if still:
            alpha = 0.45
        else:
            wave = math.cos(2 * math.pi * (u - seconds / PERIOD))
            alpha = 0.25 + 0.5 * max(0.0, wave)
        dots.append((x, y, alpha))
    return tuple(dots)


def landing_glow(seconds: float, still: bool = False) -> float:
    """How bright the folder's top edge is (0..1): it lights up as each paper drops in."""
    if still:
        return 0.6
    since = ((seconds / PERIOD) * PAPERS) % 1.0  # 0 right when a paper lands
    return max(0.0, 1.0 - since * 2.5)


def fit(width: float, height: float) -> tuple[float, float, float]:
    """(scale, left, top) that fit the design box into a ``width`` x ``height`` view, centred."""
    scale = max(0.0, min(width / WIDTH, height / HEIGHT))
    return scale, (width - WIDTH * scale) / 2, (height - HEIGHT * scale) / 2


def rotate(points, angle: float, cx: float, cy: float, scale: float = 1.0):
    """``points`` (relative to a centre) turned by ``angle`` degrees and moved to (cx, cy)."""
    rad = math.radians(angle)
    cos, sin = math.cos(rad), math.sin(rad)
    return [(cx + scale * (x * cos - y * sin), cy + scale * (x * sin + y * cos)) for x, y in points]


def paper_outline(paper: Paper):
    w, h = PAPER_SIZE[0] / 2, PAPER_SIZE[1] / 2
    return rotate(((-w, -h), (w, -h), (w, h), (-w, h)), paper.angle, paper.x, paper.y, paper.scale)


def paper_lines(paper: Paper):
    """The three text lines on a paper, as ((x1, y1), (x2, y2)) pairs."""
    lines = []
    for offset, length in PAPER_LINES:
        start, end = rotate(((PAPER_LINE_X, offset), (PAPER_LINE_X + length, offset)),
                            paper.angle, paper.x, paper.y, paper.scale)
        lines.append((start, end))
    return lines


def blend(color: str, background: str, alpha: float) -> str:
    """``color`` at ``alpha`` over ``background`` as one opaque "#rrggbb" (Tk has no transparency)."""
    def rgb(value: str):
        value = value.lstrip("#")
        return [int(value[i:i + 2], 16) for i in (0, 2, 4)]

    mixed = [round(a * alpha + b * (1 - alpha)) for a, b in zip(rgb(color), rgb(background))]
    return "#" + "".join(f"{max(0, min(255, part)):02x}" for part in mixed)
