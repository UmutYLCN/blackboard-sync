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
