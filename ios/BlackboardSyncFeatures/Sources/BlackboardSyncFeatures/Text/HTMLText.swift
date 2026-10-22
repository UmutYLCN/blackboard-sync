import Foundation

/// Blackboard's rich-text bodies made readable: the desktop's `htmltext.py` and the
/// announcement preview of `announcements.py`.
public enum HTMLText {
    /// The HTML of a body field, whatever shape the API used for it (`body_text`).
    public static func bodyHTML(_ body: JSONValue?) -> String {
        guard let body else { return "" }
        switch body {
        case .object:
            for key in ["rawText", "displayText", "text"] {
                if let value = body[key], value.isTruthy { return value.string ?? "" }
            }
            return ""
        case .string(let value):
            return value
        case .null:
            return ""
        default:
            return ""
        }
    }

    /// One line of plain text: the announcement list's preview before it is shortened.
    public static func plainText(_ html: String) -> String {
        var parts: [String] = []
        var hidden = 0
        for token in HTMLTokenizer.tokens(html) {
            switch token {
            case .start(let tag, _):
                if tag == "script" || tag == "style" { hidden += 1 }
                if ["p", "div", "br", "li", "tr"].contains(tag) { parts.append(" ") }
            case .end(let tag):
                if tag == "script" || tag == "style" { hidden = max(0, hidden - 1) }
                if ["p", "div", "li", "tr"].contains(tag) { parts.append(" ") }
            case .text(let data):
                if hidden == 0 { parts.append(data) }
            }
        }
        return parts.joined().split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    /// The body as light Markdown (headings, lists, emphasis, links), as the desktop writes
    /// it into an announcement's note (`html_to_markdown`). Files linked with `data-bbfile`
    /// are left out of the text; `EmbeddedFile.find` lists them.
    public static func markdown(_ html: String) -> String {
        if html.isEmpty { return "" }
        guard html.contains("<") else {
            return HTMLEntities.decode(html).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var converter = MarkdownConverter()
        for token in HTMLTokenizer.tokens(html) { converter.handle(token) }
        return converter.result()
    }
}

/// A port of the desktop's `_Converter`. It also hides `<script>`/`<style>` text, which the
/// desktop parser would quote.
private struct MarkdownConverter {
    private static let blocks: Set<String> = ["p", "div", "section", "article", "header", "footer",
                                              "table", "blockquote", "pre"]
    private static let headings: [String: Int] = ["h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6]

    private var out: [String] = []
    private var lists: [(kind: String, counter: Int)] = []
    private var links: [String] = []
    private var linkTextStart: [Int] = []
    private var inPre = 0
    private var cellCount = 0
    private var skipFileLink = 0  // inside <a data-bbfile>: the file is listed, not quoted
    private var hidden = 0

    mutating func handle(_ token: HTMLToken) {
        switch token {
        case .start(let tag, let attributes): start(tag, attributes)
        case .end(let tag): end(tag)
        case .text(let data): text(data)
        }
    }

    private var joined: String { out.joined() }

    private mutating func newlines(_ count: Int) {
        let text = joined
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let trailing = text.reversed().prefix { $0 == "\n" }.count
        if trailing < count { out.append(String(repeating: "\n", count: count - trailing)) }
    }

    private mutating func closeMark(_ mark: String) {
        // Drop formatting that wraps nothing (common in editor-generated HTML).
        if out.last == mark {
            out.removeLast()
        } else if let last = out.last, last.hasSuffix(" "), out.count >= 2 {
            // Keep the marker attached to the word: "**bold** " not "**bold **".
            out[out.count - 1] = last.trimmingTrailingWhitespace()
            out.append(mark + " ")
        } else {
            out.append(mark)
        }
    }

    private mutating func start(_ tag: String, _ attributes: [String: String]) {
        if !(attributes["data-bbfile"] ?? "").isEmpty {
            if tag == "a" { skipFileLink += 1 }
            return
        }
        if skipFileLink > 0 { return }
        if tag == "script" || tag == "style" {
            hidden += 1
        } else if let level = Self.headings[tag] {
            newlines(2)
            out.append(String(repeating: "#", count: level) + " ")
        } else if Self.blocks.contains(tag) {
            newlines(2)
            if tag == "blockquote" { out.append("> ") }
            if tag == "pre" {
                inPre += 1
                out.append("```\n")
            }
        } else if tag == "br" {
            out.append("\n")
        } else if tag == "ul" || tag == "ol" {
            newlines(lists.isEmpty ? 2 : 1)
            lists.append((tag, 0))
        } else if tag == "li" {
            newlines(1)
            // A nested list starts under its parent item's text, after "- " or "12. ".
            let indent = String(repeating: " ", count: lists.dropLast().reduce(0) {
                $0 + ($1.kind == "ol" ? "\($1.counter). ".count : 2)
            })
            if lists.last?.kind == "ol" {
                lists[lists.count - 1].counter += 1
                out.append("\(indent)\(lists[lists.count - 1].counter). ")
            } else {
                out.append("\(indent)- ")
            }
        } else if tag == "tr" {
            newlines(1)
            cellCount = 0
        } else if tag == "td" || tag == "th" {
            if cellCount > 0 { out.append(" | ") }
            cellCount += 1
        } else if tag == "strong" || tag == "b" {
            out.append("**")
        } else if tag == "em" || tag == "i" {
            out.append("_")
        } else if tag == "code", inPre == 0 {
            out.append("`")
        } else if tag == "a" {
            links.append(attributes["href"] ?? "")
            linkTextStart.append(out.count)
            out.append("[")
        } else if tag == "img" {
            let alt = attributes["alt"].flatMap { $0.isEmpty ? nil : $0 } ?? "image"
            let src = attributes["src"] ?? ""
            out.append(src.isEmpty ? "[\(alt)]" : "![\(alt)](\(src))")
        } else if tag == "hr" {
            newlines(2)
            out.append("---")
            newlines(2)
        }
    }

    private mutating func end(_ tag: String) {
        if tag == "a", skipFileLink > 0 {
            skipFileLink -= 1
            return
        }
        if skipFileLink > 0 { return }
        if tag == "script" || tag == "style" {
            hidden = max(0, hidden - 1)
        } else if Self.headings[tag] != nil || Self.blocks.contains(tag) {
            if tag == "pre", inPre > 0 {
                inPre -= 1
                newlines(1)
                out.append("```")
            }
            newlines(2)
        } else if tag == "ul" || tag == "ol" {
            if !lists.isEmpty { lists.removeLast() }
            newlines(lists.isEmpty ? 2 : 1)
        } else if tag == "strong" || tag == "b" {
            closeMark("**")
        } else if tag == "em" || tag == "i" {
            closeMark("_")
        } else if tag == "code", inPre == 0 {
            closeMark("`")
        } else if tag == "a", let href = links.popLast(), let start = linkTextStart.popLast() {
            let text = out[(start + 1)...].joined().trimmingCharacters(in: .whitespacesAndNewlines)
            if href.isEmpty {
                out[start] = ""
            } else if text.isEmpty || text == href {
                out.removeSubrange(start...)
                out.append("<\(href)>")
            } else {
                out.append("](\(href))")
            }
        }
    }

    private mutating func text(_ data: String) {
        if skipFileLink > 0 || hidden > 0 { return }
        if inPre > 0 {
            out.append(data)
            return
        }
        var data = Self.collapseWhitespace(data)
        let text = joined
        if text.isEmpty || ["\n", " ", "- ", "> "].contains(where: text.hasSuffix) {
            data = String(data.drop { $0.isWhitespace })
        }
        out.append(data)
    }

    /// `re.sub(r"\s+", " ", data)`.
    static func collapseWhitespace(_ data: String) -> String {
        var result = ""
        var inSpace = false
        for character in data {
            if character.isWhitespace {
                if !inSpace { result.append(" ") }
                inSpace = true
            } else {
                result.append(character)
                inSpace = false
            }
        }
        return result
    }

    func result() -> String {
        var text = joined.components(separatedBy: "\n").map { $0.trimmingTrailingWhitespace() }
            .joined(separator: "\n")
        while text.contains("\n\n\n") { text = text.replacingOccurrences(of: "\n\n\n", with: "\n\n") }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

extension String {
    func trimmingTrailingWhitespace() -> String {
        var copy = self
        while let last = copy.last, last.isWhitespace { copy.removeLast() }
        return copy
    }
}
