"""Small HTML -> Markdown converter for Blackboard item bodies and announcements.

Blackboard bodies are short rich-text snippets (paragraphs, lists, links,
emphasis, the odd table). This handles those well enough for a readable note
without pulling in a heavier dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

_BLOCK = {"p", "div", "section", "article", "header", "footer", "table", "blockquote", "pre"}
_HEADINGS = {f"h{i}": i for i in range(1, 7)}
# Files live at /bbcswebdav/xid-<id> or, in Ultra, /bbcswebdav/pid-..-rid-<id>/xid-<id>?<signed query>.
_XID = re.compile(r"bbcswebdav/(?:[^?#\s\"']*/)?xid-(\d+_\d+)")
_RID = re.compile(r"bbcswebdav/[^?#\s\"']*rid-(\d+_\d+)")


@dataclass
class EmbeddedFile:
    """A file embedded in an item body (Ultra documents link files this way)."""

    xid: str  # stable file id; a replaced file gets a new one
    name: str
    url: str  # as found in the body; Ultra URLs carry a short-lived signed query


def body_text(body) -> str:
    """Return the HTML of a body field, whatever shape the API used for it."""
    if body is None:
        return ""
    if isinstance(body, dict):
        for key in ("rawText", "displayText", "text"):
            if body.get(key):
                return str(body[key])
        return ""
    return str(body)


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.lists: list[list] = []  # stack of [kind, counter]
        self.links: list[str | None] = []
        self.link_text_start: list[int] = []
        self.in_pre = 0
        self.cell_count = 0
        self.skip_file_link = 0  # inside <a data-bbfile>: the file is saved, not quoted

    # -- helpers ---------------------------------------------------------
    def _newlines(self, n: int) -> None:
        text = "".join(self.out)
        trailing = len(text) - len(text.rstrip("\n"))
        if not text.strip():
            return
        if trailing < n:
            self.out.append("\n" * (n - trailing))

    def _close_mark(self, mark: str) -> None:
        # Drop formatting that wraps nothing (common in editor-generated HTML).
        if self.out and self.out[-1] == mark:
            self.out.pop()
        elif self.out and self.out[-1].endswith(" ") and len(self.out) >= 2:
            # Keep the marker attached to the word: "**bold** " not "**bold **".
            self.out[-1] = self.out[-1].rstrip()
            self.out.append(mark + " ")
        else:
            self.out.append(mark)

    # -- parser callbacks ------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("data-bbfile"):
            if tag == "a":
                self.skip_file_link += 1
            return
        if self.skip_file_link:
            return
        if tag in _HEADINGS:
            self._newlines(2)
            self.out.append("#" * _HEADINGS[tag] + " ")
        elif tag in _BLOCK:
            self._newlines(2)
            if tag == "blockquote":
                self.out.append("> ")
            if tag == "pre":
                self.in_pre += 1
                self.out.append("```\n")
        elif tag == "br":
            self.out.append("\n")
        elif tag in ("ul", "ol"):
            self._newlines(1 if self.lists else 2)
            self.lists.append([tag, 0])
        elif tag == "li":
            self._newlines(1)
            indent = "  " * max(len(self.lists) - 1, 0)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.out.append(f"{indent}{self.lists[-1][1]}. ")
            else:
                self.out.append(f"{indent}- ")
        elif tag == "tr":
            self._newlines(1)
            self.cell_count = 0
        elif tag in ("td", "th"):
            if self.cell_count:
                self.out.append(" | ")
            self.cell_count += 1
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("_")
        elif tag == "code" and not self.in_pre:
            self.out.append("`")
        elif tag == "a":
            self.links.append(attrs.get("href"))
            self.link_text_start.append(len(self.out))
            self.out.append("[")
        elif tag == "img":
            alt = attrs.get("alt") or "image"
            src = attrs.get("src") or ""
            self.out.append(f"![{alt}]({src})" if src else f"[{alt}]")
        elif tag == "hr":
            self._newlines(2)
            self.out.append("---")
            self._newlines(2)

    def handle_endtag(self, tag):
        if tag == "a" and self.skip_file_link:
            self.skip_file_link -= 1
            return
        if self.skip_file_link:
            return
        if tag in _HEADINGS or tag in _BLOCK:
            if tag == "pre" and self.in_pre:
                self.in_pre -= 1
                self._newlines(1)
                self.out.append("```")
            self._newlines(2)
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self._newlines(1 if self.lists else 2)
        elif tag in ("strong", "b"):
            self._close_mark("**")
        elif tag in ("em", "i"):
            self._close_mark("_")
        elif tag == "code" and not self.in_pre:
            self._close_mark("`")
        elif tag == "a" and self.links:
            href = self.links.pop()
            start = self.link_text_start.pop()
            text = "".join(self.out[start + 1:]).strip()
            if not href:
                self.out[start] = ""
            elif not text or text == href:
                del self.out[start:]
                self.out.append(f"<{href}>")
            else:
                self.out.append(f"]({href})")

    def handle_data(self, data):
        if self.skip_file_link:
            return
        if self.in_pre:
            self.out.append(data)
            return
        data = re.sub(r"\s+", " ", data)
        text = "".join(self.out)
        if not text or text.endswith(("\n", " ", "- ", "> ")):
            data = data.lstrip()
        self.out.append(data)

    def result(self) -> str:
        text = "".join(self.out)
        lines = [line.rstrip() for line in text.split("\n")]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    if not html:
        return ""
    if "<" not in html:
        return html.strip()
    parser = _Converter()
    parser.feed(html)
    parser.close()
    return parser.result()


class _EmbedFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[EmbeddedFile] = []
        self._open: list[dict] = []

    def _add(self, url: str, name: str) -> None:
        match = _XID.search(url or "") or _RID.search(url or "")
        if not match:
            return
        if any(f.xid == match.group(1) for f in self.found):
            return
        self.found.append(EmbeddedFile(xid=match.group(1), name=name.strip(), url=url))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        meta = {}
        if attrs.get("data-bbfile"):
            try:
                meta = json.loads(attrs["data-bbfile"])
            except ValueError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        url = meta.get("resourceUrl") or attrs.get("href") or attrs.get("src") or ""
        name = meta.get("displayName") or meta.get("linkName") or meta.get("fileName") or ""
        if tag == "a":
            self._open.append({"url": url, "name": name, "text": []})
        elif _XID.search(url) or _RID.search(url):
            self._add(url, name or attrs.get("alt") or "")

    def handle_data(self, data):
        if self._open:
            self._open[-1]["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._open:
            link = self._open.pop()
            self._add(link["url"], link["name"] or "".join(link["text"]))


def find_embedded_files(html: str) -> list[EmbeddedFile]:
    """Files stored in Blackboard's content collection and linked from a body."""
    if not html or "bbcswebdav" not in html:
        return []
    finder = _EmbedFinder()
    finder.feed(html)
    finder.close()
    for link in finder._open:  # unclosed anchors
        finder._add(link["url"], link["name"] or "".join(link["text"]))
    return finder.found
