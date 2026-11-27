"""The list under a school address field (AppKit): only the schools that match what is typed.

The list lives in the field's scroll view, so it moves with the field, and never takes the keyboard
focus: the student keeps typing, picks with the arrows and Return, or clicks a row.
"""

from __future__ import annotations

from typing import Callable

import objc
from AppKit import (NSBezelBorder, NSFont, NSLineBreakByTruncatingTail, NSScrollView, NSTableColumn, NSTableView,
                    NSTextFieldCell)
from Foundation import NSIndexSet, NSMakeRect, NSObject

from blackboard_sync import schools

ROW = 24
VISIBLE_ROWS = 8
MIN_WIDTH = 360  # the longest school names fit
_PLAIN_STYLE = 4  # NSTableViewStylePlain: no inset around the rows


class _MatchTable(NSTableView):
    def acceptsFirstResponder(self):
        return False  # the field keeps the focus

    def mouseDown_(self, event):
        # Pick on the press itself: NSTableView's own tracking would end the field's editing first.
        row = self.rowAtPoint_(self.convertPoint_fromView_(event.locationInWindow(), None))
        if row >= 0:
            self.picker.choose(row)


class _CenteredCell(NSTextFieldCell):
    def drawingRectForBounds_(self, bounds):
        rect = objc.super(_CenteredCell, self).drawingRectForBounds_(bounds)
        spare = max(0, rect.size.height - self.cellSizeForBounds_(bounds).height)
        return NSMakeRect(rect.origin.x + 4, rect.origin.y + spare / 2, rect.size.width - 4, rect.size.height - spare)


class _Rows(NSObject):
    """The table's data source."""

    def numberOfRowsInTableView_(self, _table):
        return len(self.picker.matches)

    def tableView_objectValueForTableColumn_row_(self, _table, _column, row):
        return self.picker.matches[row]


class SchoolPicker:
    """One list for the window, shown under whichever school field is being typed in."""

    def __init__(self, picked: Callable):
        self.picked = picked  # called with the field once a school's name is in it
        self.field = None
        self.matches: list[str] = []
        self.rows = _Rows.alloc().init()
        self.rows.picker = self
        self.table = _MatchTable.alloc().initWithFrame_(NSMakeRect(0, 0, MIN_WIDTH, ROW))
        self.table.picker = self
        column = NSTableColumn.alloc().initWithIdentifier_("school")
        column.setEditable_(False)
        cell = _CenteredCell.alloc().initTextCell_("")
        cell.setLineBreakMode_(NSLineBreakByTruncatingTail)
        cell.setFont_(NSFont.systemFontOfSize_(13))
        column.setDataCell_(cell)
        self.table.addTableColumn_(column)
        self.table.setHeaderView_(None)
        if self.table.respondsToSelector_("setStyle:"):
            self.table.setStyle_(_PLAIN_STYLE)
        self.table.setRowHeight_(ROW - self.table.intercellSpacing().height)
        self.table.setDataSource_(self.rows)
        self.view = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, MIN_WIDTH, ROW))
        self.view.setHasVerticalScroller_(True)
        self.view.setAutohidesScrollers_(True)
        self.view.setBorderType_(NSBezelBorder)
        self.view.setDocumentView_(self.table)

    def is_open(self) -> bool:
        return self.field is not None

    def show(self, field) -> None:
        """List the schools matching the field's text under it; close the list when none does."""
        self.matches = [school.name for school in schools.search(str(field.stringValue()))]
        scroll = field.enclosingScrollView()
        if not self.matches or scroll is None:
            self.hide()
            return
        self.field = field
        document = scroll.documentView()
        anchor = field.convertRect_toView_(field.bounds(), document)
        width = min(max(anchor.size.width, MIN_WIDTH), document.frame().size.width - 16)
        height = min(len(self.matches), VISIBLE_ROWS) * ROW + 4
        # Under the field, right edges together unless that would leave the page.
        x = max(8, anchor.origin.x + anchor.size.width - width)
        self.view.setFrame_(NSMakeRect(x, anchor.origin.y + anchor.size.height + 2, width, height))
        document.addSubview_(self.view)  # above the cards
        self.table.tableColumns()[0].setWidth_(self.view.contentSize().width - 4)
        self.table.reloadData()
        self._select(0)

    def hide(self) -> None:
        self.field = None
        self.view.removeFromSuperview()

    def move(self, step: int) -> None:
        self._select(min(max(self.table.selectedRow() + step, 0), len(self.matches) - 1))

    def _select(self, row: int) -> None:
        self.table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)
        self.table.scrollRowToVisible_(row)

    def choose(self, row: int | None = None) -> None:
        """Put the school's name in the field (``normalize_base_url`` turns it into the address)."""
        row = self.table.selectedRow() if row is None else row
        field = self.field
        if field is None or not 0 <= row < len(self.matches):
            return
        name = self.matches[row]
        self.hide()
        field.setStringValue_(name)
        editor = field.currentEditor()
        if editor is not None:
            editor.setSelectedRange_((len(name), 0))
        self.picked(field)
