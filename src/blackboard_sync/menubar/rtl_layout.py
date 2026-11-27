"""Right to left for the AppKit window: its frame layout mirrored after the fact.

The macOS window places every view by its frame, measured from the left
(``main_window.py``). For a right-to-left language (Arabic) ``mirror`` moves each
view to the same distance from its parent's right edge, turns the alignment of
labels round (left to right, right to left; centred stays), and asks controls for
their right-to-left look (a checkbox's box, a pop-up's arrow, the scroller on the
left). A scroll view's document keeps its place; what it holds is mirrored.

Editable text fields keep their direction: they hold a school's address or a folder path.

``mirror`` writes what it did into each view's identifier, so running it again after
any layout moves only the views that layout placed anew; it is safe to run often.
"""

from __future__ import annotations

from types import SimpleNamespace

RIGHT_TO_LEFT = 1  # NSUserInterfaceLayoutDirectionRightToLeft
MARK = "rtl"


def appkit_kinds():
    """The AppKit classes and alignment values ``mirror`` needs (the values differ by CPU)."""
    import AppKit

    return SimpleNamespace(
        control=AppKit.NSControl, scroll=AppKit.NSScrollView, text=AppKit.NSTextField,
        left=AppKit.NSTextAlignmentLeft, right=AppKit.NSTextAlignmentRight, natural=AppKit.NSTextAlignmentNatural,
    )


def flipped_alignment(alignment: int, kinds) -> int:
    """Left (or the natural one, left in this app) becomes right, right becomes left."""
    if alignment in (kinds.left, kinds.natural):
        return kinds.right
    if alignment == kinds.right:
        return kinds.left
    return alignment


def _frame_mark(x: float, y: float, width: float, height: float) -> str:
    return f"{MARK} {x:g} {y:g} {width:g} {height:g}"


def mirror(view, kinds=None) -> None:
    """Mirror everything inside ``view`` (the window's content view) across its width."""
    kinds = kinds or appkit_kinds()
    _mirror_children(view, kinds)


def _mirror_children(parent, kinds) -> None:
    width = parent.bounds().size.width
    for child in parent.subviews():
        _place(child, width, kinds)
        if child.isKindOfClass_(kinds.scroll):
            document = child.documentView()
            if document is not None:
                _mirror_children(document, kinds)
        elif not child.isKindOfClass_(kinds.control):
            _mirror_children(child, kinds)


def _place(view, width: float, kinds) -> None:
    frame = view.frame()
    x, y = frame.origin.x, frame.origin.y
    w, h = frame.size.width, frame.size.height
    old = str(view.identifier() or "")
    frame_mark, _, align_mark = old.partition("|")
    if frame_mark != _frame_mark(x, y, w, h):  # laid out (again) from the left
        x = width - x - w
        view.setFrameOrigin_((x, y))
        frame_mark = _frame_mark(x, y, w, h)
    if view.isKindOfClass_(kinds.text) and view.isEditable():
        align_mark = ""
    elif view.isKindOfClass_(kinds.control) or view.isKindOfClass_(kinds.scroll):
        view.setUserInterfaceLayoutDirection_(RIGHT_TO_LEFT)
        if view.isKindOfClass_(kinds.text):
            alignment = view.alignment()
            if str(alignment) != align_mark:  # a new label, or the layout set its alignment again
                alignment = flipped_alignment(alignment, kinds)
                view.setAlignment_(alignment)
            align_mark = str(alignment)
    view.setIdentifier_(f"{frame_mark}|{align_mark}")
