import SwiftUI
import BlackboardSyncFeatures

// The announcements and due-date pages come from the BlackboardSyncFeatures package. They get
// the app's own signed-in client and course selection; no networking, cookie or Keychain code here.

/// The package's only network surface. The client is looked up per request, so a reconnect's
/// new session is used without rebuilding the pages.
struct ShellHTTP: BlackboardHTTP {
    let client: @MainActor @Sendable () -> BlackboardAPI?

    func getJSON(_ path: String) async throws -> Data {
        guard let api = await client() else { throw BlackboardHTTPError.loginRequired }
        do { return try await api.jsonData(path, label: "Course page") }
        catch let failure as SyncFailure {
            if failure.authRequired { throw BlackboardHTTPError.loginRequired }
            guard let status = failure.status else { throw failure }
            throw (200...299).contains(status) ? BlackboardHTTPError.notJSON : BlackboardHTTPError.status(status)
        }
    }
}

/// The current-term courses the student left ticked on the Courses page.
struct ShellCourses: CourseProvider {
    let courses: @MainActor @Sendable () -> [FeatureCourse]

    func selectedCourses() async throws -> [FeatureCourse] { await courses() }
}

/// The two pages' state for one signed-in account and language.
@MainActor
final class FeatureModels {
    let announcements: AnnouncementsViewModel
    let deadlines: DeadlinesViewModel
    let strings: FeatureStrings

    init(http: any BlackboardHTTP, courses: any CourseProvider, tenant: URL, language: String,
         onSignInRequired: @escaping @MainActor () -> Void) {
        strings = FeatureStrings(FeatureLanguage(code: language))
        announcements = AnnouncementsViewModel(http: http, courses: courses, baseURL: tenant,
                                               strings: strings, onSignInRequired: onSignInRequired)
        deadlines = DeadlinesViewModel(http: http, courses: courses, baseURL: tenant,
                                       strings: strings, onSignInRequired: onSignInRequired)
    }

    /// Reads Blackboard again for the pages already shown once; pages never opened load on appearance.
    func refreshLoaded() async {
        if announcements.phase != .idle {
            while announcements.phase == .loading { try? await Task.sleep(for: .milliseconds(100)) }
            await announcements.refresh()
        }
        if deadlines.phase != .idle {
            while deadlines.phase == .loading { try? await Task.sleep(for: .milliseconds(100)) }
            await deadlines.refresh()
        }
    }
}

extension Color {
    static let appAccent = Color(red: 0.15, green: 0.36, blue: 0.95)
}

extension FeatureTheme {
    /// The app's cards: grouped backgrounds, 18 pt corners and a faint outline.
    static let app = FeatureTheme(accent: .appAccent, pageBackground: Color(uiColor: .systemGroupedBackground),
                                  cardFill: Color(uiColor: .secondarySystemGroupedBackground),
                                  cardBorder: .primary.opacity(0.055), warning: .orange, secondaryText: .secondary,
                                  cornerRadius: 18, spacing: 14)
}
