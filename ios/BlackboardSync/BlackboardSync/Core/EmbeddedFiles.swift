import Foundation

struct EmbeddedFile {
    let id: String
    let name: String
    let path: String
    let mime: String?
}

/// Tolerant attribute scanner. Only Blackboard collection files/explicit uploads are mirrored;
/// ordinary external links are never fetched. Signed URLs stay in memory only.
enum EmbeddedFiles {
    static func entities(_ text: String) -> String {
        var result = text
        let named = ["&quot;": "\"", "&#39;": "'", "&apos;": "'", "&lt;": "<", "&gt;": ">", "&nbsp;": " "]
        for (entity, value) in named { result = result.replacingOccurrences(of: entity, with: value) }
        let regex = try! NSRegularExpression(pattern: #"&#(x[0-9a-fA-F]+|[0-9]+);"#)
        for match in regex.matches(in: result, range: NSRange(result.startIndex..., in: result)).reversed() {
            let value = (result as NSString).substring(with: match.range(at: 1))
            let number = value.hasPrefix("x") ? UInt32(value.dropFirst(), radix: 16) : UInt32(value)
            if let number, let scalar = UnicodeScalar(number), let range = Range(match.range, in: result) {
                result.replaceSubrange(range, with: String(scalar))
            }
        }
        return result.replacingOccurrences(of: "&amp;", with: "&")
    }

    static func body(_ raw: Any?) -> String {
        if let text = raw as? String { return text }
        if let object = raw as? [String: Any] {
            return ["rawText", "displayText", "text"].compactMap { object[$0] as? String }.first(where: { !$0.isEmpty }) ?? ""
        }
        return ""
    }

    static func find(_ html: String) -> [EmbeddedFile] {
        let tags = try! NSRegularExpression(pattern: #"(?is)<(?:a|img|iframe|object|embed|source)\b([^>]*?)(?:>(.*?)</a\s*>|>)"#)
        let attrs = try! NSRegularExpression(pattern: #"(?is)([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"#)
        let identity = try! NSRegularExpression(pattern: #"(?:xid-|rid-)(\d+_\d+)"#)
        let upload = try! NSRegularExpression(pattern: #"/sessions/[^/]+/[^/]+/([0-9a-fA-F]{32})/"#)
        var seen: Set<String> = []
        var files: [EmbeddedFile] = []
        let ns = html as NSString
        for tag in tags.matches(in: html, range: NSRange(html.startIndex..., in: html)) {
            let raw = ns.substring(with: tag.range(at: 1))
            var attributes: [String: String] = [:]
            for attr in attrs.matches(in: raw, range: NSRange(raw.startIndex..., in: raw)) {
                let key = (raw as NSString).substring(with: attr.range(at: 1)).lowercased()
                let range = (2...4).map { attr.range(at: $0) }.first { $0.location != NSNotFound }!
                attributes[key] = entities((raw as NSString).substring(with: range))
            }
            let meta = attributes["data-bbfile"].flatMap { $0.data(using: .utf8) }
                .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
            let candidates = [meta["resourceUrl"] as? String, attributes["href"], meta["viewerUrl"] as? String, attributes["src"], attributes["data"]].compactMap { $0 }
            guard let rawURL = candidates.first(where: { $0.contains("bbcswebdav/") }) ?? candidates.first else { continue }
            var id: String?
            var path = rawURL
            if rawURL.contains("bbcswebdav/"), let match = identity.firstMatch(in: rawURL, range: NSRange(rawURL.startIndex..., in: rawURL)) {
                id = (rawURL as NSString).substring(with: match.range(at: 1))
                // Keep Ultra signed pid links, as on desktop. Classic xid links use a stable path.
                if !rawURL.contains("/pid-") { path = "/bbcswebdav/xid-\(id!)" }
            } else if !meta.isEmpty, let match = upload.firstMatch(in: rawURL, range: NSRange(rawURL.startIndex..., in: rawURL)) {
                id = "upload-" + (rawURL as NSString).substring(with: match.range(at: 1))
            }
            guard let id, seen.insert(id).inserted else { continue }
            let text = tag.range(at: 2).location == NSNotFound ? "" : ns.substring(with: tag.range(at: 2))
                .replacingOccurrences(of: #"<[^>]+>"#, with: "", options: .regularExpression)
            let name = [meta["displayName"] as? String, meta["linkName"] as? String, meta["fileName"] as? String, attributes["alt"], text.isEmpty ? nil : entities(text)].compactMap { $0 }.first ?? "file-\(id)"
            files.append(EmbeddedFile(id: id, name: name, path: path, mime: meta["mimeType"] as? String))
        }
        return files
    }
}
