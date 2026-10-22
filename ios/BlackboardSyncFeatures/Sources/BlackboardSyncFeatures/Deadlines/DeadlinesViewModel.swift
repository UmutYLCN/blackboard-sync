import Foundation
import Observation

/// The Calendar page's state: due dates grouped by local day, upcoming before past due.
@MainActor
@Observable
public final class DeadlinesViewModel {
    public private(set) var page: DeadlinePage
    public private(set) var phase: LoadPhase = .idle
    /// The session expired or Blackboard could not be reached; the page's own message
    /// (`page.message`) covers courses that could not be updated.
    public private(set) var error: String?
    public var selection: DeadlineRow.ID?

    public let strings: FeatureStrings
    public let timeZone: TimeZone

    @ObservationIgnored private let service: DeadlineService
    @ObservationIgnored private let courses: any CourseProvider
    @ObservationIgnored private let now: @Sendable () -> Date
    @ObservationIgnored private let onSignInRequired: @MainActor () -> Void
    /// Nil until the first refresh finished: the page then says "Sync to see due dates."
    @ObservationIgnored private var cache: [String: DeadlineCourse]?

    public init(http: any BlackboardHTTP, courses: any CourseProvider, baseURL: URL,
                strings: FeatureStrings = FeatureStrings(), timeZone: TimeZone = .current,
                now: @escaping @Sendable () -> Date = { Date() },
                onSignInRequired: @escaping @MainActor () -> Void = {}) {
        self.service = DeadlineService(http: http, baseURL: baseURL, strings: strings)
        self.courses = courses
        self.strings = strings
        self.timeZone = timeZone
        self.now = now
        self.onSignInRequired = onSignInRequired
        self.page = DeadlineCalendar.page(nil, now: now(), timeZone: timeZone, strings: strings)
    }

    public var selected: DeadlineRow? {
        selection.flatMap { id in page.days.lazy.flatMap(\.rows).first { $0.id == id } }
    }

    /// "1 deadline today · 3 this week", for a Home header.
    public var subtitle: String {
        DeadlineCalendar.subtitle(page, now: now(), timeZone: timeZone, strings: strings)
    }

    /// "Today · October 13, 2026 15:00": when a selected row is due.
    public func dueText(for row: DeadlineRow) -> String {
        let today = LocalTime(now(), timeZone).day
        return "\(DeadlineCalendar.dayTitle(row.day, today: today, strings: strings)) \(row.time)"
    }

    public func loadIfNeeded() async {
        if phase == .idle { await refresh() }
    }

    public func refresh() async {
        guard phase != .loading else { return }
        phase = .loading
        do {
            let selected = try await courses.selectedCourses()
            let result = try await service.load(selected)
            var updated: [String: DeadlineCourse] = [:]
            for course in selected {
                if let items = result.loaded[course.id] {
                    updated[course.id] = DeadlineCourse(name: course.name, items: items, unavailable: false)
                } else {
                    // Keep what an earlier refresh read and say the course is out of date.
                    updated[course.id] = DeadlineCourse(name: course.name, items: cache?[course.id]?.items ?? [],
                                                        unavailable: true)
                }
            }
            cache = updated
            error = selected.isEmpty ? strings.noCourses : nil
            phase = .loaded
        } catch BlackboardHTTPError.loginRequired {
            phase = .signInRequired
            error = strings.sessionExpired
            onSignInRequired()
        } catch {
            phase = .failed
            self.error = strings.unreachable
        }
        rebuild()
    }

    /// Regroups without a request, e.g. when the day changes while the page stays open.
    public func rebuild() {
        page = DeadlineCalendar.page(cache, now: now(), timeZone: timeZone, strings: strings)
        if selection != nil, selected == nil { selection = nil }
    }
}
