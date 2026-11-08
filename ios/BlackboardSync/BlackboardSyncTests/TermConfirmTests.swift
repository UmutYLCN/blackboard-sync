import XCTest
@testable import BlackboardSync

/// The card before the first download at a school whose current term is not clear (`TermConfirm`), the
/// desktop's tests/test_term_confirm.py on the iPad.
///
/// Only a first sync at a school (no state for it) with an unclear term choice asks; it downloads and saves
/// nothing until the student confirms. Confirm keeps the ticked courses and asks once; Not now saves nothing,
/// so the next sync asks again. A school with state, such as the first school with its files, never asks.
@MainActor
final class TermConfirmTests: XCTestCase {
    private let tenant = URL(string: "https://blackboard.example.edu")!
    private let school = "blackboard.example.edu"
    private let scope = "scope-a"
    private static let fall = SyncLogic.date("2026-09-21T00:00:00.000Z")
    private static let fallEnd = SyncLogic.date("2027-01-31T23:59:59.000Z")

    /// What the desktop's `ambiguity` says for each of the 28 setups of `term_scenarios.json`, on the terms
    /// its discovery picks (computed with src/blackboard_sync/term_confirm.py); the others are clear.
    private static let desktopReasons: [String: [String]] = [
        "S04": ["undated"], "S05": ["undated", "unknown_name"], "S06": ["undated", "unknown_name"],
        "S07": ["several_starts", "unknown_name"], "S08": ["several_starts", "unknown_name"],
        "S09": ["several_starts"], "S11": ["several_starts"], "S16": ["undated", "unknown_name"],
        "S17": ["several_starts"], "S18": ["stale_dates"], "S19": ["undated"], "S24": ["undated"],
        "S27": ["undated"], "S28": ["undated", "unknown_name"],
    ]

    private var root: URL!
    private var saved: [String: Any?] = [:]

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        for key in ["paused", "syncOnOpen"] { saved[key] = UserDefaults.standard.object(forKey: key) }
        UserDefaults.standard.removeObject(forKey: "paused")
        UserDefaults.standard.set(false, forKey: "syncOnOpen")
    }

    override func tearDownWithError() throws {
        for (key, value) in saved { UserDefaults.standard.set(value ?? nil, forKey: key) }
        try? FileManager.default.removeItem(at: root)
    }

    private func newStore() throws -> LibraryStore {
        try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
    }

    private func term(_ id: String, _ name: String, start: Date? = nil, end: Date? = nil,
                      courses: [String] = [], created: [String] = []) -> Term {
        var list = courses.map { Course(id: $0, name: $0, termID: id, created: nil, code: $0) }
        list += created.enumerated().map { Course(id: "\(id)_\($0.offset)", name: "X\($0.offset)", termID: id,
                                                  created: SyncLogic.date($0.element), code: "X\($0.offset)") }
        return Term(id: id, name: name, start: start, end: end, courses: list)
    }

    private func record(_ path: String) -> FileRecord {
        FileRecord(relativePath: path, hash: "h", updated: Date(), size: 1)
    }

    // MARK: When the card is needed

    func testADatedTermWithASeasonNameIsClear() {
        XCTAssertEqual(TermConfirm.ambiguity([term("_fall", "2026-2027 Güz", start: Self.fall, end: Self.fallEnd, courses: ["_c1"])]), [])
        // Turkish and English records of one semester, merged, are still one clear term.
        let both = Term(id: "_fall", name: "2026-2027 Güz", start: Self.fall, end: Self.fallEnd,
                        courses: [Course(id: "_c1", name: "_c1", termID: "_fall", created: nil)],
                        ids: ["_fall", "_fall_en"], names: ["2026-2027 Güz", "2026-2027 Fall"])
        XCTAssertEqual(TermConfirm.ambiguity([both]), [])
    }

    func testUnclearTermsAreNamed() {
        let fall = term("_fall", "2026-2027 Güz", start: Self.fall, end: Self.fallEnd, courses: ["_c1"])
        XCTAssertEqual(TermConfirm.ambiguity([term("_u", "2026-2027 Güz", courses: ["_c2"])]), [.undated])
        let stale = term("_s", "2026-2027 Güz", start: SyncLogic.date("2020-09-01T00:00:00Z"),
                         end: SyncLogic.date("2021-01-31T00:00:00Z"), created: ["2026-08-01T00:00:00Z"])
        XCTAssertEqual(TermConfirm.ambiguity([stale]), [.staleDates])
        let block = term("_b", "2026-2027 Güz", start: SyncLogic.date("2026-11-01T00:00:00Z"), end: Self.fallEnd, courses: ["_c3"])
        XCTAssertEqual(TermConfirm.ambiguity([fall, block]), [.severalStarts])
        let odd = term("_o", "Term 1 (Sept)", start: Self.fall, end: Self.fallEnd, courses: ["_c4"])
        XCTAssertEqual(TermConfirm.ambiguity([odd]), [.unknownName])
        XCTAssertEqual(TermConfirm.Reason.allRawValues, ["undated", "stale_dates", "several_starts", "unknown_name"])
    }

    func testCoursesWithoutATermOrNoCoursesNeedNoCard() {
        XCTAssertEqual(TermConfirm.ambiguity([term("", Term.noTerm, courses: ["_c1"])]), [])
        XCTAssertEqual(TermConfirm.ambiguity([term("_u", "Term")]), []) // nothing to download
        XCTAssertNil(TermConfirm.proposal(tenant: tenant, terms: [term("_u", "Term")]))
    }

    /// The 28 school setups: the iPad names the same reasons as the desktop, and the first school
    /// (İSTÜN) is clear, so it never sees the card.
    func testEachSetupIsAsUnclearAsOnTheDesktop() async throws {
        XCTAssertEqual(TermScenarioTests.scenarios.count, 28)
        for sid in TermScenarioTests.scenarios.keys.sorted() {
            let terms = try await TermScenarioTests.discover(TermScenarioTests.scenarios[sid]!)
            XCTAssertEqual(TermConfirm.ambiguity(terms).map(\.rawValue), Self.desktopReasons[sid] ?? [], sid)
            let card = TermConfirm.card(library: LibraryState(), tenant: tenant, scope: scope, terms: terms)
            XCTAssertEqual(card != nil, Self.desktopReasons[sid] != nil, sid)
            if let card { // every course found is on the card, under the terms that hold them
                XCTAssertEqual(Set(card.courses.map(\.id)), Set(terms.flatMap(\.courses).map(\.id)), sid)
                XCTAssertEqual(card.terms, terms.filter { !$0.courses.isEmpty }.map(\.name), sid)
            }
        }
        for sid in TermScenarioTests.firstSchool {
            let terms = try await TermScenarioTests.discover(TermScenarioTests.scenarios[sid]!)
            XCTAssertNil(TermConfirm.card(library: LibraryState(), tenant: tenant, scope: scope, terms: terms), sid)
        }
    }

    func testSchoolStateIsWhatASyncLeft() {
        func has(_ library: LibraryState) -> Bool { TermConfirm.hasSchoolState(library, school: school, scope: scope) }
        XCTAssertFalse(has(LibraryState()))
        // Finding the courses records the school and its folders before any download: no state yet.
        var found = LibraryState()
        found.school = school
        found.folders = [scope + ":course:_1": "T/C"]
        found.selected = [scope: ["_1"]]
        XCTAssertFalse(has(found))
        // A library from before syncs were recorded per school is the school's in use: the first school's users.
        var legacy = LibraryState()
        legacy.records = ["old-scope:_1:_2:attachment:_3": record("T/C/a.pdf")]
        XCTAssertTrue(has(legacy))
        legacy.records = [:]
        legacy.lastSync = Date()
        XCTAssertTrue(has(legacy))
        // This account's files at this school.
        var mine = LibraryState()
        mine.syncedSchools = []
        mine.records = [scope + ":_1:_2:attachment:_3": record("T/C/a.pdf")]
        XCTAssertTrue(has(mine))
        // Another school's files: this school has none.
        var other = LibraryState()
        other.syncedSchools = ["bb.other.edu"]
        other.records = ["other-scope:_1:_2:attachment:_3": record("T/C/a.pdf")]
        XCTAssertFalse(has(other))
        other.syncedSchools = ["bb.other.edu", school]
        XCTAssertTrue(has(other))
    }

    func testAnExistingSchoolWithItsStateNeverSeesTheCard() async throws {
        let terms = try await TermScenarioTests.discover(TermScenarioTests.scenarios["S04"]!)
        var library = LibraryState()
        XCTAssertNotNil(TermConfirm.card(library: library, tenant: tenant, scope: scope, terms: terms))
        library.records = ["first-school:_1:_2:attachment:_3": record("T/C/a.pdf")] // from before 1.7.1
        XCTAssertNil(TermConfirm.card(library: library, tenant: tenant, scope: scope, terms: terms))
        library = LibraryState()
        library.confirmedSchools = [school]
        XCTAssertNil(TermConfirm.card(library: library, tenant: tenant, scope: scope, terms: terms), "asked once")
    }

    func testABeginningSyncRecordsItsSchool() async throws {
        let store = try newStore()
        try await store.useSchool(tenant)
        try await store.begin()
        try await store.finish(success: false)
        let library = await store.snapshot()
        XCTAssertEqual(library.syncedSchools, [school])
        XCTAssertTrue(TermConfirm.hasSchoolState(library, school: school, scope: scope))
    }

    // MARK: The card

    func testCardRowsNameTheTermOnlyWhenThereAreSeveral() {
        let one = TermConfirm.Card(school: school, reasons: [.undated], terms: ["T"],
                                   courses: [.init(id: "_1", name: "CSE303 Algorithms", term: "T")])
        XCTAssertEqual(TermConfirm.rows(one).map(\.label), ["CSE303 Algorithms"])
        let two = TermConfirm.Card(school: school, reasons: [.undated], terms: ["A", "B"],
                                   courses: [.init(id: "_1", name: "CSE303 Algorithms", term: "A"),
                                             .init(id: "_2", name: "Seminar", term: "B")])
        XCTAssertEqual(TermConfirm.rows(two).map(\.id), ["_1", "_2"])
        XCTAssertEqual(TermConfirm.rows(two).map(\.label), ["CSE303 Algorithms · A", "Seminar · B"])
        XCTAssertTrue(TermConfirm.message(two, language: "en").contains("It found A, B."))
        XCTAssertTrue(TermConfirm.message(two, language: "tr").contains("Bulunan dönem(ler): A, B."))
        for key in [TermConfirm.title, TermConfirm.messageTemplate, TermConfirm.confirmLabel, TermConfirm.notNow, TermConfirm.waiting] {
            XCTAssertNotNil(L10n.turkish[key], key)
        }
    }

    func testTheCardNamesCoursesAsTheirFolders() throws {
        let algorithms = Course(id: "_13004_1", name: "Algorithm Analysis", termID: "_u", created: nil, code: "CSE303-1")
        let card = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, terms: [
            Term(id: "_u", name: "2026-2027 Güz", start: nil, end: nil, courses: [algorithms])]))
        XCTAssertEqual(card, TermConfirm.Card(school: school, reasons: [.undated], terms: ["2026-2027 Güz"],
                                              courses: [.init(id: "_13004_1", name: "CSE303 Algorithm Analysis", term: "2026-2027 Güz")]))
    }

    func testTheCardIsTickedAsCoursesAndConfirmKeepsOtherCourses() {
        let card = TermConfirm.Card(school: school, reasons: [.undated], terms: ["T"],
                                    courses: [.init(id: "_1", name: "A", term: "T"), .init(id: "_2", name: "B", term: "T")])
        // A new school selects every course found; one unticked in Courses before stays unticked.
        XCTAssertEqual(TermConfirm.initialTicks(card, selected: ["_1", "_2"]), ["_1", "_2"])
        XCTAssertEqual(TermConfirm.initialTicks(card, selected: ["_2", "_9"]), ["_2"])
        XCTAssertEqual(TermConfirm.confirmedSelection(card, ticked: ["_1", "_7"], selected: ["_1", "_2", "_9"]), ["_1", "_9"])
    }

    func testConfirmSavesTheTicksAndTheSchoolAndKeepsOtherSchools() async throws {
        let store = try newStore()
        let other = TermConfirm.Card(school: "bb.other.edu", reasons: [.undated], terms: ["T"], courses: [])
        try await TermConfirm.confirm(other, ticked: [], selected: [], scope: "other", store: store)
        let card = TermConfirm.Card(school: school, reasons: [.undated], terms: ["T"],
                                    courses: [.init(id: "_1", name: "A", term: "T"), .init(id: "_2", name: "B", term: "T")])
        let chosen = try await TermConfirm.confirm(card, ticked: ["_1"], selected: ["_1", "_2"], scope: scope, store: store)
        XCTAssertEqual(chosen, ["_1"])
        let reopened = try await newStore().snapshot() // saved on disk
        XCTAssertEqual(reopened.selected[scope], ["_1"])
        XCTAssertEqual(reopened.confirmedSchools, ["bb.other.edu", school])
    }

    // MARK: The app

    /// The whole flow on the app: the card instead of a download; Not now saves nothing and the next sync
    /// asks again; Confirm saves the ticks, syncs only the ticked course, and is asked once.
    func testNothingIsDownloadedBeforeConfirmAndConfirmIsAskedOnce() async throws {
        let model = AppModel()
        let documents = root.appendingPathComponent("Documents"), support = root.appendingPathComponent("Support")
        model.libraryFolders = { (documents, support) }
        model.loadSession = { nil }
        await model.start(restoreSession: false)
        var requested: [String] = []
        model.install(tenant: tenant, cookies: [], pageLoader: { path in
            requested.append(path)
            return ["results": [[String: Any]]()]
        })
        model.hasSession = true
        let algorithms = Course(id: "_1_1", name: "CSE303 Algorithm Analysis", termID: "_u", created: nil)
        let algebra = Course(id: "_2_1", name: "MTH201 Linear Algebra", termID: "_u", created: nil)
        model.terms = [Term(id: "_u", name: "2026-2027 Güz", start: nil, end: nil, courses: [algorithms, algebra])]
        model.selected = ["_1_1", "_2_1"]

        model.syncNow()
        await waitUntil { !model.busy }
        let card = try XCTUnwrap(model.termConfirm)
        XCTAssertEqual(card.reasons, [.undated])
        XCTAssertEqual(TermConfirm.initialTicks(card, selected: model.selected), ["_1_1", "_2_1"], "every course ticked")
        XCTAssertEqual(model.status, TermConfirm.waiting)
        XCTAssertEqual(requested, [], "nothing is read or downloaded before Confirm")
        XCTAssertNil(model.library.lastSync)

        model.notNowFirstCourses()
        XCTAssertNil(model.termConfirm)
        var library = try await newStore().snapshot()
        XCTAssertNil(library.confirmedSchools, "Not now saves nothing")
        XCTAssertNil(library.syncedSchools)
        model.syncNow()
        await waitUntil { !model.busy }
        XCTAssertNotNil(model.termConfirm, "the next sync asks again")
        XCTAssertEqual(requested, [])

        model.confirmFirstCourses(ticked: ["_1_1"])
        XCTAssertNil(model.termConfirm)
        await waitUntil { !model.busy }
        XCTAssertEqual(model.selected, ["_1_1"])
        XCTAssertEqual(model.status, "Up to date")
        XCTAssertFalse(requested.isEmpty)
        XCTAssertTrue(requested.allSatisfy { $0.removingPercentEncoding?.contains("/courses/_1_1/") == true }, "only the ticked course is read: \(requested)")
        library = try await newStore().snapshot()
        XCTAssertEqual(library.confirmedSchools, [school])
        XCTAssertEqual(library.selected[model.scope], ["_1_1"])

        requested = []
        model.syncNow()
        await waitUntil { !model.busy }
        XCTAssertNil(model.termConfirm, "asked once")
        XCTAssertFalse(requested.isEmpty)
    }

    private func waitUntil(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = Date().addingTimeInterval(5)
        while !condition() && Date() < deadline { try? await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(condition(), file: file, line: line)
    }
}

private extension TermConfirm.Reason {
    static var allRawValues: [String] { [Self.undated, .staleDates, .severalStarts, .unknownName].map(\.rawValue) }
}
