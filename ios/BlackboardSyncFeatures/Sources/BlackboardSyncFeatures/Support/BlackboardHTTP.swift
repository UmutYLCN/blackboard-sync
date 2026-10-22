import Foundation

/// The only network surface this package uses; the app shell implements it.
///
/// `path` is relative to the signed-in Blackboard tenant and may carry a query string,
/// e.g. `/learn/api/public/v1/courses/_1_1/announcements?limit=100`. Paging links that
/// Blackboard returns (`paging.nextPage`) are passed back exactly as received.
///
/// The shell owns cookies, redirects and sign-in. It returns the raw JSON body of a 2xx
/// response and throws `BlackboardHTTPError` for everything else, so this package can tell
/// an expired session from a course that simply has no announcements.
public protocol BlackboardHTTP: Sendable {
    func getJSON(_ path: String) async throws -> Data
}

/// What the shell throws from `BlackboardHTTP.getJSON`. Any other error (offline, timeout)
/// counts as a failed course, the same as a server error.
public enum BlackboardHTTPError: Error, Equatable, Sendable {
    /// HTTP 401, or Blackboard bounced the request to a sign-in page.
    case loginRequired
    /// Any other HTTP status of 400 or more.
    case status(Int)
    /// A 2xx answer that was not JSON (a maintenance page, for instance).
    case notJSON
}

/// A course the student chose in the shell's course list.
public struct FeatureCourse: Identifiable, Hashable, Sendable {
    /// Blackboard's internal id, such as `_13004_1`; used in API paths.
    public let id: String
    /// What the student reads, such as "CSE303 Algorithm Analysis".
    public let name: String

    public init(id: String, name: String) {
        self.id = id
        self.name = name
    }
}

/// The courses whose announcements and due dates are shown: the current-term courses the
/// student left ticked (the desktop's Dersler page leaves unticked ones out).
public protocol CourseProvider: Sendable {
    func selectedCourses() async throws -> [FeatureCourse]
}

/// A fixed list, for tests, previews or a shell that already holds the selection.
public struct StaticCourseProvider: CourseProvider {
    public let courses: [FeatureCourse]

    public init(_ courses: [FeatureCourse]) {
        self.courses = courses
    }

    public func selectedCourses() async throws -> [FeatureCourse] { courses }
}
