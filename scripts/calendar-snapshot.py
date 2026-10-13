"""Render the native macOS calendar with invented data, without signing in.

PYTHONPATH=src python scripts/calendar-snapshot.py
Requires the app's Cocoa dependencies; writes docs/images/calendar-*.png.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from AppKit import (NSApplication, NSAppearance, NSBitmapImageFileTypePNG,
                    NSBitmapImageRep, NSColor, NSGraphicsContext, NSImage, NSRectFill)

from blackboard_sync import deadlines
from blackboard_sync.menubar.main_window import MainWindow
from blackboard_sync.menubar.main_window_model import CALENDAR, main_status
from blackboard_sync.menubar.model import AppModel, RunOutcome
from blackboard_sync.menubar.settings_form import FormValues
from blackboard_sync.state import State


def main():
    NSApplication.sharedApplication()
    root = Path(__file__).resolve().parents[1]
    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    state = State(root / ".venv" / "snapshot-state.json")
    for course_id, name, items in (
        ("_example1_1", "CSE303 Algorithm Analysis", [("Proje raporu", "2026-10-13T13:30:00Z"),
                                                     ("Haftalık ödev", "2026-10-12T13:00:00Z")]),
        ("_example2_1", "MTH201 Linear Algebra", [("Ara sınav", "2026-10-14T06:30:00Z")]),
    ):
        state.deadline_courses[course_id] = {"name": name, "items": [deadlines.column_deadline({
            "id": f"_grade{i}_1", "name": title, "contentId": f"_content{i}_1", "grading": {"due": due}},
            course_id, "https://blackboard.example.edu") for i, (title, due) in enumerate(items)]}
    page = deadlines.calendar_page(state, root / ".venv", now, ZoneInfo("Europe/Istanbul"))
    model = AppModel(root / ".venv", now, last=RunOutcome("ok", finished_at=now))
    model.session = {"saved_at": now.timestamp(), "user": {"displayName": "Ada Öğrenci"}}
    values = FormValues("https://blackboard.example.edu", str(root / ".venv"), True)
    window = MainWindow(values, main_status(model, now), lambda *_: None, lambda *_: None,
                        lambda: None, on_deadlines=lambda: page)
    window.select(CALENDAR)
    output = root / "docs" / "images"
    output.mkdir(exist_ok=True)
    view = window.window.contentView()
    for theme, appearance in (("light", "NSAppearanceNameAqua"), ("dark", "NSAppearanceNameDarkAqua")):
        native_appearance = NSAppearance.appearanceNamed_(appearance)
        window.window.setAppearance_(native_appearance)

        def capture():
            # A window's content view is transparent. Paint its native window
            # background before rendering, including translucent warning cards.
            image = NSImage.alloc().initWithSize_(view.bounds().size)
            image.lockFocus()
            NSColor.windowBackgroundColor().setFill()
            NSRectFill(view.bounds())
            view.displayRectIgnoringOpacity_inContext_(view.bounds(), NSGraphicsContext.currentContext())
            image.unlockFocus()
            bitmap = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
            bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(
                str(output / f"calendar-{theme}.png"), True)

        native_appearance.performAsCurrentDrawingAppearance_(capture)
    window.window.close()


if __name__ == "__main__":
    main()
