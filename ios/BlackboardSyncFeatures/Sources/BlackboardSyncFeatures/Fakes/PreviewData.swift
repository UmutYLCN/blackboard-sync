import Foundation
import SwiftUI

/// Two courses with a few announcements and due dates around now, for SwiftUI previews and
/// for a shell that wants to show the pages before sign-in is wired.
public enum PreviewData {
    public static let baseURL = URL(string: "https://blackboard.example.edu")!

    public static let courses = [
        FeatureCourse(id: "_13004_1", name: "CSE303 Algorithm Analysis"),
        FeatureCourse(id: "_13010_1", name: "MTH201 Linear Algebra"),
    ]

    public static func http(now: Date = Date()) -> FakeBlackboardHTTP {
        func iso(_ offset: TimeInterval) -> String {
            ISO8601DateFormatter().string(from: now.addingTimeInterval(offset))
        }
        let day: TimeInterval = 24 * 3600
        let fake = FakeBlackboardHTTP()
        fake.set("/learn/api/public/v1/courses/_13004_1/announcements?limit=100", json: """
        {"results": [
          {"id": "_n3_1", "title": "Exam rooms &amp; times", "created": "\(iso(-2 * day))",
           "body": {"rawText": "<p>The midterm is on <strong>Friday</strong>.</p><ul><li>Bring ID</li><li>No phones</li></ul><p><a href=\\"https://blackboard.example.edu/bbcswebdav/pid-700-dt-asiobject-rid-911_1/xid-911_1?token=T\\" data-bbfile=\\"{&quot;displayName&quot;:&quot;exam-rooms.pdf&quot;}\\">exam-rooms.pdf</a></p>"}},
          {"id": "_n1_1", "title": "Welcome to CSE303", "created": "\(iso(-20 * day))",
           "body": "<p>Welcome! Office hours are on Tuesdays.</p>"}
        ]}
        """)
        fake.set("/learn/api/public/v1/courses/_13010_1/announcements?limit=100", json: """
        {"results": [{"id": "_m1_1", "title": "Lecture recording", "created": "\(iso(-day))",
          "body": "<p>Today's recording: <a href=\\"/bbcswebdav/xid-77_1\\">lecture-5.mp4</a></p>"}]}
        """)
        fake.set("/learn/api/public/v2/courses/_13004_1/gradebook/columns?limit=200", json: """
        {"results": [
          {"id": "_g1_1", "name": "Homework 3", "grading": {"due": "\(iso(5 * 3600))"}, "contentId": "_c4_1",
           "score": {"possible": 100}},
          {"id": "_g2_1", "name": "Project proposal", "grading": {"due": "\(iso(3 * day))"}, "score": {"possible": 12.5}},
          {"id": "_g0_1", "name": "Homework 2", "grading": {"due": "\(iso(-2 * day))"}}
        ]}
        """)
        fake.set("/learn/api/public/v2/courses/_13010_1/gradebook/columns?limit=200", json: """
        {"results": [{"id": "_g9_1", "displayName": "Quiz 1", "grading": {"due": "\(iso(day + 3600))"}}]}
        """)
        return fake
    }

    @MainActor
    public static func announcements(_ language: FeatureLanguage = .english) -> AnnouncementsViewModel {
        AnnouncementsViewModel(http: http(), courses: StaticCourseProvider(courses), baseURL: baseURL,
                               strings: FeatureStrings(language))
    }

    @MainActor
    public static func deadlines(_ language: FeatureLanguage = .english) -> DeadlinesViewModel {
        DeadlinesViewModel(http: http(), courses: StaticCourseProvider(courses), baseURL: baseURL,
                           strings: FeatureStrings(language))
    }
}

#Preview("Announcements") {
    AnnouncementsView(model: PreviewData.announcements())
}

#Preview("Duyurular") {
    AnnouncementsView(model: PreviewData.announcements(.turkish))
}

#Preview("Calendar") {
    DeadlinesView(model: PreviewData.deadlines())
}

#Preview("Takvim") {
    DeadlinesView(model: PreviewData.deadlines(.turkish))
}
