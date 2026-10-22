import XCTest
@testable import BlackboardSync

final class LibraryStoreTests: XCTestCase {
    private var root: URL!
    private var store: LibraryStore!
    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        store = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: root) }
    private func body(_ text: String) throws -> URL {
        let url = root.appendingPathComponent(UUID().uuidString)
        try Data(text.utf8).write(to: url)
        return url
    }
    private func install(_ text: String, fingerprint: String = "v1") async throws -> Activity {
        try await store.install(key: "a", desired: "Term/CSE101 Algorithms/Week 1/notes.pdf", temporary: body(text),
                                fingerprint: fingerprint, etag: "etag", lastModified: nil)
    }

    func testHashHasKnownSHA256AndStateRoundTrips() async throws {
        let activity = try await install("abc")
        let record = await store.record("a")
        XCTAssertEqual(record?.hash, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        XCTAssertEqual(activity.status, .downloaded)
        let restored = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
        let snapshot = await restored.snapshot()
        XCTAssertEqual(snapshot.records["a"], record)
        XCTAssertFalse(try String(contentsOf: root.appendingPathComponent("Support/library-v1.json"), encoding: .utf8).contains("requestPath"))
    }

    func testSecondRunAvoidsDownloadAndMissingFileInvalidatesCache() async throws {
        _ = try await install("original")
        let unchanged = try await store.unchanged(key: "a", fingerprint: "v1")
        XCTAssertTrue(unchanged)
        let changed = try await store.unchanged(key: "a", fingerprint: "v2")
        XCTAssertFalse(changed)
        let nilVersion = try await store.unchanged(key: "a", fingerprint: nil)
        XCTAssertFalse(nilVersion)
        let savedRecord = await store.record("a")
        let record = try XCTUnwrap(savedRecord)
        try FileManager.default.removeItem(at: await store.url(record.relativePath))
        let missing = try await store.unchanged(key: "a", fingerprint: "v1")
        XCTAssertFalse(missing)
    }

    func testModifiedLocalIsPreservedAndNewRemoteSavedBesideIt() async throws {
        let first = try await install("original")
        let path = try XCTUnwrap(first.relativePath)
        let local = try await store.url(path)
        try Data("annotated".utf8).write(to: local)
        let conflict = try await install("remote update", fingerprint: "v2")
        XCTAssertEqual(conflict.status, .conflict)
        XCTAssertEqual(conflict.relativePath, "Term/CSE101 Algorithms/Week 1/notes (2).pdf")
        XCTAssertEqual(try String(contentsOf: local, encoding: .utf8), "annotated")
        let remote = try await store.url(XCTUnwrap(conflict.relativePath))
        XCTAssertEqual(try String(contentsOf: remote, encoding: .utf8), "remote update")
        let second = try await store.unchanged(key: "a", fingerprint: "v2")
        XCTAssertTrue(second)
    }

    func testChangedRemoteReplacesOnlyUnmodifiedFile() async throws {
        let original = try await install("original")
        let changed = try await install("update", fingerprint: "v2")
        XCTAssertEqual(changed.relativePath, original.relativePath)
        XCTAssertEqual(changed.status, .downloaded)
        let url = try await store.url(XCTUnwrap(original.relativePath))
        XCTAssertEqual(try String(contentsOf: url, encoding: .utf8), "update")
    }

    func testIdenticalRemoteBytesNeverReplaceLocalAnnotations() async throws {
        let original = try await install("original")
        let local = try await store.url(XCTUnwrap(original.relativePath))
        try Data("annotated".utf8).write(to: local)
        let identical = try await install("original", fingerprint: "v2")
        XCTAssertEqual(identical.status, .unchanged)
        XCTAssertEqual(try String(contentsOf: local, encoding: .utf8), "annotated")
    }

    func testExistingUntrackedFileIsNeverOverwritten() async throws {
        let first = try await install("first")
        let collision = try await store.install(key: "b", desired: XCTUnwrap(first.relativePath), temporary: body("second"), fingerprint: nil, etag: nil, lastModified: nil)
        XCTAssertNotEqual(first.relativePath, collision.relativePath)
        let url = try await store.url(XCTUnwrap(first.relativePath))
        XCTAssertEqual(try String(contentsOf: url, encoding: .utf8), "first")
    }

    func testPathTraversalAndSymlinksAreRejected() async throws {
        for path in ["../secret", "/absolute", "a/../../b", "a//b", "a/./b", ""] {
            do { _ = try await store.url(path); XCTFail("Accepted \(path)") } catch { XCTAssertTrue(error is SyncFailure) }
        }
        let university = root.appendingPathComponent("Documents/University")
        try FileManager.default.createDirectory(at: university, withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(at: university.appendingPathComponent("escape"), withDestinationURL: root)
        do { _ = try await store.url("escape/secret"); XCTFail("Accepted symlink") } catch { XCTAssertTrue(error is SyncFailure) }
    }

    func testInterruptedStateAndExplicitEmptySelectionSurviveRelaunch() async throws {
        try await store.select([], scope: "account")
        try await store.begin()
        _ = try await install("original")
        let restored = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
        let snapshot = await restored.snapshot()
        XCTAssertTrue(snapshot.interrupted)
        XCTAssertEqual(snapshot.selected["account"], [])
        XCTAssertNotNil(snapshot.records["a"])
    }

    func testCourseAndTermFolderCollisionsAreStableAndAccountScoped() async throws {
        let course = Course(id: "a", name: "CSE101-1 Algorithms", termID: "t", created: nil, code: "CSE101-1")
        let other = Course(id: "b", name: course.name, termID: "t", created: nil, code: course.code)
        let term = Term(id: "t", name: "2026 Fall", start: nil, end: nil, courses: [course,other])
        let a = try await store.courseFolder(course, term: term, scope: "me")
        let b = try await store.courseFolder(other, term: term, scope: "me")
        XCTAssertEqual(a, "2026 Fall/CSE101 Algorithms")
        XCTAssertNotEqual(a,b)
        let again = try await store.courseFolder(course, term: term, scope: "me")
        XCTAssertEqual(a,again)
        let differentAccount = try await store.courseFolder(course, term: term, scope: "other")
        XCTAssertTrue(differentAccount.hasPrefix("2026 Fall (2)/"))
    }

    func testReadableNamingAndByteLimitsPreserveExtension() {
        XCTAssertEqual(MirrorPaths.name("../Week 1: Intro / notes.pdf"), "-Week 1 - Intro - notes.pdf")
        XCTAssertEqual(MirrorPaths.name(".."), "untitled")
        XCTAssertEqual(MirrorPaths.name("A &amp; B.pdf"), "A & B.pdf")
        let long = MirrorPaths.name(String(repeating: "📚", count: 120) + ".pdf")
        XCTAssertLessThanOrEqual(long.utf8.count, 240)
        XCTAssertTrue(long.hasSuffix(".pdf"))
        XCTAssertEqual(MirrorPaths.course(Course(id: "_1_1", name: "İNG101-1 İngilizce I", termID: "t", created: nil)), "İNG101 İngilizce I")
        XCTAssertTrue(MirrorPaths.isMedia("Recording.MP4"))
        XCTAssertTrue(MirrorPaths.isMedia("unknown", mime: "audio/mp4"))
        XCTAssertFalse(MirrorPaths.isMedia("notes.pdf"))
    }

    func testEmbeddedFilesRecognizeClassicUltraMetadataAndInstructions() {
        let html = """
        <a href="/bbcswebdav/xid-123_1">Week 1.pdf</a>
        <img src='/bbcswebdav/xid-123_1' alt='duplicate'>
        <a data-bbfile='{"resourceUrl":"/sessions/a/b/abcdef0123456789abcdef0123456789/file", "viewerUrl":"/bbcswebdav/pid-7-rid-456_1/xid-456_1?signature=FAKE", "displayName":"Slides.pdf", "mimeType":"application/pdf"}'>download</a>
        <a href='https://example.org/external.pdf'>External</a>
        """
        let files = EmbeddedFiles.find(html)
        XCTAssertEqual(files.map(\.id), ["123_1", "456_1"])
        XCTAssertEqual(files.map(\.name), ["Week 1.pdf", "Slides.pdf"])
        guard files.count == 2 else { return }
        XCTAssertTrue(files[1].path.contains("signature=FAKE"))
        XCTAssertEqual(files[1].mime, "application/pdf")
        XCTAssertEqual(EmbeddedFiles.body(["rawText":"<p>Instructions</p>"]), "<p>Instructions</p>")
    }
}
