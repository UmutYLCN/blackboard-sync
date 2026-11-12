import Foundation

/// Which first-run screen the app shows (board picks F1 and F2).
public enum FirstRunScreen: Equatable, Sendable {
    /// The normal app.
    case none
    /// F1: a full-screen page in place of the app, until Blackboard is signed in for the first time.
    case fullScreen
    /// F2: a welcome card inside the app, on Home and Courses, while Blackboard is signed out.
    case welcomeCard
}

/// The one stored first-run flag and the decision between F1, F2 and the normal app.
///
/// F1 is due from the app account's sign-in (`begin`) until the first Blackboard sign-in (`finish`).
/// Later, a student signed out of Blackboard sees F2, unless downloaded files are on the iPad: then the
/// normal app stays, so those files remain reachable offline.
public struct FirstRun {
    /// True while F1 is due; absent until the app's first launch with this flag.
    public static let pendingKey = "firstRunPending"
    private let defaults: UserDefaults

    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    /// True while F1 is due.
    public var isPending: Bool { defaults.bool(forKey: Self.pendingKey) }

    /// F1 becomes due.
    public func begin() { defaults.set(true, forKey: Self.pendingKey) }

    /// Blackboard was signed in: F1 is never shown again.
    public func finish() { defaults.set(false, forKey: Self.pendingKey) }

    /// True once, on the first launch of a fresh install, and records that launch. An update from a
    /// version without this flag, where Blackboard was signed in before, is not a fresh install.
    public func firstLaunchOfFreshInstall(signedInBefore: Bool) -> Bool {
        guard defaults.object(forKey: Self.pendingKey) == nil else { return false }
        defaults.set(false, forKey: Self.pendingKey)
        return !signedInBefore
    }

    /// The screen for the app's state. `blackboardAccount` is a session, a stored session or one that
    /// needs signing in again; `downloadedFiles` is the small check that keeps the normal app.
    public static func screen(pending: Bool, blackboardAccount: Bool, downloadedFiles: Bool) -> FirstRunScreen {
        if blackboardAccount || downloadedFiles { return .none }
        return pending ? .fullScreen : .welcomeCard
    }
}
