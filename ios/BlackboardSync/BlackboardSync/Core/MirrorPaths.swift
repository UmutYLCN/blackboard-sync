import Foundation
import CryptoKit

/// Mirrors macOS naming: NFC, readable course codes, safe APFS components, preserved extensions.
enum MirrorPaths {
    static func name(_ raw: String) -> String {
        var text = EmbeddedFiles.entities(raw).precomposedStringWithCanonicalMapping
        text = text.replacingOccurrences(of: ": ", with: " - ")
            .replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
            .replacingOccurrences(of: "\\", with: "-")
        text = text.components(separatedBy: .controlCharacters).joined(separator: " ")
        text = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            .trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        if text.isEmpty { return "untitled" }
        let ext = (text as NSString).pathExtension
        let suffix = ext.isEmpty || ext.count > 10 || ext.contains(" ") ? "" : "." + ext
        var stem = suffix.isEmpty ? text : String(text.dropLast(suffix.count))
        while (stem + suffix).utf8.count > 240 { stem.removeLast() }
        return stem + suffix
    }

    static func course(_ course: Course) -> String {
        let pattern = #"\b([\p{L}]{2,6})\s?(\d{3,4}[\p{L}]?)(?:[-_.]\d{1,3})?\b"#
        let regex = try! NSRegularExpression(pattern: pattern)
        let title = EmbeddedFiles.entities(course.name).precomposedStringWithCanonicalMapping
        let source: String
        let match: NSTextCheckingResult?
        if let first = regex.firstMatch(in: title, range: NSRange(title.startIndex..., in: title)), first.range.location == 0 {
            source = title; match = first
        } else {
            source = course.code; match = regex.firstMatch(in: source, range: NSRange(source.startIndex..., in: source))
        }
        guard let match else {
            return name(course.code.isEmpty || course.code == course.id ? title : course.code + " " + title)
        }
        let ns = source as NSString
        let rawCode = ns.substring(with: match.range(at: 1)) + ns.substring(with: match.range(at: 2))
        let code = rawCode.uppercased(with: Locale(identifier: rawCode.unicodeScalars.allSatisfy(\.isASCII) ? "en" : "tr"))
        let rest = source == title ? ns.substring(from: NSMaxRange(match.range)).trimmingCharacters(in: CharacterSet(charactersIn: " -_:|")) : title
        return name(rest.isEmpty || rest.uppercased() == code ? code : code + " " + rest)
    }

    static func digest(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    static func numbered(_ path: String, _ n: Int) -> String {
        let url = URL(fileURLWithPath: path)
        let ext = url.pathExtension
        let stem = ext.isEmpty ? url.lastPathComponent : url.deletingPathExtension().lastPathComponent
        let file = name(stem + " (\(n))" + (ext.isEmpty ? "" : "." + ext))
        let parent = (path as NSString).deletingLastPathComponent
        return parent.isEmpty ? file : parent + "/" + file
    }

    static func isMedia(_ name: String, mime: String? = nil) -> Bool {
        let mime = (mime ?? "").lowercased()
        let extensions: Set<String> = ["mp4","m4v","mov","avi","mkv","wmv","webm","flv","f4v","mpg","mpeg","3gp","3g2","ogv","m2ts","mts","vob","asf","mp3","m4a","m4b","wav","aac","flac","ogg","oga","opus","wma","aif","aiff","amr","mka"]
        return mime.hasPrefix("audio/") || mime.hasPrefix("video/") || extensions.contains((name.lowercased() as NSString).pathExtension)
    }
}
