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
    /// The course this one is the merged (cross-listed) parent of, for this student.
    var childID: String? = nil
}

/// A Blackboard term and the courses listed under it. The rule is a port of the desktop
/// `merge_term_aliases`, `choose_current_terms` and their helpers (sync.py, PR #145); each
/// function here carries the name of its Python twin so the two stay easy to compare.
struct Term: Codable, Hashable, Identifiable {
    let id: String
    let name: String
    let start: Date?
    let end: Date?
    var courses: [Course]
    /// Every Blackboard id and name this term goes by: the records of one semester under two
    /// names are merged into one term (`mergeAliases`). Not saved; only choosing terms uses them.
    var ids: [String]
    var names: [String]

    init(id: String, name: String, start: Date?, end: Date?, courses: [Course], ids: [String] = [], names: [String] = []) {
        self.id = id
        self.name = name
        self.start = start
        self.end = end
        self.courses = courses
        self.ids = ids.isEmpty ? (id.isEmpty ? [] : [id]) : ids
        self.names = names.isEmpty ? [name] : names
    }

    private enum CodingKeys: String, CodingKey { case id, name, start, end, courses }

    init(from decoder: Decoder) throws {
        let saved = try decoder.container(keyedBy: CodingKeys.self)
        self.init(id: try saved.decode(String.self, forKey: .id), name: try saved.decode(String.self, forKey: .name),
                  start: try saved.decodeIfPresent(Date.self, forKey: .start),
                  end: try saved.decodeIfPresent(Date.self, forKey: .end),
                  courses: try saved.decode([Course].self, forKey: .courses))
    }

    /// The group of courses Blackboard lists without a term (an empty termId); it is always synced.
    static let noTerm = "No term"
    /// Availability values that mean closed, on a membership, a course or a term.
    static let closed: Set<String> = ["No", "Disabled"]
    /// Courses open before the first lecture, so the next term may take over this early.
    static let leadTime: TimeInterval = 30 * 86400
    /// The age of a term nothing dates: older than any real term.
    static let undated = Date.distantPast
    /// Undated terms whose newest courses were created this close together are one semester's.
    static let undatedCohort: TimeInterval = 45 * 86400

    /// The seasons of one semester in Turkish, English and Arabic: "2025-2026 Bahar" and
    /// "2025-2026 Spring" are the same semester when Blackboard returns them as two term records.
    /// Used only to recognise such a pair and to tell which of two named terms is newer; a term
    /// keeps the name the school gave it. Keys are written as `fold` leaves them.
    static let seasons = ["güz": "fall", "fall": "fall", "autumn": "fall",
                          "bahar": "spring", "spring": "spring", "yaz": "summer", "summer": "summer"]
    /// Semesters named by their place in the academic year ("1448 First Semester",
    /// "الفصل الدراسي الأول 1448", "Semester 1 2026"): the year in such a name is the academic year itself.
    static let ordinalSeasons = [
        "first semester": "fall", "1st semester": "fall", "semester 1": "fall",
        "second semester": "spring", "2nd semester": "spring", "semester 2": "spring",
        "summer semester": "summer",
        "الفصل الدراسي الأول": "fall", "الفصل الأول": "fall", "الفصل الدراسي الاول": "fall", "الفصل الاول": "fall",
        "الفصل الدراسي الثاني": "spring", "الفصل الثاني": "spring",
        "الفصل الدراسي الصيفي": "summer", "الفصل الصيفي": "summer",
    ]
    static let seasonOrder = ["fall": 0, "spring": 1, "summer": 2]

    /// A term's name, as `fold` leaves it: the years first ("2026-2027 Güz", "1448 First Semester")
    /// or the season first ("Fall 2026", "الفصل الدراسي الأول 1448"). Python's `ACADEMIC_TERMS`.
    private static let academicTerms: [String] = {
        let season = Set(seasons.keys).union(ordinalSeasons.keys)
            .sorted { a, b in // the longest first, so "first semester" wins over a shorter word in it
                a.unicodeScalars.count != b.unicodeScalars.count ? a.unicodeScalars.count > b.unicodeScalars.count : a < b
            }
            .map { NSRegularExpression.escapedPattern(for: $0).replacingOccurrences(of: "\\ ", with: " ")
                .replacingOccurrences(of: " ", with: #"\s+"#) }
            .joined(separator: "|")
        // "2026-2027", "2026/27", "1448" or "1448 هـ".
        let years = #"(?<year>\d{4})(?:\s*[-–/]\s*(?<next>\d{4}|\d{2}))?(?:\s*هـ)?"#
        // Words a full official name puts between the years and the season ("2026-2027 Eğitim-Öğretim Yılı Güz Dönemi").
        let yearWords = #"(?:(?:eğitim\s*[-–]?\s*öğretim|akademik|öğretim)\s+yili?|academic\s+year)"#
        let suffix = #"(?:\s+(?:dönemi|dönem|yariyili|yariyil|okulu|term|semester|school))?"#
        let sep = #"\s*[-–:,]?\s*"#
        return ["\(years)\(sep)(?:\(yearWords)\(sep))?(?<season>\(season))\(suffix)",
                "(?<season>\(season))\(suffix)\(sep)(?:\(yearWords)\(sep))?\(years)"]
    }()
    private static let wholeNames = academicTerms.map { try! NSRegularExpression(pattern: #"\A(?:"# + $0 + #")\z"#) }
    private static let namesInText = academicTerms.map { try! NSRegularExpression(pattern: #"(?<!\w)(?:"# + $0 + #")(?!\w)"#) }

    /// Lower case for matching term names; Turkish and English i's (İ I ı i) are one letter.
    static func fold(_ text: String) -> String {
        var text = text.precomposedStringWithCanonicalMapping
        for letter in ["İ", "I", "ı"] { text = text.replacingOccurrences(of: letter, with: "i", options: .literal) }
        return text.lowercased().replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The value of a run of decimal digits in any script ("2026", "١٤٤٨").
    private static func number(_ digits: String) -> Int {
        digits.unicodeScalars.reduce(0) { $0 * 10 + Int($1.properties.numericValue ?? 0) }
    }

    private struct NameMatch {
        let year: String
        let next: String?
        let season: String
    }

    /// The year and season in a term's name: its whole name, or else (`whole` false) whole words in it.
    private static func matchTermName(_ name: String, whole: Bool) -> NameMatch? {
        let text = fold(name)
        let ns = text as NSString
        for regex in whole ? wholeNames : namesInText {
            guard let match = regex.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) else { continue }
            func group(_ name: String) -> String? {
                let range = match.range(withName: name)
                return range.location == NSNotFound ? nil : ns.substring(with: range)
            }
            guard let year = group("year"), let season = group("season") else { continue }
            let next = group("next")
            if let next, next.count == 2, number(next) != (number(year) + 1) % 100 {
                continue // "2026-01" is not an academic year
            }
            return NameMatch(year: year, next: next, season: season)
        }
        return nil
    }

    /// (season, ordinal) of the season words in `match`; ordinal names count the academic year.
    private static func seasonOf(_ match: NameMatch) -> (season: String, ordinal: Bool)? {
        let words = match.season.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        if let season = ordinalSeasons[words] { return (season, true) }
        return seasons[words].map { ($0, false) }
    }

    struct AcademicTerm: Hashable {
        let first: String
        let second: String
        let season: String
    }

    /// The academic year and semester a term's whole name gives; else nil.
    ///
    /// ("2025", "2026", "spring") for "2025-2026 Spring", "2025/2026 Bahar Dönemi" and
    /// "2025-2026 Eğitim-Öğretim Yılı Bahar Dönemi"; ("1448", "", "fall") for "1448 First Semester"
    /// and "الفصل الدراسي الأول 1448"; ("2026", "", "fall") for "Fall 2026".
    /// Only for telling whether two term records are the same semester; it never names a folder.
    static func academicTerm(_ name: String) -> AcademicTerm? {
        guard let match = matchTermName(name, whole: true), let season = seasonOf(match) else { return nil }
        var next = match.next ?? ""
        if next.count == 2 { next = String(match.year.prefix(2)) + next }
        return AcademicTerm(first: match.year, second: next, season: season.season)
    }

    /// An academic year and its semester (fall 0, spring 1, summer 2), in the order they come.
    struct AcademicOrder: Hashable, Comparable {
        let year: Int
        let semester: Int
        static func < (lhs: Self, rhs: Self) -> Bool { (lhs.year, lhs.semester) < (rhs.year, rhs.semester) }
    }

    /// (academic year, semester) a term's name gives anywhere in it, for telling which is newer.
    ///
    /// "2026-2027 Güz", "Fall 2026" and "2026FA - Fall 2026" give (2026, 0); "Spring 2027" gives
    /// (2026, 1), its academic year starting in the fall before; "1448 Second Semester" gives
    /// (1448, 1). Nil when the name holds no year with a season.
    static func academicOrder(_ name: String) -> AcademicOrder? {
        guard let match = matchTermName(name, whole: false), let season = seasonOf(match) else { return nil }
        var year = number(match.year)
        if !(match.next != nil || season.ordinal || season.season == "fall") { year -= 1 }
        return AcademicOrder(year: year, semester: seasonOrder[season.season] ?? 0)
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
                            Course(id: $0.id, name: $0.name, termID: head.id, created: $0.created, code: $0.code, childID: $0.childID)
                        },
                        ids: records.map(\.id), names: records.map(\.name))
        }
    }

    /// The term's dates contain today (it opens a month early).
    static func inDateRange(_ term: Term, now: Date) -> Bool {
        guard !term.id.isEmpty, let start = term.start, let end = term.end else { return false }
        return start.addingTimeInterval(-leadTime) <= now && now <= end
    }

    /// The term ended before any of its courses was created: dates left from the year it was copied from.
    static func hasStaleDates(_ term: Term) -> Bool {
        guard let end = term.end, let first = term.courses.compactMap(\.created).min() else { return false }
        return first > end
    }

    /// The start date the term is dated by: nil when it has none or its dates are stale.
    static func termStart(_ term: Term) -> Date? {
        hasStaleDates(term) ? nil : term.start
    }

    /// When the term started, or else when its newest course was created (`undated` if neither is known).
    static func age(_ term: Term) -> Date {
        termStart(term) ?? term.courses.map { $0.created ?? undated }.max() ?? undated
    }

    /// The current term group of Blackboard's term records: one semester's records are merged,
    /// and a term an older version archived (`pastTerms`) is left out before choosing, unless its
    /// dates contain today. The iPad app never archived a term, so it passes none; the parameter
    /// keeps this a twin of the desktop `Syncer.discover`.
    static func current(_ terms: [Term], now: Date = Date(), pastTerms: Set<String> = []) -> [Term] {
        let candidates = mergeAliases(terms).filter { pastTerms.isDisjoint(with: $0.ids) || inDateRange($0, now: now) }
        return chooseCurrent(candidates, now: now)
    }

    /// (the most recent group, the other terms running beside it) among terms with dates.
    ///
    /// The group is the term(s) that started most recently, or the first upcoming one before any
    /// has started. Once it has ended, a term starting within a month takes over early. Running
    /// beside it: every other term that has started and not ended (a year-long term beside a
    /// semester, a full term beside an 8-week block); while the group itself is still to start,
    /// also those starting within a month.
    private static func datedCurrent(_ dated: [Term], now: Date) -> (group: [Term], running: [Term]) {
        func begins(_ term: Term) -> Date { term.start ?? undated }
        guard let first = dated.map(begins).min() else { return ([], []) }
        var group: [Term]
        let started = dated.filter { begins($0) <= now }
        if let latest = started.map(begins).max() {
            group = started.filter { begins($0) == latest }
            let soon = dated.filter { now < begins($0) && begins($0) <= now.addingTimeInterval(leadTime) }
            if let next = soon.map(begins).min(), group.allSatisfy({ $0.end.map { $0 < now } ?? false }) {
                group = soon.filter { begins($0) == next }
            }
        } else {
            group = dated.filter { begins($0) == first }
        }
        let lead = begins(group[0]) > now ? leadTime : 0
        let inGroup = Set(group.map(\.id))
        let running = dated.filter { term in
            guard !inGroup.contains(term.id), let end = term.end else { return false }
            return begins(term).addingTimeInterval(-lead) <= now && now <= end
        }
        return (group, running)
    }

    /// The undated terms of the semester holding the newest course.
    ///
    /// Their newest courses were created within `undatedCohort` of it, and when its name gives a
    /// year and season, theirs give the same one (or none).
    private static func undatedCohort(_ undated: [Term]) -> [Term] {
        guard let newest = undated.max(by: { age($0) < age($1) }) else { return [] }
        let key = academicOrder(newest.name)
        let from = age(newest).addingTimeInterval(-undatedCohort)
        return undated.filter { term in
            guard age(term) >= from else { return false }
            guard let key else { return true }
            return academicOrder(term.name).map { $0 == key } ?? true
        }
    }

    /// An undated term belongs with the running dated terms `current`.
    ///
    /// Its newest course was created once they opened, and its name does not give another
    /// academic year or season than theirs (a next-term shell or an old summer term that got a
    /// new course stays out).
    private static func joins(_ term: Term, _ current: [Term]) -> Bool {
        guard let opened = current.compactMap(\.start).min(), age(term) >= opened.addingTimeInterval(-leadTime) else { return false }
        guard let key = academicOrder(term.name) else { return true }
        let keys = Set(current.flatMap(\.names).compactMap(academicOrder))
        return keys.isEmpty || keys.contains(key)
    }

    /// With nothing to date the terms by: those whose names give the latest year and season.
    ///
    /// Terms whose names give none come along; when no name gives one, every term.
    private static func latestNamed(_ terms: [Term]) -> [Term] {
        let keys = terms.map { academicOrder($0.name) }
        guard let latest = keys.compactMap({ $0 }).max() else { return terms }
        return zip(terms, keys).filter { $0.1 == nil || $0.1 == latest }.map(\.0)
    }

    /// Pick the term(s) a student means by "this term".
    ///
    /// 1. Terms with dates: the term that started most recently, with every term starting at the
    ///    same moment, plus every other term running now (a year-long term beside a semester,
    ///    sections starting on different days). Once that group has ended, a term starting within
    ///    a month takes over early, since courses open before the first lecture; while it runs
    ///    (exam weeks) it stays. Before any term has started, the first upcoming one. A term that
    ///    ended before any of its courses was created has stale dates (copied from an earlier
    ///    year) and counts as undated.
    /// 2. Terms without dates count from their newest course's creation date, on a clock of their
    ///    own: they never push out a dated term that is running. One joins the running terms when
    ///    its newest course was created once they opened and its name gives no other academic
    ///    year or season. When no dated term is running, the newer of the dated group and the
    ///    undated terms of the newest semester (`undatedCohort`) is current.
    /// 3. A term holding the merged (cross-listed) parent of a current course comes along.
    /// 4. Courses without a term (an empty termId) are always included.
    /// 5. When no term can be dated at all, the terms whose names give the latest academic year
    ///    and season (`latestNamed`); if no name gives one, every course.
    static func chooseCurrent(_ terms: [Term], now: Date) -> [Term] {
        let termless = terms.filter { $0.id.isEmpty }
        let dated = terms.filter { !$0.id.isEmpty && termStart($0) != nil }
        let undatedTerms = terms.filter { !$0.id.isEmpty && termStart($0) == nil }
        let aged = undatedTerms.filter { age($0) != undated }
        let chosen: [Term]
        if dated.isEmpty && aged.isEmpty {
            chosen = latestNamed(undatedTerms)
        } else {
            let (group, running) = datedCurrent(dated, now: now)
            let cohort = undatedCohort(aged)
            if (group + running).contains(where: { inDateRange($0, now: now) }) {
                chosen = group + running + aged.filter { joins($0, group + running) }
            } else { // nothing dated runs now (so nothing runs beside the group)
                let groupAge = group.first?.start.flatMap { $0 <= now ? $0 : nil }
                let cohortAge = cohort.map(age).max()
                if let cohortAge, groupAge.map({ cohortAge > $0 }) ?? true {
                    chosen = cohort
                } else if let cohortAge, cohortAge == groupAge {
                    chosen = group + cohort
                } else {
                    chosen = group
                }
            }
        }
        let current = Set(chosen.flatMap(\.courses).map(\.id))
        var picked = Set(chosen.map(\.id))
        picked.formUnion(terms.filter { term in
            !term.id.isEmpty && term.courses.contains { $0.childID.map(current.contains) ?? false }
        }.map(\.id))
        return terms.filter { !$0.id.isEmpty && picked.contains($0.id) } + termless
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
