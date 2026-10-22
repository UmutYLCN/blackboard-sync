import Foundation

/// The events Python's `HTMLParser(convert_charrefs=True)` reports, which the desktop's
/// parsers are written against: tags with lower-cased names and decoded attributes, and runs
/// of text with character references decoded.
enum HTMLToken: Equatable {
    case start(String, [String: String])
    case end(String)
    case text(String)
}

enum HTMLTokenizer {
    /// Never fails: markup it cannot read is skipped or kept as text, so one odd body cannot
    /// stop a page (`htmltext.feed_html`).
    static func tokens(_ html: String) -> [HTMLToken] {
        var scanner = Scanner(Array(html.unicodeScalars))
        var tokens: [HTMLToken] = []
        var text = String.UnicodeScalarView()

        func flush() {
            if !text.isEmpty {
                tokens.append(.text(HTMLEntities.decode(String(text))))
                text.removeAll()
            }
        }

        while let scalar = scanner.peek() {
            guard scalar == "<" else {
                text.append(scalar)
                scanner.advance()
                continue
            }
            let next = scanner.peek(1)
            if next == "!" || next == "?" {
                flush()
                scanner.skipDeclaration()
            } else if next == "/", let name = scanner.peek(2), name.properties.isAlphabetic {
                flush()
                scanner.advance(2)
                tokens.append(.end(scanner.name()))
                scanner.skip(past: ">")
            } else if let next, next.properties.isAlphabetic {
                flush()
                scanner.advance()
                let (name, attributes, selfClosing) = scanner.tag()
                tokens.append(.start(name, attributes))
                if selfClosing {
                    tokens.append(.end(name))
                } else if name == "script" || name == "style" {
                    // Raw text until the closing tag, as HTMLParser's CDATA content mode.
                    let raw = scanner.raw(until: "</\(name)")
                    if !raw.isEmpty { tokens.append(.text(raw)) }
                }
            } else {
                text.append(scalar)
                scanner.advance()
            }
        }
        flush()
        return tokens
    }

    private struct Scanner {
        let scalars: [Unicode.Scalar]
        var index = 0

        init(_ scalars: [Unicode.Scalar]) {
            self.scalars = scalars
        }

        func peek(_ offset: Int = 0) -> Unicode.Scalar? {
            index + offset < scalars.count ? scalars[index + offset] : nil
        }

        mutating func advance(_ count: Int = 1) {
            index = min(index + count, scalars.count)
        }

        mutating func skip(past terminator: Unicode.Scalar) {
            while let scalar = peek() {
                advance()
                if scalar == terminator { return }
            }
        }

        /// `<!-- -->`, `<!DOCTYPE>`, `<![CDATA[ ]]>`, `<?xml ?>`: nothing a reader sees.
        mutating func skipDeclaration() {
            if starts(with: "<!--") {
                advance(4)
                while peek() != nil, !starts(with: "-->") { advance() }
                advance(3)
            } else {
                skip(past: ">")
            }
        }

        func starts(with prefix: String) -> Bool {
            for (offset, scalar) in prefix.unicodeScalars.enumerated() where peek(offset) != scalar {
                return false
            }
            return true
        }

        mutating func name() -> String {
            var name = String.UnicodeScalarView()
            while let scalar = peek(), !scalar.properties.isWhitespace, scalar != ">", scalar != "/" {
                name.append(scalar)
                advance()
            }
            return String(name).lowercased()
        }

        mutating func skipSpace() {
            while let scalar = peek(), scalar.properties.isWhitespace { advance() }
        }

        mutating func tag() -> (String, [String: String], Bool) {
            let name = self.name()
            var attributes: [String: String] = [:]
            while true {
                skipSpace()
                guard let scalar = peek() else { return (name, attributes, false) }
                if scalar == ">" {
                    advance()
                    return (name, attributes, false)
                }
                if scalar == "/" {
                    advance()
                    if peek() == ">" {
                        advance()
                        return (name, attributes, true)
                    }
                    continue
                }
                var key = String.UnicodeScalarView()
                while let scalar = peek(), !scalar.properties.isWhitespace, !["=", ">"].contains(scalar),
                      !(scalar == "/" && peek(1) == ">") {
                    key.append(scalar)
                    advance()
                }
                if key.isEmpty {
                    advance()  // a stray character; HTMLParser drops it too
                    continue
                }
                skipSpace()
                var value: String?
                if peek() == "=" {
                    advance()
                    skipSpace()
                    value = HTMLEntities.decode(attributeValue())
                }
                let lowered = String(key).lowercased()
                attributes[lowered] = value ?? ""  // the last one wins, as dict(attrs) on the desktop
            }
        }

        mutating func attributeValue() -> String {
            var value = String.UnicodeScalarView()
            if let quote = peek(), quote == "\"" || quote == "'" {
                advance()
                while let scalar = peek(), scalar != quote {
                    value.append(scalar)
                    advance()
                }
                advance()
            } else {
                while let scalar = peek(), !scalar.properties.isWhitespace, scalar != ">" {
                    value.append(scalar)
                    advance()
                }
            }
            return String(value)
        }

        /// Text up to (not including) `terminator`, matched without regard to case.
        mutating func raw(until terminator: String) -> String {
            let lowered = Array(terminator.lowercased().unicodeScalars)
            var raw = String.UnicodeScalarView()
            while let scalar = peek() {
                if lowered.enumerated().allSatisfy({ offset, wanted in
                    peek(offset).map { Character($0).lowercased() == Character(wanted).lowercased() } ?? false
                }) {
                    break
                }
                raw.append(scalar)
                advance()
            }
            return String(raw)
        }
    }
}
