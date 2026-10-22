import Foundation

/// Where a page's last refresh stands.
public enum LoadPhase: Equatable, Sendable {
    /// Nothing asked for yet.
    case idle
    case loading
    case loaded
    /// Blackboard wants the student to sign in again; the shell is told through
    /// `onSignInRequired`. What was shown before stays.
    case signInRequired
    /// The course list itself could not be read, or every course failed with nothing kept.
    case failed
}
