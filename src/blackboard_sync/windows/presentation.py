"""Testable mapping from the shared model to Windows UI primitives."""

from pathlib import Path
from blackboard_sync.menubar.model import Icon, Notification

COLORS = {Icon.IDLE: "#236b45", Icon.SYNCING: "#1675d1",
          Icon.EXPIRED: "#d62728", Icon.ERROR: "#d98200"}


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
    target = note.data.get("open")
    return {"app_id": "Blackboard Sync", "title": note.title, "msg": note.message,
            "launch": Path(target).as_uri() if target else ""}


def icon_image(state: Icon):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=12, fill=COLORS[state])
    if state == Icon.IDLE:
        draw.polygon([(12, 25), (32, 15), (52, 25), (32, 35)], fill="white")
        draw.line([(20, 33), (20, 43), (44, 43), (44, 33)], fill="white", width=4)
    elif state == Icon.SYNCING:
        draw.arc((15, 15, 49, 49), 30, 300, fill="white", width=5)
        draw.polygon([(46, 13), (50, 29), (36, 24)], fill="white")
    else:
        draw.line((32, 15, 32, 36), fill="white", width=6)
        draw.ellipse((29, 44, 35, 50), fill="white")
    return image
