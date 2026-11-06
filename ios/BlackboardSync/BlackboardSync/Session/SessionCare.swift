import Foundation

/// How a background sign-in ended. The raw values are the only thing logged; they never hold a secret.
enum SilentOutcome: String {
    case refreshed
    case needsInteraction = "sso-needs-interaction" // the school wants the student
    case timedOut = "timeout"
    case unreachable
    case webFailed = "web-failed"
    case cancelled
    case failed = "error"
}

/// What the session needs next.
enum SessionAction: Equatable { case nothing, keepAlive, refresh }

/// When to look at the session and when another background sign-in may start: the same rules as the
/// Mac's `SessionCare` in src/blackboard_sync/session_refresh.py. Saved, so that a relaunch or a
/// background launch keeps the wait after a failure and the note on Home.
struct SessionCare: Codable, Equatable {
    static let silentTimeout: TimeInterval = 45
    /// iPadOS gives a background refresh about 30 seconds.
    static let backgroundTimeout: TimeInterval = 25
    static let keepAliveEvery: TimeInterval = 25 * 60
    /// Over `keepAliveEvery`: the look before last must not be the last chance to act in time.
    static let expiryMargin: TimeInterval = 30 * 60
    static let failedRetryAfter: TimeInterval = 10 * 60
    /// A session refused right after a sign-in that worked will not be helped by another one.
    static let refreshedRetryAfter: TimeInterval = 60
    /// How long Home's card mentions a background sign-in, as on the Mac.
    static let noteFor: TimeInterval = 2 * 60 * 60
    static let backgroundTaskID = "com.blackboardsync.session-refresh"
    private static let defaultsKey = "sessionCare"

    var enabled = true // the "Automatic re-sign-in" setting
    var checkedAt: Date? // the last keep-alive, account check or finished sync
    var failedAt: Date? // the last background sign-in that did not work
    var refreshedAt: Date?

    static func saved(in defaults: UserDefaults = .standard) -> SessionCare {
        defaults.data(forKey: defaultsKey).flatMap { try? JSONDecoder().decode(SessionCare.self, from: $0) } ?? SessionCare()
    }

    func save(in defaults: UserDefaults = .standard) {
        defaults.set(try? JSONEncoder().encode(self), forKey: Self.defaultsKey)
    }

    func keepAliveDue(_ now: Date) -> Bool {
        // A time in the future means the clock was changed: look anyway.
        enabled && !Self.within(checkedAt, Self.keepAliveEvery, of: now)
    }

    /// Not again right after a failure: a dead sign-on must not keep starting the hidden browser.
    func mayRefresh(_ now: Date) -> Bool {
        enabled && !Self.within(failedAt, Self.failedRetryAfter, of: now)
            && !Self.within(refreshedAt, Self.refreshedRetryAfter, of: now)
    }

    func noteVisible(_ now: Date) -> Bool { Self.within(refreshedAt, Self.noteFor, of: now) }

    func action(now: Date, expiresAt: Date?) -> SessionAction {
        guard enabled else { return .nothing }
        if let expiresAt, expiresAt.timeIntervalSince(now) < Self.expiryMargin, mayRefresh(now) { return .refresh }
        return keepAliveDue(now) ? .keepAlive : .nothing
    }

    mutating func record(_ outcome: SilentOutcome, now: Date) {
        switch outcome {
        case .refreshed: refreshedAt = now; failedAt = nil
        case .cancelled: break // the app left the foreground or the student took over: it says nothing about the sign-on
        default: failedAt = now
        }
    }

    /// When to ask iPadOS for the next background look; it decides the real time, often much later.
    func nextBackgroundCheck(now: Date, expiresAt: Date?) -> Date {
        max(now.addingTimeInterval(Self.keepAliveEvery), expiresAt?.addingTimeInterval(-Self.expiryMargin) ?? .distantPast)
    }

    private static func within(_ start: Date?, _ span: TimeInterval, of now: Date) -> Bool {
        guard let start else { return false }
        return start <= now && now < start.addingTimeInterval(span)
    }

    /// When Blackboard will end this session, if it says. The session cookies carry no expiry of their
    /// own; Blackboard writes one into the value of `BbRouter`, as `expires:<seconds>` in a comma-separated list.
    static func sessionExpiry(_ cookies: [HTTPCookie]) -> Date? {
        for cookie in cookies where cookie.name == "BbRouter" {
            for part in cookie.value.split(separator: ",") {
                let pair = part.split(separator: ":", maxSplits: 1)
                if pair.count == 2, pair[0] == "expires", let seconds = TimeInterval(pair[1]) {
                    return Date(timeIntervalSince1970: seconds)
                }
            }
        }
        return nil
    }

    /// The cookies a sign-in saves: the live ones the school's Blackboard address would receive.
    static func sessionCookies(_ cookies: [HTTPCookie], tenant: URL, now: Date = Date()) -> [HTTPCookie] {
        cookies.filter { SyncLogic.matchesHost($0, tenant.host ?? "") && ($0.expiresDate.map { $0 > now } ?? true) }
    }

    /// The cookies set for Blackboard's own host. A cookie of a parent domain also reaches Blackboard,
    /// but it may be the school's sign-on, so unlike `sessionCookies` this leaves it out.
    static func blackboardOwned(_ cookies: [HTTPCookie], tenant: URL) -> [HTTPCookie] {
        let host = tenant.host?.lowercased() ?? ""
        return cookies.filter { [host, "." + host].contains($0.domain.lowercased()) }
    }
}
