import Foundation

/// Reads due dates the way the desktop's sync does (`BlackboardClient.grade_columns`):
/// student-visible column metadata only, never grades, submissions or attempts.
public struct DeadlineService: Sendable {
    public let http: any BlackboardHTTP
    public let baseURL: URL
    public let strings: FeatureStrings

    public init(http: any BlackboardHTTP, baseURL: URL, strings: FeatureStrings = FeatureStrings()) {
        self.http = http
        self.baseURL = baseURL
        self.strings = strings
    }

    /// Every page is read before anything is returned, so a failed second page never
    /// replaces due dates read earlier. A refusal (403) is an error, not "no due dates": the
    /// page then says some courses could not be updated, as the desktop does.
    public func deadlines(for course: FeatureCourse) async throws -> [Deadline] {
        let columns = try await Paging.all("\(APIRoot.publicAPI)/v2/courses/\(course.id)/gradebook/columns",
                                           query: "limit=200", http: http)
        return columns.compactMap { Deadline(column: $0, course: course, baseURL: baseURL, strings: strings) }
    }

    func load(_ courses: [FeatureCourse]) async throws -> CourseFetchResult<Deadline> {
        try await CourseFetch.run(courses) { try await deadlines(for: $0) }
    }
}
