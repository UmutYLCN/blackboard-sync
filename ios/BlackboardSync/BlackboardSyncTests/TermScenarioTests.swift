import XCTest
@testable import BlackboardSync

/// Which terms are current at schools set up in 28 different ways: the desktop's
/// tests/test_term_scenarios.py run on the iPad's discovery (`BlackboardAPI.courses`).
///
/// `Fixtures/term_scenarios.json` is a copy of the desktop's tests/fixtures/term_scenarios.json: 28
/// synthetic Blackboard setups (no real account's data), each one's API answers, the date of the sync
/// and the terms and courses a student there means by "this term" (`expected_ideal_output`).
/// `current_rule_output` is what version 1.7.0's rule picked; at the first school (İSTÜN) that was
/// right and must stay exactly so.
@MainActor
final class TermScenarioTests: XCTestCase {
    private static let scenarios: [String: [String: Any]] = {
        guard let url = Bundle(for: TermScenarioTests.self).url(forResource: "term_scenarios", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let file = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let list = file["scenarios"] as? [[String: Any]] else { return [:] }
        return Dictionary(uniqueKeysWithValues: list.map { (String(($0["id"] as? String ?? "").prefix(3)), $0) })
    }()
    private static let user = "_900_1"
    /// The first school's checks (research report, part 3): their result must not change at all.
    private static let firstSchool = ["S01", "S02", "S03", "S12", "S15"]
    /// Where the test expects something other than the report's ideal pick, and why (as on desktop).
    private static let expected: [String: [String: [String]]] = [
        // The spring term's start is set to the day registration opens, inside the fall term. The
        // report accepts "Fall 2026 (or both)"; both are kept, since fall is still running.
        "S11": ["ideal_term_names": ["Fall 2026", "Spring 2027"], "ideal_course_ids": ["_13004_1", "_16001_1"],
                "ideal_course_codes": ["CSE303", "CSE304"]],
    ]

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }

    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: root) }

    /// An empty library of its own for one scenario.
    private func newLibrary() throws -> LibraryStore {
        let folder = root.appendingPathComponent(UUID().uuidString)
        return try LibraryStore(documents: folder.appendingPathComponent("Documents"), support: folder.appendingPathComponent("Support"))
    }

    /// The current terms the iPad finds at a scenario's school, on the scenario's date.
    private func discover(_ scenario: [String: Any]) async throws -> [Term] {
        let routes = scenario["api_routes"] as? [String: Any] ?? [:]
        let api = BlackboardAPI(tenant: URL(string: "https://blackboard.example.edu")!, cookies: [], pageLoader: { path in
            let route = (path.split(separator: "?").first.map(String.init) ?? path).removingPercentEncoding ?? path
            guard let answer = routes[route] as? [String: Any] else { throw SyncFailure(message: "Not found", status: 404) }
            return answer
        }, log: { _ in })
        defer { api.cancel() }
        let state = scenario["initial_state"] as? [String: Any] ?? [:]
        let pastTerms = Set((state["past_terms"] as? [String: Any] ?? [:]).keys)
        return try await api.courses(userID: Self.user, now: SyncLogic.date(scenario["now"] as? String)!, pastTerms: pastTerms)
    }

    /// The course code the desktop shows ("CSE303" for "CSE303-1"): the start of the course's folder name.
    private static func code(_ course: Course) -> String {
        String(MirrorPaths.course(course).split(separator: " ").first ?? "")
    }

    /// The desktop's order of a term's courses: by code, then by Blackboard course id.
    private static func ordered(_ terms: [Term]) -> [Course] {
        terms.flatMap { $0.courses.sorted { (code($0), $0.code) < (code($1), $1.code) } }
    }

    func testEveryScenarioIsLoaded() {
        XCTAssertEqual(Self.scenarios.count, 28)
    }

    func testTheCurrentTermsAndCoursesOfEachSetup() async throws {
        for sid in Self.scenarios.keys.sorted() {
            let scenario = Self.scenarios[sid]!
            let expected = Self.expected[sid] ?? scenario["expected_ideal_output"] as? [String: [String]] ?? [:]
            let terms = try await discover(scenario)
            let courses = terms.flatMap(\.courses)
            XCTAssertEqual(terms.map(\.name).sorted(), expected["ideal_term_names"]?.sorted(), sid)
            XCTAssertEqual(courses.map(\.id).sorted(), expected["ideal_course_ids"]?.sorted(), sid)
            XCTAssertEqual(courses.map(Self.code).sorted(), expected["ideal_course_codes"]?.sorted(), sid)
            let store = try newLibrary()
            let scope = sid == "S20" ? "other-school" : "first-school"
            if sid == "S20" {
                // The recorded files are the first school's; the student has moved to another one.
                let state = scenario["initial_state"] as? [String: Any] ?? [:]
                let outputs = state["outputs"] as? [String: [String: Any]] ?? [:]
                let recorded = (outputs.values.first?["path"] as? String).map { ($0 as NSString).deletingLastPathComponent }
                let algorithms = Course(id: "_13004_1", name: "Algorithm Analysis", termID: "_50_1", created: nil, code: "CSE303-1")
                let first = try await store.courseFolder(algorithms, term: Term(id: "_50_1", name: "2026-2027 Güz", start: nil, end: nil,
                                                                                courses: [algorithms]), scope: "first-school")
                XCTAssertEqual(first, recorded, sid)
            }
            var folders: [String] = []
            for term in terms {
                for course in term.courses {
                    let folder = try await store.courseFolder(course, term: term, scope: scope)
                    // Each course in its own term's folder.
                    XCTAssertEqual(folder.split(separator: "/").first.map(String.init), MirrorPaths.name(term.name), sid)
                    folders.append(folder)
                }
            }
            if sid == "S20" { // not in the first school's folder of its course with the same id
                XCTAssertEqual(folders, ["1448 الفصل الدراسي الأول/ARAB101 اللغة العربية"], sid)
            }
        }
    }

    func testTheFirstSchoolGetsExactlyWhatItGotBefore() async throws {
        for sid in Self.firstSchool {
            let scenario = Self.scenarios[sid]!
            let before = scenario["current_rule_output"] as? [String: Any] ?? [:]
            let terms = try await discover(scenario)
            let courses = Self.ordered(terms)
            let store = try newLibrary()
            XCTAssertEqual(terms.map(\.name), before["selected_term_names"] as? [String], sid)
            XCTAssertEqual(courses.map(\.id), before["selected_course_ids"] as? [String], sid)
            var folders: [String] = []
            for course in courses {
                let term = terms.first { $0.courses.contains(course) }!
                folders.append(try await store.courseFolder(course, term: term, scope: "first-school"))
            }
            XCTAssertEqual(folders, before["selected_course_rel_dirs"] as? [String], sid)
        }
    }

    /// S14: the archived term is left out first, so the running term is current, not nothing.
    func testArchivedTermWithANewCourseDoesNotLeaveTheStudentWithNothing() async throws {
        let terms = try await discover(Self.scenarios["S14"]!)
        XCTAssertEqual(terms.map(\.name), ["2026-2027 Güz"])
        XCTAssertEqual(terms.flatMap(\.courses).map(Self.code), ["CSE303"])
    }
}
