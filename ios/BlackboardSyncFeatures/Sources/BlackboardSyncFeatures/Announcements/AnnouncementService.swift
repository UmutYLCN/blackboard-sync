import Foundation

/// Reads announcements the way the desktop's `BlackboardClient.announcements` does.
public struct AnnouncementService: Sendable {
    public let http: any BlackboardHTTP
    public let baseURL: URL
    public let strings: FeatureStrings

    public init(http: any BlackboardHTTP, baseURL: URL, strings: FeatureStrings = FeatureStrings()) {
        self.http = http
        self.baseURL = baseURL
        self.strings = strings
    }

    /// The public endpoint first, then the private one Ultra's own UI uses. When both refuse
    /// with 403 or 404 the course has no announcements to show (no tool or no collection), so
    /// the result is empty; any other failure is thrown for the course.
    public func announcements(for course: FeatureCourse) async throws -> [Announcement] {
        var lastError: Error?
        for root in [APIRoot.publicAPI + "/v1", APIRoot.privateAPI] {
            do {
                let results = try await Paging.all("\(root)/courses/\(course.id)/announcements",
                                                   query: "limit=100", http: http)
                return results.compactMap { Announcement(json: $0, course: course, baseURL: baseURL, strings: strings) }
            } catch BlackboardHTTPError.loginRequired {
                throw BlackboardHTTPError.loginRequired
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                lastError = error
            }
        }
        if case .status(let code)? = lastError as? BlackboardHTTPError, code == 403 || code == 404 {
            return []
        }
        throw lastError ?? BlackboardHTTPError.notJSON
    }

    /// Every selected course's announcements, newest first. Failed courses are reported, not
    /// thrown; an expired session is thrown.
    func load(_ courses: [FeatureCourse]) async throws -> CourseFetchResult<Announcement> {
        try await CourseFetch.run(courses) { try await announcements(for: $0) }
    }
}
