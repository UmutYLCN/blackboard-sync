import Foundation
import Observation

/// The Announcements page's state: every announcement of the selected courses, newest first.
@MainActor
@Observable
public final class AnnouncementsViewModel {
    public private(set) var announcements: [Announcement] = []
    public private(set) var phase: LoadPhase = .idle
    /// Shown above the list: some courses could not be updated, the session expired, or
    /// Blackboard could not be reached. Nil when all is well.
    public private(set) var message: String?
    public var selection: Announcement.ID?

    public let strings: FeatureStrings
    public let timeZone: TimeZone

    @ObservationIgnored private let service: AnnouncementService
    @ObservationIgnored private let courses: any CourseProvider
    @ObservationIgnored private let onSignInRequired: @MainActor () -> Void
    @ObservationIgnored private var cache: [String: [Announcement]] = [:]

    public init(http: any BlackboardHTTP, courses: any CourseProvider, baseURL: URL,
                strings: FeatureStrings = FeatureStrings(), timeZone: TimeZone = .current,
                onSignInRequired: @escaping @MainActor () -> Void = {}) {
        self.service = AnnouncementService(http: http, baseURL: baseURL, strings: strings)
        self.courses = courses
        self.strings = strings
        self.timeZone = timeZone
        self.onSignInRequired = onSignInRequired
    }

    public var selected: Announcement? {
        selection.flatMap { id in announcements.first { $0.id == id } }
    }

    public func detail(for announcement: Announcement) -> String {
        announcement.detail(in: timeZone, strings: strings)
    }

    /// The first time the page appears.
    public func loadIfNeeded() async {
        if phase == .idle { await refresh() }
    }

    /// Reads every selected course again. A course that fails keeps what it showed before,
    /// as the desktop keeps cached rows when a fetch fails.
    public func refresh() async {
        guard phase != .loading else { return }
        phase = .loading
        do {
            let selected = try await courses.selectedCourses()
            let result = try await service.load(selected)
            cache = CourseFetch.merge(cache, result, courses: selected)
            announcements = Announcement.newestFirst(cache.values.flatMap { $0 })
            let nothing = !selected.isEmpty && result.failed.count == selected.count && announcements.isEmpty
            if selected.isEmpty {
                message = strings.noCourses
            } else if nothing {
                message = strings.unreachable
            } else {
                message = result.failed.isEmpty ? nil : strings.announcementsIncomplete
            }
            phase = nothing ? .failed : .loaded
            if let selection, !announcements.contains(where: { $0.id == selection }) { self.selection = nil }
        } catch BlackboardHTTPError.loginRequired {
            phase = .signInRequired
            message = strings.sessionExpired
            onSignInRequired()
        } catch {
            phase = .failed
            message = strings.unreachable
        }
    }
}
