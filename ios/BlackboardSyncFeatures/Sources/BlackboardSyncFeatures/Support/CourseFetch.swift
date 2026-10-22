import Foundation

/// What one refresh across the selected courses produced.
struct CourseFetchResult<Item: Sendable>: Sendable {
    var loaded: [String: [Item]] = [:]
    /// Courses whose request failed; their earlier items are kept and the page says so.
    var failed: Set<String> = []
}

enum CourseFetch {
    /// Fetches every course at once. One failing course never hides the others, but an
    /// expired session stops the whole refresh (the desktop's `LoginRequired` is not caught
    /// per course either).
    static func run<Item: Sendable>(
        _ courses: [FeatureCourse],
        _ fetch: @escaping @Sendable (FeatureCourse) async throws -> [Item]
    ) async throws -> CourseFetchResult<Item> {
        try await withThrowingTaskGroup(of: (String, [Item]?).self) { group in
            for course in courses {
                group.addTask {
                    do {
                        return (course.id, try await fetch(course))
                    } catch BlackboardHTTPError.loginRequired {
                        throw BlackboardHTTPError.loginRequired
                    } catch is CancellationError {
                        throw CancellationError()
                    } catch {
                        return (course.id, nil)
                    }
                }
            }
            var result = CourseFetchResult<Item>()
            for try await (id, items) in group {
                if let items { result.loaded[id] = items } else { result.failed.insert(id) }
            }
            return result
        }
    }

    /// The new per-course cache: fresh items, the previous ones for failed courses, and
    /// nothing for courses no longer selected.
    static func merge<Item>(_ previous: [String: [Item]], _ result: CourseFetchResult<Item>,
                            courses: [FeatureCourse]) -> [String: [Item]] {
        var merged: [String: [Item]] = [:]
        for course in courses {
            merged[course.id] = result.loaded[course.id] ?? previous[course.id] ?? []
        }
        return merged
    }
}
