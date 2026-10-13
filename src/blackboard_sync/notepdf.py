"""PDF copies of the Markdown notes, drawn with ReportLab.

The Markdown note stays the single source of truth: the PDF is rendered from
its text and understands what ``notes`` and ``htmltext`` produce (headings,
paragraphs and line breaks, bold, italic, inline code, code blocks, nested
bulleted and numbered lists, quotes, rules and links). Every link, including
bare web addresses, becomes a clickable URI link.

The output is byte-for-byte the same for the same note (fixed dates and
document id), so an unchanged note never looks changed to the sync. The fonts
are Noto Sans and Noto Sans Mono cut down to Latin and Turkish letters
(``assets/fonts``, SIL Open Font License); ReportLab embeds only the glyphs a
note uses, so a typical note stays well below 100 KB.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

FONT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "fonts"
SANS = "BBSyncSans"
MONO = "BBSyncMono"
_FONT_FILES = {
    SANS: "NotoSans-Regular.ttf",
    f"{SANS}-Bold": "NotoSans-Bold.ttf",
    f"{SANS}-Italic": "NotoSans-Italic.ttf",
    f"{SANS}-BoldItalic": "NotoSans-BoldItalic.ttf",
    MONO: "NotoSansMono-Regular.ttf",
}
LINK_COLOR = "#1a5fb4"
# Only these open from a PDF; anything else (relative or script links) stays plain text.
LINK_SCHEMES = ("http://", "https://", "mailto:", "ftp://")

_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_LIST_ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_AUTOLINK = re.compile(r"<((?:https?|ftp)://[^\s<>]+|mailto:[^\s<>]+)>")
_BARE_URL = re.compile(r"(?:https?|ftp)://[^\s<>\"']+")
# Characters that end a sentence rather than a bare web address.
_URL_TRAILING = ".,;:!?'\")]}"

# Characters each font can draw, filled in when the fonts are registered.
_covered: dict[str, frozenset[str]] = {}


def _register_fonts() -> dict[str, frozenset[str]]:
    if _covered:
        return _covered
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for name, file_name in _FONT_FILES.items():
        font = TTFont(name, str(FONT_DIR / file_name))
        pdfmetrics.registerFont(font)
        if name in (SANS, MONO):
            _covered[name] = frozenset(chr(code) for code in font.face.charToGlyph)
    for bold, italic, name in ((0, 0, SANS), (1, 0, f"{SANS}-Bold"), (0, 1, f"{SANS}-Italic"),
                               (1, 1, f"{SANS}-BoldItalic")):
        addMapping(SANS, bold, italic, name)
    for bold in (0, 1):
        for italic in (0, 1):
            addMapping(MONO, bold, italic, MONO)
    return _covered


def _text(text: str, mono: bool = False) -> str:
    """Escape text for a paragraph so that no character silently disappears.

    The sans font has no math symbols or arrows; those are drawn with the mono
    font, which has them. A character neither font has becomes U+FFFD (a replacement mark).
    """
    covered = _register_fonts()
    out: list[str] = []
    fallback: list[str] = []
    for ch in text:
        if ch in covered[MONO if mono else SANS] or ch in "\n\t":
            if fallback:
                out.append(f'<font face="{MONO}">{escape("".join(fallback))}</font>')
                fallback.clear()
            out.append(escape(ch))
        elif not mono and ch in covered[MONO]:
            fallback.append(ch)
        else:
            out.append("\ufffd")
    if fallback:
        out.append(f'<font face="{MONO}">{escape("".join(fallback))}</font>')
    return "".join(out)


# -- inline text ---------------------------------------------------------

def _link(url: str, label_markup: str) -> str:
    if not url.lower().startswith(LINK_SCHEMES):
        return label_markup
    return f'<a href="{escape(url, {chr(34): "&quot;"})}" color="{LINK_COLOR}">{label_markup}</a>'


def _plain(text: str, links: bool = True) -> str:
    """Escape text and make bare web addresses in it clickable."""
    if not links:
        return _text(text)
    out: list[str] = []
    pos = 0
    for match in _BARE_URL.finditer(text):
        url = match.group(0).rstrip(_URL_TRAILING)
        # Keep a closing bracket that belongs to the address: ".../Foo_(bar)".
        while url.count("(") > url.count(")") and match.group(0)[len(url):len(url) + 1] == ")":
            url += ")"
        out.append(_text(text[pos:match.start()]))
        out.append(_link(url, _text(url)))
        pos = match.start() + len(url)
    out.append(_text(text[pos:]))
    return "".join(out)


def _closing(text: str, start: int, opener: str, closer: str) -> int:
    """Index of the ``closer`` that balances the ``opener`` just before ``start``; -1 if none."""
    depth = 1
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _is_word(ch: str) -> bool:
    return ch.isalnum()


def inline(text: str, links: bool = True) -> str:
    """Markdown inline syntax to ReportLab paragraph markup (``links=False`` inside a link)."""
    out: list[str] = []
    plain: list[str] = []
    i = 0
    n = len(text)

    def flush() -> None:
        if plain:
            out.append(_plain("".join(plain), links))
            plain.clear()

    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] in "\\`*_[]()<>#!-":
            plain.append(text[i + 1])
            i += 2
            continue
        if ch == "`":
            end = text.find("`", i + 1)
            if end > i + 1:
                flush()
                out.append(f'<font face="{MONO}">{_text(text[i + 1:end], mono=True)}</font>')
                i = end + 1
                continue
        if ch == "<" and links:
            match = _AUTOLINK.match(text, i)
            if match:
                flush()
                out.append(_link(match.group(1), _text(match.group(1))))
                i = match.end()
                continue
        if ch == "!" and text.startswith("![", i):
            close = _closing(text, i + 2, "[", "]")
            if close != -1 and text.startswith("(", close + 1):
                end = _closing(text, close + 2, "(", ")")
                if end != -1:
                    flush()
                    alt = text[i + 2:close] or "image"
                    out.append(_link(text[close + 2:end].strip(), _text(f"[{alt}]")))
                    i = end + 1
                    continue
        if ch == "[":
            close = _closing(text, i + 1, "[", "]")
            if close != -1 and text.startswith("(", close + 1):
                end = _closing(text, close + 2, "(", ")")
                if end != -1:
                    flush()
                    out.append(_link(text[close + 2:end].strip(), inline(text[i + 1:close], False)))
                    i = end + 1
                    continue
        if text.startswith("**", i) and i + 2 < n and not text[i + 2].isspace():
            end = text.find("**", i + 2)
            while end != -1 and text[end - 1].isspace():
                end = text.find("**", end + 2)
            if end != -1:
                flush()
                out.append(f"<b>{inline(text[i + 2:end], links)}</b>")
                i = end + 2
                continue
        if ch == "_" and (i == 0 or not _is_word(text[i - 1])) and i + 1 < n and not text[i + 1].isspace():
            end = i + 1
            while True:
                end = text.find("_", end + 1)
                if end == -1 or (not text[end - 1].isspace() and (end + 1 == n or not _is_word(text[end + 1]))):
                    break
            if end != -1:
                flush()
                out.append(f"<i>{inline(text[i + 1:end], links)}</i>")
                i = end + 1
                continue
        plain.append(ch)
        i += 1
    flush()
    return "".join(out)


# -- blocks --------------------------------------------------------------

def _blocks(markdown: str) -> list[tuple]:
    """Split a note into ("heading", level, text), ("para", lines), ("code", lines),
    ("quote", lines), ("rule",) and ("item", depth, marker, lines) blocks."""
    blocks: list[tuple] = []
    lines = markdown.replace("\r\n", "\n").split("\n")
    para: list[str] = []
    indents: list[int] = []  # indentation of the open list levels
    item: list[str] | None = None

    def end_para() -> None:
        nonlocal item
        if para:
            blocks.append(("para", list(para)))
            para.clear()
        item = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if _FENCE.match(line):
            end_para()
            indents.clear()
            code: list[str] = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                code.append(lines[i])
                i += 1
            blocks.append(("code", code))
            i += 1
            continue
        if not line.strip():
            end_para()
            i += 1
            continue
        heading = _HEADING.match(line)
        list_item = _LIST_ITEM.match(line)
        if heading:
            end_para()
            indents.clear()
            blocks.append(("heading", len(heading.group(1)), heading.group(2).strip()))
        elif _RULE.match(line):
            end_para()
            indents.clear()
            blocks.append(("rule",))
        elif list_item:
            end_para()
            indent = len(list_item.group(1))
            while indents and indents[-1] > indent:
                indents.pop()
            if not indents or indents[-1] < indent:
                indents.append(indent)
            item = [list_item.group(3)]
            blocks.append(("item", len(indents) - 1, list_item.group(2), item))
        elif item is not None:
            item.append(line.strip())  # a line break inside a list item
        elif _QUOTE.match(line):
            end_para()
            indents.clear()
            quote = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                quote.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            blocks.append(("quote", quote))
            continue
        else:
            indents.clear()
            para.append(line.strip())
        i += 1
    end_para()
    return blocks


def _styles():
    from reportlab.lib.styles import ParagraphStyle

    body = ParagraphStyle("body", fontName=SANS, fontSize=10.5, leading=14.5, spaceAfter=6)
    headings = {
        level: ParagraphStyle(f"h{level}", parent=body, fontName=f"{SANS}-Bold", fontSize=size,
                              leading=size * 1.25, spaceBefore=4 if level == 1 else 8, spaceAfter=6)
        for level, size in ((1, 18), (2, 15), (3, 13), (4, 11.5), (5, 11), (6, 10.5))
    }
    code = ParagraphStyle("code", parent=body, fontName=MONO, fontSize=9, leading=12,
                          backColor="#f3f3f3", borderPadding=5, leftIndent=5, rightIndent=5,
                          spaceBefore=4, spaceAfter=10)
    quote = ParagraphStyle("quote", parent=body, leftIndent=14, textColor="#555555")
    return body, headings, code, quote


def _code_markup(lines: list[str]) -> str:
    rows = []
    for line in lines:
        stripped = line.lstrip(" ")
        rows.append("&nbsp;" * (len(line) - len(stripped)) + _text(stripped.replace("\t", "    "), mono=True))
    return "<br/>".join(rows) or "&nbsp;"


def _flowables(markdown: str) -> tuple[list, str]:
    """ReportLab flowables for a note, and its title (first heading)."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import HRFlowable, Paragraph, Spacer

    body, headings, code_style, quote_style = _styles()
    story: list = []
    title = ""
    item_styles: dict[int, ParagraphStyle] = {}
    for block in _blocks(markdown):
        kind = block[0]
        if kind == "heading":
            title = title or block[2]
            story.append(Paragraph(inline(block[2]), headings[block[1]]))
        elif kind == "para":
            story.append(Paragraph("<br/>".join(inline(line) for line in block[1]), body))
        elif kind == "quote":
            story.append(Paragraph("<br/>".join(inline(line) for line in block[1]), quote_style))
        elif kind == "code":
            story.append(Paragraph(_code_markup(block[1]), code_style))
        elif kind == "rule":
            story.append(Spacer(1, 2))
            story.append(HRFlowable(width="100%", thickness=0.6, color="#bbbbbb", spaceBefore=2, spaceAfter=8))
        elif kind == "item":
            depth, marker, lines = block[1], block[2], block[3]
            if depth not in item_styles:
                item_styles[depth] = ParagraphStyle(
                    f"item{depth}", parent=body, leftIndent=20 + depth * 20, bulletIndent=6 + depth * 20,
                    bulletFontName=SANS, spaceAfter=2,
                )
            bullet = marker if marker[0].isdigit() else "•" if depth % 2 == 0 else "–"
            story.append(Paragraph("<br/>".join(inline(line) for line in lines), item_styles[depth],
                                   bulletText=bullet))
    return story, title


def render_pdf(markdown: str) -> bytes:
    """The PDF for a Markdown note; the same text always gives the same bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    _register_fonts()
    story, title = _flowables(markdown)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=title, creator="Blackboard Sync", invariant=1, pageCompression=1, initialFontName=SANS,
    )
    doc.build(story)
    return buffer.getvalue()


def check_runtime() -> str:
    """Self-test of the packaged app: the fonts are found and a note with a link is drawn."""
    url = "https://blackboard.example.edu/ultra"
    pdf = render_pdf(f"# Ödev çğıİöşü\n\nOpen in Blackboard: <{url}>\n")
    if not pdf.startswith(b"%PDF-") or f"/URI ({url})".encode() not in pdf:
        raise RuntimeError("the PDF note has no link")
    return f"note pdf ok ({len(pdf)} bytes)"
