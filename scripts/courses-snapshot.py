"""Render the native macOS Dersler section with invented courses, without signing in.

PYTHONPATH=src python scripts/courses-snapshot.py
Requires the app's Cocoa dependencies; writes docs/screenshots/courses-*.png.
"""
from datetime import datetime, timezone
from pathlib import Path

from AppKit import (NSApplication, NSAppearance, NSBitmapImageFileTypePNG,
                    NSBitmapImageRep, NSColor, NSGraphicsContext, NSImage, NSRectFill)

from blackboard_sync.courses import CourseRow
from blackboard_sync.menubar.main_window import MainWindow
from blackboard_sync.menubar.main_window_model import COURSES, main_status
from blackboard_sync.menubar.model import AppModel, RunOutcome
from blackboard_sync.menubar.settings_form import FormValues

TERM = "2026-2027 Güz"
ROWS = (
    CourseRow("_example1_1", "COE305", "Software Project Management", TERM, True),
    CourseRow("_example2_1", "CSE303", "Algorithm Analysis", TERM, True),
    CourseRow("_example3_1", "İNG101", "İngilizce I", TERM, False),
    CourseRow("_example4_1", "MTH201", "Linear Algebra", TERM, True),
)


def main():
    NSApplication.sharedApplication()
    root = Path(__file__).resolve().parents[1]
    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    model = AppModel(root / ".venv", now, last=RunOutcome("ok", finished_at=now))
    model.session = {"saved_at": now.timestamp(), "user": {"displayName": "Ada Öğrenci"}}
    values = FormValues("https://blackboard.example.edu", str(root / ".venv"), True)
    window = MainWindow(values, main_status(model, now), lambda *_: None, lambda *_: None,
                        lambda: None, on_courses=lambda: ROWS)
    window.select(COURSES)
    output = root / "docs" / "screenshots"
    output.mkdir(exist_ok=True)
    view = window.window.contentView()
    for theme, appearance in (("light", "NSAppearanceNameAqua"), ("dark", "NSAppearanceNameDarkAqua")):
        native_appearance = NSAppearance.appearanceNamed_(appearance)
        window.window.setAppearance_(native_appearance)

        def capture():
            # A window's content view is transparent: paint the window background first.
            image = NSImage.alloc().initWithSize_(view.bounds().size)
            image.lockFocus()
            NSColor.windowBackgroundColor().setFill()
            NSRectFill(view.bounds())
            view.displayRectIgnoringOpacity_inContext_(view.bounds(), NSGraphicsContext.currentContext())
            image.unlockFocus()
            bitmap = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
            bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(
                str(output / f"courses-{theme}.png"), True)

        native_appearance.performAsCurrentDrawingAppearance_(capture)
    window.window.close()


if __name__ == "__main__":
    main()
