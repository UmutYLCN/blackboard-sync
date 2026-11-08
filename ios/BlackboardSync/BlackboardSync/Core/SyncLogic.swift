import Foundation

struct SyncFailure: LocalizedError {
    let message: String
    var authRequired = false
    /// The HTTP status when the server answered but the answer was unusable.
    var status: Int?
    var errorDescription: String? { message }
}

enum SyncLogic {
    static let noAttachmentHandlers: Set<String> = ["resource/x-bb-externallink", "resource/x-bb-courselink"]

    static func noAttachments(status: Int, data: Data) -> Bool {
        guard [400, 403, 404].contains(status),
              let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let message = object["message"] as? String else { return false }
        return message.lowercased().contains("does not support file attachments")
    }

    static let defaultTenant = "https://blackboard.istun.edu.tr"

    static func tenant(_ text: String) throws -> URL {
        if let known = Schools.resolve(text) { return known } // a school's name, abbreviation or web domain
        guard let parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme == "https", let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/", let url = parts.url else {
            throw SyncFailure(message: "Enter an HTTPS tenant origin, without a path, query, or credentials.")
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
        if let failure = error as? SyncFailure { return failure.message }
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

struct Course: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let termID: String
    let created: Date?
    var code: String = ""
}

/// A Blackboard term and the courses listed under it. The rule is a port of the desktop
/// `merge_term_aliases` and `choose_current_terms` (sync.py, PR #140).
struct Term: Codable, Hashable, Identifiable {
    let id: String
    let name: String
    let start: Date?
    let end: Date?
    var courses: [Course]

    /// The group of courses Blackboard lists without a term (an empty termId); it is always synced.
    static let noTerm = "No term"
    /// Courses open before the first lecture, so the next term may take over this early.
    static let leadTime: TimeInterval = 30 * 86400
    /// The age of a term nothing dates: older than any real term.
    static let undated = Date.distantPast

    /// The seasons of one semester in Turkish and English: "2025-2026 Bahar" and "2025-2026 Spring"
    /// are the same semester when Blackboard returns them as two term records. Used only to
    /// recognise such a pair; a term keeps the name the school gave it.
    static let seasons = ["güz": "fall", "fall": "fall", "autumn": "fall",
                          "bahar": "spring", "spring": "spring", "yaz": "summer", "summer": "summer"]

    struct AcademicTerm: Hashable {
        let first: String
        let second: String
        let season: String
    }

    /// ("2025", "2026", "spring") for "2025-2026 Spring", "2025/2026 Bahar Dönemi", ...; else nil.
    /// Only for telling whether two term records are the same semester; it never names a folder.
    static func academicTerm(_ name: String) -> AcademicTerm? {
        let pattern = #"(?i)^(\d{4})\s*[-–/]\s*(\d{4})\s*[-–:]?\s*(\w+)(?:\s+(?:dönemi|yarıyılı|okulu|term|semester|school))?$"#
        let regex = try! NSRegularExpression(pattern: pattern)
        let text = name.trimmingCharacters(in: .whitespacesAndNewlines).precomposedStringWithCanonicalMapping
        guard let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return nil }
        let ns = text as NSString
        guard let season = seasons[ns.substring(with: match.range(at: 3)).lowercased()] else { return nil }
        return AcademicTerm(first: ns.substring(with: match.range(at: 1)), second: ns.substring(with: match.range(at: 2)), season: season)
    }

    private static func datesOverlap(_ a: Term, _ b: Term) -> Bool {
        if let aStart = a.start, let aEnd = a.end, let bStart = b.start, let bEnd = b.end {
            return aStart <= bEnd && bStart <= aEnd
        }
        return true
    }

    /// Merge the records of one semester that Blackboard returns under two names.
    ///
    /// Two records are one term only when their names give the same academic year and semester
    /// ("2025-2026 Bahar" and "2025-2026 Spring") and their dates, when both have them, overlap.
    /// Other terms are never merged, whatever their names. Names are kept as the school wrote
    /// them: the merged term takes the name and id of the record holding most of its courses
    /// (the first listed on a tie), and a term with one record keeps its own name.
    static func mergeAliases(_ terms: [Term]) -> [Term] {
        var groups: [[Term]] = []
        for term in terms {
            let key = term.id.isEmpty ? nil : academicTerm(term.name)
            let index = key.flatMap { key in
                groups.firstIndex { group in
                    !group[0].id.isEmpty && academicTerm(group[0].name) == key && group.allSatisfy { datesOverlap($0, term) }
                }
            }
            if let index { groups[index].append(term) } else { groups.append([term]) }
        }
        return groups.map { group in
            guard group.count > 1 else { return group[0] }
            var main = 0
            for i in group.indices where group[i].courses.count > group[main].courses.count { main = i }
            let head = group[main]
            let records = [head] + group.indices.filter { $0 != main }.map { group[$0] }
            return Term(id: head.id, name: head.name, start: group.compactMap(\.start).min(), end: group.compactMap(\.end).max(),
                        courses: records.flatMap(\.courses).map {
                            Course(id: $0.id, name: $0.name, termID: head.id, created: $0.created, code: $0.code)
                        })
        }
    }

    /// When the term started, or else when its newest course was created (`undated` if neither is known).
    static func age(_ term: Term) -> Date {
        term.start ?? term.courses.map { $0.created ?? undated }.max() ?? undated
    }

    /// The current term group of Blackboard's term records, after merging one semester's records.
    static func current(_ terms: [Term], now: Date = Date()) -> [Term] {
        chooseCurrent(mergeAliases(terms), now: now)
    }

    /// Pick the term(s) a student means by "this term": the top group on Blackboard.
    ///
    /// 1. The term that started most recently; a term without a start date counts from its
    ///    newest course's creation date. Every term starting at that same moment belongs to the
    ///    group (a year-long and a semester term, or two records of one semester).
    /// 2. Once that group has ended, a term starting within a month takes over early, since
    ///    courses open before the first lecture; while it runs (exam weeks) it stays. Before any
    ///    term has started, the first upcoming one.
    /// 3. Courses without a term (an empty termId) are always included.
    /// 4. When no term can be dated at all, every course is current.
    static func chooseCurrent(_ terms: [Term], now: Date) -> [Term] {
        let termless = terms.filter { $0.id.isEmpty }
        let known = terms.filter { !$0.id.isEmpty && age($0) != undated }
        guard !known.isEmpty else { return terms }
        func starting(at moment: Date) -> [Term] { known.filter { age($0) == moment } }
        let started = known.map(age).filter { $0 <= now }
        let upcoming = known.map(age).filter { $0 > now }
        guard let moment = started.max() ?? upcoming.min() else { return termless }
        var group = starting(at: moment)
        if !started.isEmpty, group.allSatisfy({ $0.end.map { $0 < now } ?? false }),
           let soon = upcoming.filter({ $0 <= now.addingTimeInterval(leadTime) }).min() {
            group = starting(at: soon)
        }
        return group + termless
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
    var modified: String?
    var embedded: [EmbeddedFile] = []
    var isFolder: Bool {
        ["resource/x-bb-folder", "resource/x-bb-lesson", "resource/x-bb-module-page", "resource/x-bb-learningmodule"].contains(handlerID ?? "") || (hasChildren && !["resource/x-bb-file", "resource/x-bb-externallink", "resource/x-bb-courselink"].contains(handlerID ?? ""))
    }
}
