"""The macOS window mirrored for Arabic (menubar/rtl_layout.py), on stand-in views: no AppKit needed."""

from types import SimpleNamespace

from blackboard_sync.menubar import rtl_layout

LEFT, RIGHT, CENTER, NATURAL = 0, 2, 1, 4  # Apple silicon's values; the module takes them from AppKit


class View:
    def __init__(self, x, y, width, height, *children):
        self.x, self.y, self.width, self.height = x, y, width, height
        self.children = list(children)
        self.ident = None
        self.direction = 0

    def frame(self):
        return SimpleNamespace(origin=SimpleNamespace(x=self.x, y=self.y),
                               size=SimpleNamespace(width=self.width, height=self.height))

    def bounds(self):
        return SimpleNamespace(size=SimpleNamespace(width=self.width, height=self.height))

    def subviews(self):
        return self.children

    def setFrameOrigin_(self, origin):
        self.x, self.y = origin

    def identifier(self):
        return self.ident

    def setIdentifier_(self, value):
        self.ident = value

    def setUserInterfaceLayoutDirection_(self, value):
        self.direction = value

    def isKindOfClass_(self, kind):
        return isinstance(self, kind)


class Control(View):
    pass


class Label(Control):
    def __init__(self, x, y, width, height, alignment=NATURAL, editable=False):
        super().__init__(x, y, width, height)
        self.align, self.editable = alignment, editable

    def alignment(self):
        return self.align

    def setAlignment_(self, value):
        self.align = value

    def isEditable(self):
        return self.editable


class Scroll(View):
    def __init__(self, x, y, width, height, document):
        super().__init__(x, y, width, height, View(0, 0, width - 15, height))  # the clip view
        self.document = document

    def documentView(self):
        return self.document


KINDS = SimpleNamespace(control=Control, scroll=Scroll, text=Label, left=LEFT, right=RIGHT, natural=NATURAL)


def test_every_view_keeps_its_distance_from_the_other_side():
    title = Label(20, 10, 100, 20)
    size = Label(300, 10, 60, 20, alignment=RIGHT)
    centred = Label(150, 40, 100, 20, alignment=CENTER)
    card = View(10, 0, 400, 100, title, size, centred)
    sidebar = View(0, 0, 200, 600)
    root = View(0, 0, 1000, 600, sidebar, View(200, 0, 800, 600, card))
    rtl_layout.mirror(root, KINDS)
    assert (sidebar.x, card.x) == (800, 390)  # the sidebar moves to the right
    assert (title.x, size.x, centred.x) == (280, 40, 150)
    assert (title.align, size.align, centred.align) == (RIGHT, LEFT, CENTER)
    assert title.direction == rtl_layout.RIGHT_TO_LEFT


def test_running_again_moves_only_what_was_laid_out_again():
    moved, still = Label(20, 10, 100, 20), Label(200, 10, 100, 20)
    root = View(0, 0, 400, 100, moved, still)
    rtl_layout.mirror(root, KINDS)
    rtl_layout.mirror(root, KINDS)
    assert (moved.x, still.x, moved.align) == (280, 100, RIGHT)
    moved.setFrameOrigin_((30, 50))  # the window laid it out again, from the left
    moved.setAlignment_(NATURAL)  # ...and set its alignment again
    rtl_layout.mirror(root, KINDS)
    assert (moved.x, still.x, moved.align) == (270, 100, RIGHT)


def test_a_scroll_views_document_stays_and_its_content_is_mirrored():
    row = Label(20, 300, 100, 20)
    document = View(0, 0, 600, 900, row)
    scroll = Scroll(0, 40, 600, 400, document)
    rtl_layout.mirror(View(0, 0, 600, 500, scroll), KINDS)
    assert (document.x, row.x) == (0, 480)
    assert scroll.direction == rtl_layout.RIGHT_TO_LEFT  # its scroller on the left


def test_text_fields_keep_their_direction():
    path = Label(20, 10, 300, 24, alignment=NATURAL, editable=True)
    rtl_layout.mirror(View(0, 0, 400, 100, path), KINDS)
    assert path.x == 80 and path.align == NATURAL and path.direction == 0
