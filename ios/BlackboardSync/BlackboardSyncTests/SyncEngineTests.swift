import XCTest
@testable import BlackboardSync

@MainActor
private final class FakeMirrorAPI: MirrorAPI {
    var requests: [String] = []
    var active = 0
    var maxActive = 0
    var fail: Set<String> = []
    var expired = false
    var slow = false
    var body = "remote"
    var listings: [String: [ContentItem]] = [:]
    func contents(courseID: String, parentID: String?) async throws -> [ContentItem] {
        try Task.checkCancellation()
        return listings[parentID ?? "root"] ?? []
    }
    func fetch(path: String, name: String, previous: FileRecord?) async throws -> TransferResult {
        requests.append(name); active += 1; maxActive = max(maxActive,active)
        defer { active -= 1 }
        try await Task.sleep(for: .milliseconds(slow ? 300 : 5))
        if expired { throw SyncFailure(message: "Session expired. Sign in again.", authRequired: true) }
        if fail.contains(name) { throw SyncFailure(message: "Fixture failure") }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try Data(body.utf8).write(to: url)
        return .file(url, etag: "etag", lastModified: nil)
    }
}

final class SyncEngineTests: XCTestCase {
    @MainActor
    func testNestedSelectedCoursesSecondRunAndPerFileRetry() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
        let api = FakeMirrorAPI()
        let course = Course(id: "a", name: "CSE101 Algorithms", termID: "t", created: nil)
        let unselected = Course(id: "b", name: "Not selected", termID: "t", created: nil)
        let term = Term(id: "t", name: "2026 Fall", start: nil, end: nil, courses: [course,unselected])
        api.listings["root"] = [ContentItem(id: "folder", title: "Week 1", hasChildren: true, handlerID: "resource/x-bb-folder", attachments: [])]
        var leaf = ContentItem(id: "leaf", title: "Files", hasChildren: false, handlerID: "resource/x-bb-file", attachments: (0..<8).map { Attachment(id: "\($0)", contentID: "leaf", name: "\($0).pdf") })
        leaf.modified = "v1"
        leaf.attachments.append(Attachment(id: "video", contentID: "leaf", name: "lecture.mp4"))
        leaf.embedded = [EmbeddedFile(id: "123_1", name: "embedded.pdf", path: "/bbcswebdav/xid-123_1", mime: "application/pdf")]
        api.listings["folder"] = [leaf]
        api.fail = ["2.pdf"]
        let engine = SyncEngine(api: api, store: store, scope: "me", update: { _ in })
        let result = try await engine.run(terms: [term], selected: ["a"])
        XCTAssertEqual(result.failed, 1)
        XCTAssertEqual(result.downloaded, 8)
        XCTAssertEqual(result.skipped, 1)
        XCTAssertLessThanOrEqual(api.maxActive, 3)
        XCTAssertGreaterThan(api.maxActive, 1)
        let snapshot = await store.snapshot()
        XCTAssertNil(snapshot.folders["me:course:b"])
        XCTAssertTrue(snapshot.records.values.allSatisfy { $0.relativePath.hasPrefix("2026 Fall/CSE101 Algorithms/Week 1/") })
        XCTAssertFalse(api.requests.contains("lecture.mp4"))
        let failures = snapshot.activities.filter { $0.status == .failed }
        XCTAssertEqual(failures.count, 1)
        api.fail = []; api.requests = []
        let retry = try await SyncEngine(api: api, store: store, scope: "me", update: { _ in }).run(terms: [term], selected: ["a"])
        XCTAssertEqual(retry.downloaded, 1)
        XCTAssertEqual(retry.unchanged, 8)
        XCTAssertEqual(api.requests, ["2.pdf"])
        api.requests = []
        let unchanged = try await SyncEngine(api: api, store: store, scope: "me", update: { _ in }).run(terms: [term], selected: ["a"])
        XCTAssertEqual(unchanged.downloaded, 0)
        XCTAssertTrue(api.requests.isEmpty)
    }

    /// An older version named an English-only "2026-2027 Fall" term "2026-2027 Güz"; its folder stays
    /// in use, nothing is downloaded again or moved, and the saved library loads unchanged.
    @MainActor
    func testExistingGuzFolderStaysInUseWhenTheTermIsNamedFall() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let documents = root.appendingPathComponent("Documents"), support = root.appendingPathComponent("Support")
        let university = documents.appendingPathComponent("University")
        let api = FakeMirrorAPI()
        var item = ContentItem(id: "item", title: "Syllabus", hasChildren: false, handlerID: "resource/x-bb-file",
                               attachments: [Attachment(id: "1", contentID: "item", name: "syllabus.pdf")])
        item.modified = "v1"
        api.listings["root"] = [item]
        let start = SyncLogic.date("2026-09-21T00:00:00Z"), end = SyncLogic.date("2027-01-31T23:59:59Z")
        let algorithms = Course(id: "_13000_1", name: "CSE303 Algorithm Analysis", termID: "_50_1", created: nil)
        let systems = Course(id: "_13777_1", name: "CSE331 Operating Systems", termID: "_50_1", created: nil)

        let old = try LibraryStore(documents: documents, support: support)
        let before = try await SyncEngine(api: api, store: old, scope: "me", update: { _ in })
            .run(terms: [Term(id: "_50_1", name: "2026-2027 Güz", start: start, end: end, courses: [algorithms])], selected: [algorithms.id])
        XCTAssertEqual(before.downloaded, 1)
        let file = university.appendingPathComponent("2026-2027 Güz/CSE303 Algorithm Analysis/syllabus.pdf")
        let modified = try FileManager.default.attributesOfItem(atPath: file.path)[.modificationDate] as? Date
        let stateURL = support.appendingPathComponent("library-v1.json")
        let savedBefore = try Data(contentsOf: stateURL)
        let recordsBefore = await old.snapshot().records

        // The saved library loads unchanged.
        let store = try LibraryStore(documents: documents, support: support)
        XCTAssertEqual(try Data(contentsOf: stateURL), savedBefore)
        let loaded = await store.snapshot()
        XCTAssertEqual(loaded.records, recordsBefore)
        XCTAssertEqual(loaded.folders["me:course:_13000_1"], "2026-2027 Güz/CSE303 Algorithm Analysis")

        // Blackboard now names the term in English, and a new course appears in it.
        let terms = Term.current([Term(id: "_50_1", name: "2026-2027 Fall", start: start, end: end, courses: [algorithms, systems])],
                                 now: SyncLogic.date("2026-10-03T12:00:00Z")!)
        XCTAssertEqual(terms.map(\.name), ["2026-2027 Fall"])
        api.requests = []
        let after = try await SyncEngine(api: api, store: store, scope: "me", update: { _ in })
            .run(terms: terms, selected: [algorithms.id, systems.id])
        XCTAssertEqual(after.downloaded, 1)
        XCTAssertEqual(after.unchanged, 1)
        XCTAssertEqual(api.requests, ["syllabus.pdf"], "only the new course's file is downloaded")
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: university.path), ["2026-2027 Güz"])
        let folder = await store.folder(courseID: systems.id, scope: "me")
        XCTAssertEqual(folder, "2026-2027 Güz/CSE331 Operating Systems")
        XCTAssertEqual(try FileManager.default.attributesOfItem(atPath: file.path)[.modificationDate] as? Date, modified)
        let recordsAfter = await store.snapshot().records
        for (key, record) in recordsBefore { XCTAssertEqual(recordsAfter[key]?.relativePath, record.relativePath) }
    }

    @MainActor
    func testCancellationStopsWindowAndRetryUsesCompletedCheckpoints() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
        let api = FakeMirrorAPI(); api.slow = true
        var leaf = ContentItem(id: "leaf", title: "Files", hasChildren: false, handlerID: nil, attachments: (0..<20).map { Attachment(id: "\($0)", contentID: "leaf", name: "\($0).pdf") })
        leaf.modified = "v1"; api.listings["root"] = [leaf]
        let course = Course(id: "a", name: "Course", termID: "t", created: nil)
        let terms = [Term(id: "t", name: "Term", start: nil, end: nil, courses: [course])]
        let task = Task { try await SyncEngine(api: api, store: store, scope: "me", update: { _ in }).run(terms: terms, selected: ["a"]) }
        try await Task.sleep(for: .milliseconds(400))
        task.cancel()
        do { _ = try await task.value; XCTFail("Should cancel") } catch { XCTAssertTrue(error is CancellationError) }
        XCTAssertEqual(api.active, 0)
        XCTAssertLessThanOrEqual(api.requests.count, 6)
        let before = await store.snapshot()
        XCTAssertGreaterThan(before.records.count, 0)
        api.requests = []; api.slow = false
        _ = try await SyncEngine(api: api, store: store, scope: "me", update: { _ in }).run(terms: terms, selected: ["a"])
        XCTAssertEqual(api.requests.count, 20-before.records.count)
    }

    @MainActor
    func testSessionExpiryPropagatesForReconnectAndStopsQueue() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
        let api = FakeMirrorAPI(); api.expired = true
        api.listings["root"] = [ContentItem(id: "leaf", title: "Files", hasChildren: false, handlerID: nil, attachments: [Attachment(id: "1", contentID: "leaf", name: "notes.pdf")])]
        let course = Course(id: "a", name: "Course", termID: "t", created: nil)
        do {
            _ = try await SyncEngine(api: api, store: store, scope: "me", update: { _ in }).run(terms: [Term(id: "t", name: "Term", start: nil, end: nil, courses: [course])], selected: ["a"])
            XCTFail("Should require reconnect")
        } catch { XCTAssertTrue((error as? SyncFailure)?.authRequired == true) }
        let snapshot = await store.snapshot()
        XCTAssertTrue(snapshot.records.isEmpty)
        XCTAssertNil(snapshot.lastSync)
    }
}
