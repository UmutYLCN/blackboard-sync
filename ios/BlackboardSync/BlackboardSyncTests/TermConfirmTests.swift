import XCTest
@testable import BlackboardSync

/// The card before the first download at a new school (`TermConfirm`), on the iPad.
///
/// The first download at a school the library holds nothing of waits for the card, whatever the term:
/// it opens right after the first sign-in there and downloads and saves nothing until Confirm and start.
/// The card keeps the desktop's reasons when the term is not clear (tests/test_term_confirm.py). Confirm
/// keeps the ticked courses and a switched term, and asks once per school. A school with state, such as
/// the first school with its files, never asks.
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

    /// The 28 school setups: the card names the same reasons as the desktop, and opens at each of them for
    /// a new school, also where the term is clear (the first school, İSTÜN, among them).
    func testEachSetupAsksAtANewSchoolWithTheDesktopsReasons() async throws {
        XCTAssertEqual(TermScenarioTests.scenarios.count, 28)
        for sid in TermScenarioTests.scenarios.keys.sorted() {
            let terms = try await TermScenarioTests.discover(TermScenarioTests.scenarios[sid]!)
            XCTAssertEqual(TermConfirm.ambiguity(terms).map(\.rawValue), Self.desktopReasons[sid] ?? [], sid)
            let card = try XCTUnwrap(TermConfirm.card(library: LibraryState(), tenant: tenant, scope: scope,
                                                      detected: terms, listed: terms), sid)
            XCTAssertEqual(card.reasons.map(\.rawValue), Self.desktopReasons[sid] ?? [], sid)
            // Every course found is on the card, under the terms that hold them.
            let draft = TermConfirm.Draft(card: card, selected: Set(terms.flatMap(\.courses).map(\.id)))
            XCTAssertEqual(Set(draft.courses.map(\.id)), Set(terms.flatMap(\.courses).map(\.id)), sid)
            XCTAssertEqual(draft.selection, Set(terms.flatMap(\.courses).map(\.id)), "every course ticked: \(sid)")
            XCTAssertEqual(card.terms, terms.filter { !$0.courses.isEmpty }.map(\.name), sid)
        }
        for sid in TermScenarioTests.firstSchool {
            let terms = try await TermScenarioTests.discover(TermScenarioTests.scenarios[sid]!)
            let card = TermConfirm.card(library: LibraryState(), tenant: tenant, scope: scope, detected: terms, listed: terms)
            XCTAssertEqual(card?.reasons, [], "a clear term still asks at a new school: \(sid)")
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

    /// The one gate: a new school asks, once; a school with state or one confirmed never does, and a
    /// second school asks again.
    func testTheGateAsksOncePerNewSchool() {
        var library = LibraryState()
        XCTAssertTrue(TermConfirm.needsConfirmation(library, tenant: tenant, scope: scope))
        library.records = ["first-school:_1:_2:attachment:_3": record("T/C/a.pdf")] // from before 1.7.1
        XCTAssertFalse(TermConfirm.needsConfirmation(library, tenant: tenant, scope: scope))
        library = LibraryState()
        library.confirmedSchools = [school]
        XCTAssertFalse(TermConfirm.needsConfirmation(library, tenant: tenant, scope: scope), "asked once")
        // The same account's next school: the library holds nothing of it yet.
        library.syncedSchools = [school]
        library.records = [scope + ":_1:_2:attachment:_3": record("T/C/a.pdf")]
        let other = URL(string: "https://bb.other.edu")!
        XCTAssertTrue(TermConfirm.needsConfirmation(library, tenant: other, scope: "scope-b"))
        let fall = term("_fall", "Fall 2026", start: Self.fall, end: Self.fallEnd, courses: ["_1"])
        XCTAssertNil(TermConfirm.card(library: library, tenant: tenant, scope: scope, detected: [fall], listed: [fall]))
        XCTAssertNotNil(TermConfirm.card(library: library, tenant: other, scope: "scope-b", detected: [fall], listed: [fall]))
        // Nothing found: nothing to confirm (Home says no courses were found).
        XCTAssertNil(TermConfirm.card(library: LibraryState(), tenant: tenant, scope: scope,
                                      detected: [term("_fall", "Fall 2026")], listed: []))
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

    private var fallTerm: Term { term("_fall", "Fall 2026", start: Self.fall, end: Self.fallEnd, courses: ["_1", "_2"]) }
    private var springTerm: Term {
        term("_spring", "Spring 2026", start: SyncLogic.date("2026-02-16T00:00:00.000Z"),
             end: SyncLogic.date("2026-06-30T00:00:00.000Z"), courses: ["_7"])
    }
    private var oldTerm: Term {
        term("_old", "Fall 2025", start: SyncLogic.date("2025-09-22T00:00:00.000Z"),
             end: SyncLogic.date("2026-01-31T00:00:00.000Z"), courses: ["_5", "_6"])
    }
    private var noTerm: Term { term("", Term.noTerm, courses: ["_9"]) }

    func testTheCardOffersTheOtherTermsNewestFirst() throws {
        let card = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: [fallTerm, noTerm],
                                                      listed: [oldTerm, fallTerm, term("_empty", "Summer 2026"), springTerm, noTerm]))
        XCTAssertEqual(card.reasons, [])
        XCTAssertEqual(card.detected.map(\.id), ["_fall", ""])
        XCTAssertEqual(card.others.map(\.id), ["_spring", "_old"], "the found, empty and no-term groups are left out")
        XCTAssertEqual(card.terms, ["Fall 2026", Term.noTerm])
        XCTAssertEqual(TermConfirm.optionLabel(springTerm, language: "en"), "Spring 2026 · 1 course")
        XCTAssertEqual(TermConfirm.optionLabel(oldTerm, language: "en"), "Fall 2025 · 2 courses")
        XCTAssertEqual(TermConfirm.optionLabel(oldTerm, language: "tr"), "Fall 2025 · 2 ders")
    }

    func testCardRowsNameTheTermOnlyWhenThereAreSeveral() {
        let algorithms = Course(id: "_1", name: "Algorithms", termID: "T", created: nil, code: "CSE303")
        let seminar = Course(id: "_2", name: "Seminar", termID: "B", created: nil, code: "")
        let one = [Term(id: "T", name: "T", start: nil, end: nil, courses: [algorithms])]
        XCTAssertEqual(TermConfirm.rows(one).map(\.label), ["CSE303 Algorithms"])
        let two = one + [Term(id: "B", name: "B", start: nil, end: nil, courses: [seminar])]
        XCTAssertEqual(TermConfirm.rows(two).map(\.id), ["_1", "_2"])
        XCTAssertEqual(TermConfirm.rows(two).map(\.label), ["CSE303 Algorithms · T", "Seminar · B"])
    }

    func testTheMessageSaysWhetherTheTermIsClear() throws {
        let clear = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: [fallTerm], listed: [fallTerm]))
        XCTAssertEqual(TermConfirm.message(clear, language: "en"), TermConfirm.foundMessage)
        XCTAssertTrue(TermConfirm.message(clear, language: "tr").hasPrefix("Blackboard Sync güncel döneminizi"))
        let undated = [term("_a", "A", courses: ["_1"]), term("_b", "B", courses: ["_2"])]
        let unclear = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: undated, listed: undated))
        XCTAssertEqual(unclear.reasons, [.undated, .unknownName])
        XCTAssertTrue(TermConfirm.message(unclear, language: "en").contains("It found A, B."))
        XCTAssertTrue(TermConfirm.message(unclear, language: "tr").contains("Bulunan dönem(ler): A, B."))
        for key in TermConfirm.strings { XCTAssertNotNil(L10n.turkish[key], key) }
    }

    func testTheCardNamesCoursesAsTheirFolders() throws {
        let algorithms = Course(id: "_13004_1", name: "Algorithm Analysis", termID: "_u", created: nil, code: "CSE303-1")
        let terms = [Term(id: "_u", name: "2026-2027 Güz", start: nil, end: nil, courses: [algorithms])]
        let card = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: terms, listed: terms))
        XCTAssertEqual(card.reasons, [.undated])
        XCTAssertEqual(TermConfirm.Draft(card: card, selected: []).courses,
                       [.init(id: "_13004_1", name: "CSE303 Algorithm Analysis", term: "2026-2027 Güz")])
    }

    /// The ticks start as Courses; unticking counts; Confirm needs one course, and the count's plural
    /// follows the number of courses.
    func testTheTicksStartAsCoursesAndConfirmNeedsOne() throws {
        let card = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: [fallTerm, noTerm], listed: [fallTerm, noTerm]))
        var draft = TermConfirm.Draft(card: card, selected: ["_1", "_2", "_9"])
        XCTAssertEqual(draft.termName, "Fall 2026")
        XCTAssertEqual(draft.selection, ["_1", "_2", "_9"])
        XCTAssertEqual(TermConfirm.selectedLine(draft, language: "en"), "3 of 3 courses selected")
        XCTAssertEqual(TermConfirm.selectedLine(draft, language: "tr"), "3 dersin 3 tanesi seçili")
        draft = TermConfirm.Draft(card: card, selected: ["_2", "_77"]) // one unticked in Courses stays unticked
        XCTAssertEqual(draft.selection, ["_2"])
        XCTAssertEqual(TermConfirm.selectedLine(draft, language: "en"), "1 of 3 courses selected")
        draft.toggle("_2")
        XCTAssertFalse(draft.canConfirm)
        XCTAssertEqual(TermConfirm.selectedLine(draft, language: "en"), "0 of 3 courses selected")
        draft.toggle("_1")
        XCTAssertTrue(draft.canConfirm)
        XCTAssertNil(draft.savedChoice, "the found term needs no choice saved")
        let single = TermConfirm.Draft(card: try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: [springTerm], listed: [])),
                                       selected: ["_7"])
        XCTAssertEqual(TermConfirm.selectedLine(single, language: "en"), "1 of 1 course selected")
    }

    /// Change term: the card shows the chosen term (with the no-term group) with every course ticked;
    /// switching back restores the found term; a term not offered changes nothing.
    func testChangingTheTerm() throws {
        let card = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: [fallTerm, noTerm],
                                                      listed: [fallTerm, springTerm, oldTerm, noTerm]))
        var draft = TermConfirm.Draft(card: card, selected: ["_1"])
        draft.choose("_old")
        XCTAssertEqual(draft.choice, "_old")
        XCTAssertEqual(draft.terms.map(\.id), ["_old", ""])
        XCTAssertEqual(draft.termName, "Fall 2025")
        XCTAssertEqual(draft.selection, ["_5", "_6", "_9"])
        XCTAssertEqual(draft.savedChoice, TermConfirm.TermChoice(detected: ["_fall"], chosen: "_old"))
        draft.toggle("_6")
        draft.choose("_nowhere")
        XCTAssertNil(draft.choice, "a term not offered is the found term")
        XCTAssertEqual(draft.terms.map(\.id), ["_fall", ""])
        XCTAssertEqual(draft.selection, ["_1", "_2", "_9"])
        XCTAssertNil(draft.savedChoice)
    }

    /// A saved choice holds while the app finds the same terms; once Blackboard's current term moves on,
    /// the app's pick is used again.
    func testASavedTermChoiceHoldsUntilTheCurrentTermChanges() {
        let listed = [fallTerm, springTerm, oldTerm, noTerm]
        let choice = TermConfirm.TermChoice(detected: ["_fall"], chosen: "_spring")
        XCTAssertEqual(TermConfirm.apply(nil, detected: [fallTerm, noTerm], listed: listed).map(\.id), ["_fall", ""])
        XCTAssertEqual(TermConfirm.apply(choice, detected: [fallTerm, noTerm], listed: listed).map(\.id), ["_spring", ""])
        let next = term("_next", "Spring 2027", start: SyncLogic.date("2027-02-15T00:00:00.000Z"), courses: ["_8"])
        XCTAssertEqual(TermConfirm.apply(choice, detected: [next], listed: listed + [next]).map(\.id), ["_next"])
        XCTAssertEqual(TermConfirm.apply(choice, detected: [fallTerm], listed: [fallTerm]).map(\.id), ["_fall"],
                       "the chosen term is gone")
    }

    func testConfirmSavesTheTicksTheTermAndTheSchoolAndKeepsOtherSchools() async throws {
        let store = try newStore()
        let other = try XCTUnwrap(TermConfirm.proposal(tenant: URL(string: "https://bb.other.edu")!, detected: [springTerm], listed: []))
        try await TermConfirm.confirm(TermConfirm.Draft(card: other, selected: ["_7"]), scope: "other", store: store)
        let card = try XCTUnwrap(TermConfirm.proposal(tenant: tenant, detected: [fallTerm], listed: [fallTerm, oldTerm]))
        var draft = TermConfirm.Draft(card: card, selected: ["_1", "_2"])
        draft.choose("_old")
        draft.toggle("_5")
        let chosen = try await TermConfirm.confirm(draft, scope: scope, store: store)
        XCTAssertEqual(chosen.terms.map(\.id), ["_old"])
        XCTAssertEqual(chosen.selected, ["_6"])
        let reopened = try await newStore().snapshot() // saved on disk
        XCTAssertEqual(reopened.selected[scope], ["_6"])
        XCTAssertEqual(reopened.terms.map(\.id), ["_old"])
        XCTAssertEqual(reopened.cachedScope, scope)
        XCTAssertEqual(reopened.termChoices, [scope: TermConfirm.TermChoice(detected: ["_fall"], chosen: "_old")])
        XCTAssertEqual(reopened.confirmedSchools, ["bb.other.edu", school])
    }

    // MARK: The app

    private func newModel() async -> AppModel {
        let model = AppModel()
        let documents = root.appendingPathComponent("Documents"), support = root.appendingPathComponent("Support")
        model.libraryFolders = { (documents, support) }
        model.loadSession = { nil }
        await model.start(restoreSession: false)
        return model
    }

    /// The first run's last step at the sample school: the card opens as soon as the courses are found,
    /// before any course page is read; Sync now keeps it; Confirm and start saves the switched term and
    /// ticks, then syncs only the ticked course; finding the courses again keeps the term and asks no more.
    func testTheCardOpensRightAfterSignInAndNothingDownloadsBeforeConfirm() async throws {
        let model = await newModel()
        var requested: [String] = []
        model.install(tenant: SampleSchool.tenant, cookies: [], pageLoader: { path in
            requested.append(path)
            return try await SampleSchool.answer(path)
        })
        model.refreshCourses() // what the first sign-in runs once the school's page closes
        await waitUntil { !model.busy }
        var draft = try XCTUnwrap(model.termConfirm, "the card opens right after sign-in")
        XCTAssertEqual(draft.termName, "Fall 2026")
        XCTAssertEqual(draft.card.reasons, [])
        XCTAssertEqual(draft.courses.map(\.name), ["CSE303 Algorithm Analysis", "CSE301 Database Management",
                                                   "COE305 Software Project Management"])
        XCTAssertEqual(draft.selection.count, 3, "every course ticked")
        XCTAssertEqual(draft.card.others.map(\.name), ["Spring 2026"])
        XCTAssertEqual(model.status, TermConfirm.waiting)
        func readCourses() -> [String] { requested.filter { $0.contains("/contents") } }
        XCTAssertEqual(readCourses(), [], "no course page is read before Confirm")

        model.syncNow()
        await waitUntil { !model.busy }
        XCTAssertNotNil(model.termConfirm, "Sync now keeps asking")
        XCTAssertEqual(readCourses(), [])
        XCTAssertNil(model.library.lastSync)

        model.chooseFirstTerm("_spring")
        model.toggleFirstCourse("_202_1")
        draft = try XCTUnwrap(model.termConfirm)
        XCTAssertEqual(draft.selection, ["_201_1"])
        model.confirmFirstCourses()
        XCTAssertNil(model.termConfirm)
        await waitUntil { !model.busy }
        XCTAssertEqual(model.status, "Up to date")
        XCTAssertEqual(model.terms.map(\.id), ["_spring"])
        XCTAssertEqual(model.selected, ["_201_1"])
        XCTAssertFalse(readCourses().isEmpty)
        XCTAssertTrue(readCourses().allSatisfy { $0.removingPercentEncoding?.contains("/courses/_201_1/") == true },
                      "only the ticked course is read: \(readCourses())")
        let library = try await newStore().snapshot()
        XCTAssertEqual(library.confirmedSchools, [school])
        XCTAssertEqual(library.selected[model.scope], ["_201_1"])
        XCTAssertEqual(library.termChoices?[model.scope]?.chosen, "_spring")

        model.refreshCourses()
        await waitUntil { !model.busy }
        XCTAssertNil(model.termConfirm, "asked once")
        XCTAssertEqual(model.terms.map(\.id), ["_spring"], "the chosen term is kept")
        XCTAssertEqual(model.selected, ["_201_1"])
    }

    /// A sync from the courses saved at the last launch (Sync on app open before any discovery) also
    /// waits for the card.
    func testASyncWithoutDiscoveryAlsoWaits() async throws {
        let model = await newModel()
        var requested: [String] = []
        model.install(tenant: tenant, cookies: [], pageLoader: { path in
            requested.append(path)
            return ["results": [[String: Any]]()]
        })
        model.hasSession = true
        let algorithms = Course(id: "_1_1", name: "CSE303 Algorithm Analysis", termID: "_u", created: nil)
        model.terms = [Term(id: "_u", name: "2026-2027 Güz", start: nil, end: nil, courses: [algorithms])]
        model.selected = ["_1_1"]
        model.syncNow()
        await waitUntil { !model.busy }
        XCTAssertEqual(model.termConfirm?.card.reasons, [.undated])
        XCTAssertEqual(requested, [], "nothing is read or downloaded before Confirm")
        model.confirmFirstCourses()
        await waitUntil { !model.busy }
        XCTAssertEqual(model.status, "Up to date")
        XCTAssertFalse(requested.isEmpty)
    }

    /// A school with state (an existing user's library) never sees the card, at sign-in or on sync.
    func testAnExistingLibraryIsNeverAsked() async throws {
        let store = try newStore()
        try await store.useSchool(SampleSchool.tenant)
        try await store.begin()
        try await store.finish(success: true)
        let model = await newModel()
        model.install(tenant: SampleSchool.tenant, cookies: [], pageLoader: SampleSchool.answer)
        model.refreshCourses()
        await waitUntil { !model.busy }
        XCTAssertNil(model.termConfirm)
        XCTAssertEqual(model.status, "Ready to sync")
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
