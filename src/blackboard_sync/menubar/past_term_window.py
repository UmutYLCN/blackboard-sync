"""AppKit presentation of the shared one-time past-term job."""

from AppKit import (NSApp, NSBackingStoreBuffered, NSButton, NSPopUpButton,
                    NSTextField, NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskTitled)
from Foundation import NSMakeRect, NSObject

from blackboard_sync.menubar.model import T_PAST_TITLE, T_PAST_NOTE, T_PAST_LOADING, T_PAST_EMPTY


class _PastTermTarget(NSObject):
    def download_(self, _sender):
        self.owner.submit()

    def cancel_(self, _sender):
        self.owner.window.close()

    def windowWillClose_(self, _notification):
        self.owner.on_close()


class PastTermWindow:
    def __init__(self, on_submit, on_close):
        self.on_submit, self.on_close = on_submit, on_close
        self.target = _PastTermTarget.alloc().init()
        self.target.owner = self
        self.window = window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 560, 210), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        window.setTitle_(T_PAST_TITLE)
        window.setReleasedWhenClosed_(False)
        window.setDelegate_(self.target)
        view = window.contentView()

        def label(text, y):
            control = NSTextField.labelWithString_(text)
            control.setFrame_(NSMakeRect(20, y, 520, 22))
            view.addSubview_(control)
            return control

        label("Dönem (eski dönem)", 170)
        self.dropdown = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(20, 130, 520, 30), False)
        self.dropdown.setEnabled_(False)
        view.addSubview_(self.dropdown)
        label(T_PAST_NOTE, 99)
        self.status = label(T_PAST_LOADING, 66)
        for title, x, action in (("Vazgeç", 350, "cancel:"), ("İndir", 450, "download:")):
            button = NSButton.alloc().initWithFrame_(NSMakeRect(x, 20, 90, 32))
            button.setTitle_(title)
            button.setBezelStyle_(1)
            button.setTarget_(self.target)
            button.setAction_(action)
            view.addSubview_(button)
            if action == "download:":
                self.download = button
                button.setEnabled_(False)
                button.setKeyEquivalent_("\r")
        window.center()
        NSApp.activateIgnoringOtherApps_(True)
        window.makeKeyAndOrderFront_(None)

    def update(self, names, message=""):
        self.dropdown.removeAllItems()
        self.dropdown.addItemsWithTitles_(names)
        self.dropdown.setEnabled_(bool(names))
        self.download.setEnabled_(bool(names))
        self.status.setStringValue_(message or ("" if names else T_PAST_EMPTY))
        self.status.setToolTip_(message or None)

    def submit(self):
        name = self.dropdown.titleOfSelectedItem()
        if name and self.on_submit(name):
            self.window.close()

    def set_enabled(self, enabled):
        self.download.setEnabled_(enabled)
