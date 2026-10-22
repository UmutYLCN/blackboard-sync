import Foundation

/// A file an instructor embedded in a body (Ultra links announcement files this way); the
/// desktop's `htmltext.EmbeddedFile`.
public struct EmbeddedFile: Hashable, Sendable {
    /// Stable content-collection id ("911_1") or "upload-<32 hex>" for a temporary upload.
    public let xid: String
    public let name: String
    /// As found in the body; Ultra URLs carry a short-lived signed query.
    public let url: String
    /// From the `data-bbfile` metadata, when the editor wrote one.
    public let mime: String

    public init(xid: String, name: String, url: String, mime: String = "") {
        self.xid = xid
        self.name = name
        self.url = url
        self.mime = mime
    }

    /// Videos and audio are never downloaded by the desktop; they are opened in Blackboard.
    public var isMedia: Bool { Media.isMedia(contentType: mime, names: [name]) }

    /// Where a student opens the file in Blackboard: the permanent `/bbcswebdav/xid-` link,
    /// never the signed URL (`SyncRun.embedded_link`). Nil unless it is an http(s) URL.
    public func link(base: URL) -> URL? {
        let path = xid.hasPrefix("upload-") ? url : "/bbcswebdav/xid-\(xid)"
        return Links.resolve(path, base: base)
    }

    // Files live at /bbcswebdav/xid-<id> or, in Ultra, /bbcswebdav/pid-..-rid-<id>/xid-<id>?<signed query>.
    private static let xidPattern = try! NSRegularExpression(pattern: #"bbcswebdav/(?:[^?#\s"']*/)?xid-(\d+_\d+)"#)
    private static let ridPattern = try! NSRegularExpression(pattern: #"bbcswebdav/[^?#\s"']*rid-(\d+_\d+)"#)
    // Older instruction files can be temporary uploads; only the upload id is stable.
    private static let uploadPattern = try! NSRegularExpression(
        pattern: #"/sessions/[^/]+/[^/]+/([0-9a-f]{32})/"#, options: .caseInsensitive)

    private static func firstGroup(_ pattern: NSRegularExpression, _ text: String) -> String? {
        let range = NSRange(text.startIndex..., in: text)
        guard let match = pattern.firstMatch(in: text, range: range),
              let group = Range(match.range(at: 1), in: text) else { return nil }
        return String(text[group])
    }

    private static func fileID(_ url: String) -> String? {
        firstGroup(xidPattern, url) ?? firstGroup(ridPattern, url)
    }

    /// Content-collection files and explicit uploads linked from instructor HTML, in order,
    /// each once (`find_embedded_files`).
    public static func find(in html: String) -> [EmbeddedFile] {
        guard !html.isEmpty, html.contains("bbcswebdav") || html.contains("/sessions/") else { return [] }
        var found: [EmbeddedFile] = []
        var open: [(url: String, name: String, text: String, fileID: String, mime: String)] = []

        func add(_ url: String, _ name: String, _ fileID: String = "", _ mime: String = "") {
            let id = fileID.isEmpty ? (Self.fileID(url) ?? "") : fileID
            guard !id.isEmpty, !found.contains(where: { $0.xid == id }) else { return }
            found.append(EmbeddedFile(xid: id, name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                                      url: url, mime: mime))
        }

        for token in HTMLTokenizer.tokens(html) {
            switch token {
            case .start(let tag, let attributes):
                var meta: JSONValue?
                if let raw = attributes["data-bbfile"], !raw.isEmpty,
                   case .object(let object)? = try? JSONValue.parse(Data(raw.utf8)), !object.isEmpty {
                    meta = .object(object)
                }
                func first(_ values: [String?]) -> String {
                    values.compactMap { $0 }.first { !$0.isEmpty } ?? ""
                }
                let href = attributes["href"] ?? ""
                var url = first([meta?["resourceUrl"]?.text, href, attributes["src"]])
                let name = first([meta?["displayName"]?.text, meta?["linkName"]?.text, meta?["fileName"]?.text])
                let mime = meta?["mimeType"]?.string ?? ""
                // Prefer a content-collection link when resourceUrl points to a temporary
                // session upload. Ultra often puts the permanent xid in href/viewerUrl.
                let candidates = [url, href, meta?["viewerUrl"]?.text ?? ""]
                url = candidates.first { Self.fileID($0) != nil } ?? url
                let upload = meta == nil ? nil : firstGroup(uploadPattern, url)
                let fileID = upload.map { "upload-\($0)" } ?? ""
                let alt = attributes["alt"] ?? ""
                if tag == "a" {
                    open.append((url, name, "", fileID, mime))
                } else if Self.fileID(url) != nil {
                    add(url, name.isEmpty ? alt : name, "", mime)
                } else if !fileID.isEmpty {
                    add(url, name.isEmpty ? alt : name, fileID, mime)
                }
            case .text(let data):
                if !open.isEmpty { open[open.count - 1].text += data }
            case .end(let tag):
                if tag == "a", let link = open.popLast() {
                    add(link.url, link.name.isEmpty ? link.text : link.name, link.fileID, link.mime)
                }
            }
        }
        for link in open {  // unclosed anchors
            add(link.url, link.name.isEmpty ? link.text : link.name, link.fileID, link.mime)
        }
        return found
    }
}

enum Media {
    /// `api.MEDIA_EXTENSIONS`: videos and audio recordings.
    static let extensions = [
        ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".flv", ".f4v", ".mpg", ".mpeg",
        ".3gp", ".3g2", ".ogv", ".m2ts", ".mts", ".vob", ".asf",
        ".mp3", ".m4a", ".m4b", ".wav", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".aif",
        ".aiff", ".amr", ".mka",
    ]

    /// `api.is_media`.
    static func isMedia(contentType: String, names: [String]) -> Bool {
        let type = contentType.trimmingCharacters(in: .whitespaces).lowercased()
        if type.hasPrefix("video/") || type.hasPrefix("audio/") { return true }
        return names.contains { name in
            let lowered = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return extensions.contains { lowered.hasSuffix($0) }
        }
    }
}

enum Links {
    /// `urljoin(base + "/", path.lstrip("/"))` (`BlackboardClient.url`), kept only when it is
    /// an http(s) URL with a host (`announcements.open_target` refuses anything else).
    static func resolve(_ path: String, base: URL) -> URL? {
        let text = base.absoluteString
        guard let root = URL(string: text.hasSuffix("/") ? text : text + "/"),
              let url = URL(string: String(path.drop { $0 == "/" }), relativeTo: root)?.absoluteURL,
              let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http",
              url.host?.isEmpty == false else { return nil }
        return url
    }
}
