import Foundation

/// A grade column's due date (`deadlines.column_deadline`).
///
/// Only the documented `grading.due` timestamp is used. Availability windows, text
/// descriptions and calendar event starts are not deadlines.
public struct Deadline: Identifiable, Hashable, Sendable {
    /// "<course id>:<column id>", the key the desktop's reminders use.
    public let id: String
    public let columnID: String
    public let courseID: String
    public let course: String
    public let title: String
    public let due: Date
    public let contentID: String?
    /// The assignment in Blackboard when the column links content, else the course's grades.
    public let url: URL?
    /// `score.possible`, when the column has one.
    public let points: Double?

    public init(columnID: String, courseID: String, course: String, title: String, due: Date,
                contentID: String?, url: URL?, points: Double?) {
        self.id = "\(courseID):\(columnID)"
        self.columnID = columnID
        self.courseID = courseID
        self.course = course
        self.title = title
        self.due = due
        self.contentID = contentID
        self.url = url
        self.points = points
    }

    /// Nil for a column without an id, hidden from students, or without an explicit due time.
    /// `contentIDs` maps column ids to content found by walking the course outline, for
    /// columns that do not name their content themselves.
    public init?(column: JSONValue, course: FeatureCourse, baseURL: URL, strings: FeatureStrings,
                 contentIDs: [String: String] = [:]) {
        guard let due = Self.parseDue(column["grading"]?["due"]), let columnID = column["id"]?.text,
              column["availability"]?["available"]?.string != "No" else { return nil }
        let contentID = column["contentId"]?.text ?? contentIDs[columnID]
        var path = "/ultra/courses/\(course.id)/grades"
        if let contentID {
            var query = URLComponents()
            query.queryItems = [URLQueryItem(name: "redirectType", value: "nautilus"),
                                URLQueryItem(name: "courseId", value: course.id),
                                URLQueryItem(name: "contentId", value: contentID)]
            path = "/ultra/redirect?" + (query.percentEncodedQuery ?? "")
        }
        let possible = column["score"]?["possible"]?.number
        self.init(columnID: columnID, courseID: course.id, course: course.name,
                  title: column["displayName"]?.text ?? column["name"]?.text ?? strings.untitledWork,
                  due: due, contentID: contentID, url: Links.resolve(path, base: baseURL),
                  points: possible.flatMap { $0.isFinite ? $0 : nil })
    }

    /// Requires an explicit time zone; an ambiguous value is never given a guessed offset.
    public static func parseDue(_ value: JSONValue?) -> Date? {
        guard let text = value?.string, let parsed = ISODate.parse(text), parsed.hasZone else { return nil }
        return parsed.date
    }

    /// "12.5", "100" (`notes._points_text`).
    public var pointsText: String? {
        points.map { String(format: "%g", $0) }
    }
}

/// One course's due dates as last read.
struct DeadlineCourse: Sendable {
    var name: String
    var items: [Deadline]
    /// The last refresh of this course failed; `items` are from an earlier one.
    var unavailable: Bool
}
