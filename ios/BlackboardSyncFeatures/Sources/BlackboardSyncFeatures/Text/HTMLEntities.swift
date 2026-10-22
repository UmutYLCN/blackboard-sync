import Foundation

/// Character references, as Python's `html.unescape`: numeric ones, and the named ones
/// instructors' editors actually write (Latin and Turkish letters, punctuation, symbols).
enum HTMLEntities {
    static func decode(_ text: String) -> String {
        guard text.contains("&") else { return text }
        let scalars = Array(text.unicodeScalars)
        var out = String.UnicodeScalarView()
        var index = 0
        while index < scalars.count {
            let scalar = scalars[index]
            if scalar == "&", let (value, length) = reference(scalars, at: index) {
                out.append(contentsOf: value.unicodeScalars)
                index += length
            } else {
                out.append(scalar)
                index += 1
            }
        }
        return String(out)
    }

    /// The text a reference at `start` stands for and how many scalars it spans.
    private static func reference(_ scalars: [Unicode.Scalar], at start: Int) -> (String, Int)? {
        var index = start + 1
        if index < scalars.count, scalars[index] == "#" {
            index += 1
            let hex = index < scalars.count && (scalars[index] == "x" || scalars[index] == "X")
            if hex { index += 1 }
            let digitsStart = index
            while index < scalars.count, hex ? scalars[index].properties.isASCIIHexDigit
                                             : ("0"..."9").contains(scalars[index]) { index += 1 }
            guard index > digitsStart else { return nil }
            let digits = String(String.UnicodeScalarView(scalars[digitsStart..<index]))
            if index < scalars.count, scalars[index] == ";" { index += 1 }
            let number = UInt32(digits.suffix(8), radix: hex ? 16 : 10) ?? 0xFFFD
            return (character(number), index - start)
        }
        let nameStart = index
        while index < scalars.count, ("0"..."9").contains(scalars[index])
                || ("a"..."z").contains(scalars[index]) || ("A"..."Z").contains(scalars[index]) { index += 1 }
        let name = String(String.UnicodeScalarView(scalars[nameStart..<index]))
        if index < scalars.count, scalars[index] == ";", let value = named[name] {
            return (value, index + 1 - start)
        }
        // Latin-1 names may omit the semicolon ("&amp" "&nbsp"); take the longest that fits.
        for length in stride(from: name.count, through: 2, by: -1) {
            let prefix = String(name.prefix(length))
            if let value = named[prefix], prefix != "apos", value.unicodeScalars.count == 1,
               value.unicodeScalars.first!.value < 0x100 {
                return (value, 1 + length)
            }
        }
        return nil
    }

    private static func character(_ number: UInt32) -> String {
        if let replaced = windows1252[number] { return replaced }
        guard number != 0, number <= 0x10FFFF, !(0xD800...0xDFFF).contains(number),
              let scalar = Unicode.Scalar(number) else { return "\u{FFFD}" }
        return String(Character(scalar))
    }

    /// Numeric references in the C1 range mean Windows-1252 characters, as browsers read them.
    private static let windows1252: [UInt32: String] = [
        0x80: "\u{20AC}", 0x85: "\u{2026}", 0x91: "\u{2018}", 0x92: "\u{2019}", 0x93: "\u{201C}",
        0x94: "\u{201D}", 0x95: "\u{2022}", 0x96: "\u{2013}", 0x97: "\u{2014}", 0x99: "\u{2122}",
    ]

    static let named: [String: String] = [
        "amp": "&", "lt": "<", "gt": ">", "quot": "\u{22}", "apos": "'", "nbsp": "\u{a0}",
        "ensp": "\u{2002}", "emsp": "\u{2003}", "thinsp": "\u{2009}", "shy": "\u{ad}", "zwnj": "\u{200c}",
        "zwj": "\u{200d}", "lrm": "\u{200e}", "rlm": "\u{200f}", "copy": "\u{a9}", "reg": "\u{ae}",
        "trade": "\u{2122}", "deg": "\u{b0}", "plusmn": "\u{b1}", "times": "\u{d7}", "divide": "\u{f7}",
        "micro": "\u{b5}", "para": "\u{b6}", "middot": "\u{b7}", "sect": "\u{a7}", "hellip": "\u{2026}",
        "ndash": "\u{2013}", "mdash": "\u{2014}", "lsquo": "\u{2018}", "rsquo": "\u{2019}",
        "sbquo": "\u{201a}", "ldquo": "\u{201c}", "rdquo": "\u{201d}", "bdquo": "\u{201e}",
        "laquo": "\u{ab}", "raquo": "\u{bb}", "lsaquo": "\u{2039}", "rsaquo": "\u{203a}", "bull": "\u{2022}",
        "prime": "\u{2032}", "Prime": "\u{2033}", "euro": "\u{20ac}", "pound": "\u{a3}", "yen": "\u{a5}",
        "cent": "\u{a2}", "curren": "\u{a4}", "frac12": "\u{bd}", "frac14": "\u{bc}", "frac34": "\u{be}",
        "sup1": "\u{b9}", "sup2": "\u{b2}", "sup3": "\u{b3}", "iexcl": "\u{a1}", "iquest": "\u{bf}",
        "ordf": "\u{aa}", "ordm": "\u{ba}", "not": "\u{ac}", "macr": "\u{af}", "acute": "\u{b4}",
        "cedil": "\u{b8}", "uml": "\u{a8}", "larr": "\u{2190}", "rarr": "\u{2192}", "uarr": "\u{2191}",
        "darr": "\u{2193}", "harr": "\u{2194}", "rArr": "\u{21d2}", "lArr": "\u{21d0}", "hArr": "\u{21d4}",
        "le": "\u{2264}", "ge": "\u{2265}", "ne": "\u{2260}", "asymp": "\u{2248}", "infin": "\u{221e}",
        "minus": "\u{2212}", "sum": "\u{2211}", "prod": "\u{220f}", "radic": "\u{221a}", "alpha": "\u{3b1}",
        "beta": "\u{3b2}", "gamma": "\u{3b3}", "delta": "\u{3b4}", "epsilon": "\u{3b5}", "lambda": "\u{3bb}",
        "mu": "\u{3bc}", "pi": "\u{3c0}", "sigma": "\u{3c3}", "omega": "\u{3c9}", "Delta": "\u{394}",
        "Sigma": "\u{3a3}", "Omega": "\u{3a9}", "check": "\u{2713}", "cross": "\u{2717}", "star": "\u{2606}",
        "hearts": "\u{2665}", "Agrave": "\u{c0}", "Aacute": "\u{c1}", "Acirc": "\u{c2}", "Atilde": "\u{c3}",
        "Auml": "\u{c4}", "Aring": "\u{c5}", "AElig": "\u{c6}", "Ccedil": "\u{c7}", "Egrave": "\u{c8}",
        "Eacute": "\u{c9}", "Ecirc": "\u{ca}", "Euml": "\u{cb}", "Igrave": "\u{cc}", "Iacute": "\u{cd}",
        "Icirc": "\u{ce}", "Iuml": "\u{cf}", "Ntilde": "\u{d1}", "Ograve": "\u{d2}", "Oacute": "\u{d3}",
        "Ocirc": "\u{d4}", "Otilde": "\u{d5}", "Ouml": "\u{d6}", "Oslash": "\u{d8}", "Ugrave": "\u{d9}",
        "Uacute": "\u{da}", "Ucirc": "\u{db}", "Uuml": "\u{dc}", "Yacute": "\u{dd}", "szlig": "\u{df}",
        "agrave": "\u{e0}", "aacute": "\u{e1}", "acirc": "\u{e2}", "atilde": "\u{e3}", "auml": "\u{e4}",
        "aring": "\u{e5}", "aelig": "\u{e6}", "ccedil": "\u{e7}", "egrave": "\u{e8}", "eacute": "\u{e9}",
        "ecirc": "\u{ea}", "euml": "\u{eb}", "igrave": "\u{ec}", "iacute": "\u{ed}", "icirc": "\u{ee}",
        "iuml": "\u{ef}", "ntilde": "\u{f1}", "ograve": "\u{f2}", "oacute": "\u{f3}", "ocirc": "\u{f4}",
        "otilde": "\u{f5}", "ouml": "\u{f6}", "oslash": "\u{f8}", "ugrave": "\u{f9}", "uacute": "\u{fa}",
        "ucirc": "\u{fb}", "uuml": "\u{fc}", "yacute": "\u{fd}", "yuml": "\u{ff}", "Gbreve": "\u{11e}",
        "gbreve": "\u{11f}", "Idot": "\u{130}", "inodot": "\u{131}", "imath": "\u{131}", "Scedil": "\u{15e}",
        "scedil": "\u{15f}", "OElig": "\u{152}", "oelig": "\u{153}", "Scaron": "\u{160}",
        "scaron": "\u{161}", "Zcaron": "\u{17d}", "zcaron": "\u{17e}",
    ]
}
