"""Testable mapping from the shared model to Windows UI primitives."""

from pathlib import Path
from blackboard_sync.menubar.model import Icon, Notification

COLORS = {Icon.IDLE: "#236b45", Icon.SYNCING: "#1675d1",
          Icon.EXPIRED: "#d62728", Icon.ERROR: "#d98200", Icon.PAUSED: "#6b7280"}


def render_menu(entries, dispatch, menu_type, item_type):
    def render(entry):
        if not entry.title:
            return menu_type.SEPARATOR
        def clicked(icon, item):
            dispatch(entry.action, entry.value)
        action = (render_menu(entry.children, dispatch, menu_type, item_type)
                  if entry.children else clicked if entry.action else None)
        return item_type(entry.title, action, enabled=entry.enabled,
                         checked=(lambda item: entry.checked)
                         if entry.action == "autostart" or entry.checked else None)
    return menu_type(*(render(entry) for entry in entries))


def notification_fields(note: Notification) -> dict:
    from .activation import UPDATE_URI

    target = note.data.get("open")
    launch = UPDATE_URI if note.data.get("action") == "update" else Path(target).as_uri() if target else ""
    return {"app_id": "Blackboard Sync", "title": note.title, "msg": note.message,
            "launch": launch}


# The app's logo (the same file the main window shows), with a status dot unless all is well.
LOGO = Path(__file__).with_name("webui") / "logo.png"
ICON_SIZE = 64
# The dot sits over the logo's own round sync badge, bottom right, with a white ring.
DOT = (36, 36, 63, 63)
DOT_RING = 3


def icon_image(state: Icon):
    from PIL import Image, ImageDraw

    image = Image.open(LOGO).convert("RGBA").resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    if state != Icon.IDLE:
        draw = ImageDraw.Draw(image)
        draw.ellipse(DOT, fill="white")
        left, top, right, bottom = DOT
        draw.ellipse((left + DOT_RING, top + DOT_RING, right - DOT_RING, bottom - DOT_RING), fill=COLORS[state])
    return image
