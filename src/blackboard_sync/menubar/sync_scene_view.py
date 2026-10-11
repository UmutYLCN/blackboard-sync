"""The sync illustration on Genel bakış (AppKit): papers flying from a cloud into a folder.

The shapes and their motion come from ``sync_scene.py``, shared with the Tk
window; this view only draws them with ``NSBezierPath`` and redraws on a timer
while it animates. With "Reduce motion" (System Settings → Accessibility →
Display) it draws the still picture and runs no timer.
"""

from __future__ import annotations

import time

import objc
from AppKit import (
    NSAffineTransform,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSBezierPath,
    NSColor,
    NSGraphicsContext,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSTimer,
    NSView,
    NSWorkspace,
)
from Foundation import NSMakeRect

from blackboard_sync.menubar import sync_scene as scene


def _color(value: str, alpha: float = 1.0):
    value = value.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(red, green, blue, alpha)


def _rounded(rect, radius: float):
    left, top, right, bottom = rect
    return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(left, top, right - left, bottom - top), radius, radius)


def reduce_motion() -> bool:
    try:
        return bool(NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
    except AttributeError:
        return False


class SyncSceneView(NSView):
    """Draws the illustration scaled into its bounds; ``start()`` / ``stop()`` run the motion."""

    def initWithFrame_(self, frame):
        self = objc.super(SyncSceneView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.timer = None
        self.started = time.monotonic()
        self.still = False
        return self

    def isFlipped(self):
        return True

    @property
    def animating(self) -> bool:
        return self.timer is not None

    def start(self) -> None:
        """Animate (or show the still picture with reduce motion); nothing happens if it runs already."""
        self.still = reduce_motion()
        if self.still:
            self.stop()
        elif self.timer is None:
            self.started = time.monotonic()
            self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                scene.FRAME_SECONDS, self, "tick:", None, True)
            # Common modes: it keeps moving while a menu is open or the window is resized.
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)
        self.setNeedsDisplay_(True)

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    def tick_(self, _timer):
        window = self.window()
        if window is not None and window.isVisible() and not self.isHiddenOrHasHiddenAncestor():
            self.setNeedsDisplay_(True)

    def dark(self) -> bool:
        match = self.effectiveAppearance().bestMatchFromAppearancesWithNames_(
            [NSAppearanceNameAqua, NSAppearanceNameDarkAqua])
        return match == NSAppearanceNameDarkAqua

    def drawRect_(self, _rect):
        bounds = self.bounds()
        size, left, top = scene.fit(bounds.size.width, bounds.size.height)
        if size <= 0:
            return
        palette = scene.DARK if self.dark() else scene.LIGHT
        seconds = time.monotonic() - self.started
        transform = NSAffineTransform.transform()
        transform.translateXBy_yBy_(left, top)
        transform.scaleBy_(size)
        transform.concat()

        for x, y, alpha in scene.trail(seconds, self.still):
            _color(palette.accent, alpha).setFill()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x - 2, y - 2, 4, 4)).fill()

        _color(palette.folder_back).setFill()
        _rounded(scene.FOLDER_TAB, 4).fill()
        _rounded(scene.FOLDER_BACK, scene.CORNER).fill()

        for paper in scene.papers(seconds, self.still):
            self._draw_paper(paper, palette)

        # The cloud over the papers: they come out from behind it.
        _color(palette.cloud).setFill()
        cloud = _rounded(scene.CLOUD_BASE, (scene.CLOUD_BASE[3] - scene.CLOUD_BASE[1]) / 2)
        for x, y, radius in scene.CLOUD_PUFFS:
            cloud.appendBezierPath_(NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(x - radius, y - radius, 2 * radius, 2 * radius)))
        cloud.setWindingRule_(0)  # non-zero: the overlapping puffs fill as one shape
        cloud.fill()

        _color(palette.folder).setFill()
        _rounded(scene.FOLDER_FRONT, scene.CORNER).fill()
        glow = scene.landing_glow(seconds, self.still)
        _color(palette.accent, 0.35 + 0.65 * glow).setFill()
        left_edge, top_edge, right_edge, _bottom = scene.FOLDER_FRONT
        _rounded((left_edge + 8, top_edge + 7, right_edge - 8, top_edge + 10), 1.5).fill()

    def _draw_paper(self, paper, palette) -> None:
        width, height = scene.PAPER_SIZE
        transform = NSAffineTransform.transform()
        transform.translateXBy_yBy_(paper.x, paper.y)
        transform.rotateByDegrees_(paper.angle)
        transform.scaleBy_(paper.scale)
        NSGraphicsContext.saveGraphicsState()
        transform.concat()
        sheet = _rounded((-width / 2, -height / 2, width / 2, height / 2), 3)
        _color(palette.paper, paper.alpha).setFill()
        sheet.fill()
        _color(palette.paper_edge, paper.alpha).setStroke()
        sheet.setLineWidth_(1.4)
        sheet.stroke()
        _color(palette.paper_line, paper.alpha).setStroke()
        for offset, length in scene.PAPER_LINES:
            line = NSBezierPath.bezierPath()
            line.moveToPoint_((scene.PAPER_LINE_X, offset))
            line.lineToPoint_((scene.PAPER_LINE_X + length, offset))
            line.setLineWidth_(1.6)
            line.setLineCapStyle_(1)  # round
            line.stroke()
        NSGraphicsContext.restoreGraphicsState()
