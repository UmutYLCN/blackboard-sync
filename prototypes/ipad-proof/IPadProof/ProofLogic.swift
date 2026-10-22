import Foundation

struct ProofFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

enum ProofLogic {
    static let noAttachmentHandlers: Set<String> = ["resource/x-bb-externallink", "resource/x-bb-courselink"]

    static func noAttachments(status: Int, data: Data) -> Bool {
        guard [400, 403, 404].contains(status),
              let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let message = object["message"] as? String else { return false }
        return message.lowercased().contains("does not support file attachments")
    }

    static let defaultTenant = "https://blackboard.istun.edu.tr"

    static func tenant(_ text: String) throws -> URL {
        guard let parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme == "https", let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/", let url = parts.url else {
            throw ProofFailure(message: "Enter an HTTPS tenant origin, without a path, query, or credentials.")
        }
        return url
    }

    static func sameOrigin(_ lhs: URL, _ rhs: URL) -> Bool {
        lhs.scheme == rhs.scheme && lhs.host?.lowercased() == rhs.host?.lowercased()
            && (lhs.port ?? 443) == (rhs.port ?? 443)
    }

    // A leading dot is a domain cookie; other cookies are host-only. Match label boundaries.
    static func matchesHost(_ cookie: HTTPCookie, _ host: String) -> Bool {
        let domain = cookie.domain.lowercased()
        let host = host.lowercased()
        if domain.hasPrefix(".") {
            let bare = String(domain.dropFirst())
            return host == bare || host.hasSuffix("." + bare)
        }
        return host == domain
    }

    static func cookies(_ cookies: [HTTPCookie], for url: URL, now: Date = Date()) -> [HTTPCookie] {
        cookies.filter { cookie in
            guard matchesHost(cookie, url.host ?? ""),
                  !cookie.isSecure || url.scheme == "https",
                  cookie.expiresDate.map({ $0 > now }) ?? true else { return false }
            let path = url.path.isEmpty ? "/" : url.path
            return path == cookie.path || (path.hasPrefix(cookie.path)
                && (cookie.path.hasSuffix("/") || path.dropFirst(cookie.path.count).hasPrefix("/")))
        }.sorted { $0.path.count > $1.path.count }
    }

    static func cookieHeader(_ cookies: [HTTPCookie], for url: URL) -> String? {
        let scoped = self.cookies(cookies, for: url)
        guard !scoped.isEmpty else { return nil }
        return scoped.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")
    }

    static func isLogin(_ url: URL?) -> Bool {
        let path = url?.path.lowercased() ?? ""
        return ["/webapps/login", "/auth-saml", "/webapps/bb-auth-provider", "/ultra/logout"]
            .contains { path.contains($0) }
    }

    static func looksLikeHTML(mime: String?, prefix: Data) -> Bool {
        let type = (mime ?? "").lowercased()
        if type.contains("text/html") || type.contains("application/xhtml") { return true }
        let text = String(decoding: prefix.prefix(4096), as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "\u{feff}")))
            .lowercased()
        return text.hasPrefix("<!doctype html") || text.hasPrefix("<html")
            || text.hasPrefix("<head") || text.hasPrefix("<body")
            || (text.hasPrefix("<?xml") && text.contains("<html"))
    }

    static func safeName(_ name: String) -> String {
        let forbidden = CharacterSet.controlCharacters.union(CharacterSet(charactersIn: "/\\:?*\"<>|"))
        let result = String(name.unicodeScalars.map { forbidden.contains($0) ? "_" : String($0) }.joined()
            .trimmingCharacters(in: CharacterSet(charactersIn: ". ")).prefix(100))
        return result.isEmpty ? "unnamed" : result
    }

    // Never log server bodies, raw errors, cookie headers, or URLs (SSO query strings can carry tokens).
    static func safeError(_ error: Error) -> String {
        if let failure = error as? ProofFailure { return failure.message }
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain { return "Network error (NSURLErrorDomain \(ns.code))." }
        if ns.domain == NSOSStatusErrorDomain { return "Keychain error (OSStatus \(ns.code))." }
        return "Operation failed (error code \(ns.code)); response details redacted."
    }

    static func date(_ text: String?) -> Date? {
        guard let text else { return nil }
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return parser.date(from: text) ?? ISO8601DateFormatter().date(from: text)
    }
}

struct Course: Identifiable {
    let id: String
    let name: String
    let termID: String
    let created: Date?
}

struct Term {
    let id: String
    let name: String
    let start: Date?
    let end: Date?
    var courses: [Course]

    static func current(_ terms: [Term], now: Date = Date()) -> [Term] {
        let eligible = terms.filter { !$0.id.isEmpty && !$0.courses.isEmpty }
        let active = eligible.filter {
            guard let start = $0.start, let end = $0.end else { return false }
            return start.addingTimeInterval(-30 * 86400) <= now && now <= end
        }
        if !active.isEmpty { return active }
        let started = eligible.filter { $0.start.map { $0 <= now } ?? false }
        if let latest = started.max(by: { $0.start! < $1.start! }) { return [latest] }
        let newest = eligible.max {
            ($0.courses.compactMap(\.created).max() ?? .distantPast)
                < ($1.courses.compactMap(\.created).max() ?? .distantPast)
        }
        return newest.map { [$0] } ?? []
    }
}

struct Attachment: Identifiable {
    let id: String
    let contentID: String
    let name: String
}

struct ContentItem: Identifiable {
    let id: String
    let title: String
    let hasChildren: Bool
    let handlerID: String?
    var attachments: [Attachment]
    var note: String?
}
