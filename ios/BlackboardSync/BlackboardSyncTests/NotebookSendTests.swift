import UIKit
import XCTest
@testable import BlackboardSync

final class NotebookSendTests: XCTestCase {
    private let folder = "2026 Spring/CSE101 Algorithms"
    private var root: URL!
    private var ledger: NotebookLedger!
    private var records: [FileRecord] = []
    private var local: [String: LocalFile] = [:]

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        ledger = try NotebookLedger(support: root)
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: root) }

    private func add(_ path: String, hash: String, size: Int64 = 10, onDisk: Bool = true) {
        let relative = folder + "/" + path
        records.removeAll { $0.relativePath == relative }
        records.append(FileRecord(relativePath: relative, hash: hash, updated: Date(), size: size))
        if onDisk { local[relative] = LocalFile(url: URL(fileURLWithPath: "/University/" + relative), size: size) }
    }
    private func courses(folders: [String]? = nil) -> [NotebookCourse] {
        NotebookSend.courses(folders: folders ?? [folder], records: records, local: local, sent: ledger.sent)
    }
    private func course() throws -> NotebookCourse { try XCTUnwrap(courses().first) }
    private func newNames() throws -> [String] { try course().newFiles.map { ($0.path as NSString).lastPathComponent } }
    @discardableResult
    private func finish(activity: String? = "com.google.Notebook.ShareExtension", completed: Bool = true, error: Error? = nil) throws -> Bool {
        try ledger.shareFinished(course(), activity: activity, completed: completed, error: error)
    }

    func testNewFilesFollowTheMacsRules() throws {
        add("Week 1/slides.pdf", hash: "a")
        add("notes.DOCX", hash: "b")
        add("photo.png", hash: "c")
        add("empty.pdf", hash: "d", size: 0)
        add("huge.pdf", hash: "e", size: NotebookSend.maxBytes + 1)
        add("limit.pdf", hash: "f", size: NotebookSend.maxBytes)
        add("deleted-in-files.pdf", hash: "g", onDisk: false)
        XCTAssertEqual(try newNames(), ["limit.pdf", "notes.DOCX", "slides.pdf"])
    }

    func testOnlyTheListedCoursesFilesCount() throws {
        add("a.pdf", hash: "a")
        records.append(FileRecord(relativePath: "2026 Spring/CSE1012 Other/b.pdf", hash: "b", updated: Date(), size: 10))
        local["2026 Spring/CSE1012 Other/b.pdf"] = LocalFile(url: URL(fileURLWithPath: "/b.pdf"), size: 10)
        XCTAssertEqual(try newNames(), ["a.pdf"])
        XCTAssertTrue(courses(folders: []).isEmpty)
    }

    func testCourseWithNothingToSendIsLeftOutAndTitlesFollowTheFolder() throws {
        add("a.pdf", hash: "a")
        let courses = courses(folders: ["2026 Spring/Empty Course", folder])
        XCTAssertEqual(courses.map(\.title), ["CSE101 Algorithms"])
        XCTAssertEqual(NotebookSend.titles(["2025 Fall/CSE101", "2026 Spring/CSE101", "2026 Spring/MAT102"]),
                       ["2025 Fall/CSE101": "CSE101 (2025 Fall)", "2026 Spring/CSE101": "CSE101 (2026 Spring)",
                        "2026 Spring/MAT102": "MAT102"])
    }

    func testCompletedShareMarksSentAndCourseShowsAllSent() throws {
        add("a.pdf", hash: "a")
        add("b.pdf", hash: "b")
        XCTAssertEqual(try course().newFiles.count, 2)
        XCTAssertTrue(try finish())
        let sent = try course()
        XCTAssertEqual(sent.title, "CSE101 Algorithms", "a fully sent course stays listed")
        XCTAssertTrue(sent.newFiles.isEmpty)
    }

    func testCancelledOrFailedShareLeavesFilesListed() throws {
        add("a.pdf", hash: "a")
        XCTAssertFalse(try finish(activity: nil, completed: false))
        XCTAssertFalse(try finish(completed: false), "an extension that was cancelled")
        XCTAssertFalse(try finish(error: SyncFailure(message: "failed")))
        XCTAssertEqual(try newNames(), ["a.pdf"])
        XCTAssertTrue(ledger.sent.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: ledger.url.path), "nothing to record")
    }

    func testApplesOwnDestinationsDoNotCountAsSent() throws {
        add("a.pdf", hash: "a")
        for activity in [UIActivity.ActivityType.mail.rawValue, UIActivity.ActivityType.copyToPasteboard.rawValue,
                         "com.apple.DocumentManagerUICore.SaveToFiles"] {
            XCTAssertFalse(try finish(activity: activity), activity)
        }
        XCTAssertEqual(try newNames(), ["a.pdf"])
        XCTAssertTrue(try finish(activity: "com.apple.UIKit.activity.RemoteOpenInApplication-ByCopy"))
        XCTAssertTrue(try newNames().isEmpty)
    }

    func testSecondCallbackAfterCompletingChangesNothing() throws {
        add("a.pdf", hash: "a")
        let share = try course()
        XCTAssertTrue(try ledger.shareFinished(share, activity: nil, completed: true, error: nil))
        XCTAssertFalse(try ledger.shareFinished(share, activity: nil, completed: false, error: nil))
        XCTAssertTrue(try newNames().isEmpty)
    }

    func testChangedFileIsListedAgainAndSameContentIsNot() throws {
        add("a.pdf", hash: "v1")
        add("b.pdf", hash: "b")
        try finish()
        add("a.pdf", hash: "v1")
        XCTAssertTrue(try newNames().isEmpty, "downloaded again, same content")
        add("a.pdf", hash: "v2")
        XCTAssertEqual(try newNames(), ["a.pdf"])
    }

    func testSameContentUnderAnotherNameGoesOnce() throws {
        add("slides.pdf", hash: "same")
        add("Week 2/slides copy.pdf", hash: "same")
        XCTAssertEqual(try newNames(), ["slides.pdf"], "two copies, one source")
        try finish()
        add("slides (2).pdf", hash: "same")
        XCTAssertTrue(try newNames().isEmpty, "the teacher uploaded the same file again")
    }

    func testFileThatChangesDuringAShareIsListedAgain() throws {
        add("a.pdf", hash: "v1")
        let share = try course()
        add("a.pdf", hash: "v2") // A sync replaced it while the sheet was open.
        _ = try ledger.shareFinished(share, activity: nil, completed: true, error: nil)
        XCTAssertEqual(try newNames(), ["a.pdf"])
    }

    func testSentRecordSurvivesRelaunchAndStaysInItsOwnFile() throws {
        add("a.pdf", hash: "a")
        try finish()
        ledger = try NotebookLedger(support: root)
        XCTAssertTrue(try newNames().isEmpty)
        XCTAssertEqual(ledger.url.lastPathComponent, "notebooklm-sent-v1.json")
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), ["notebooklm-sent-v1.json"])
    }

    func testAFailedSaveClaimsNothing() throws {
        add("a.pdf", hash: "a")
        try FileManager.default.createDirectory(at: ledger.url, withIntermediateDirectories: true)
        XCTAssertThrowsError(try finish())
        XCTAssertEqual(try newNames(), ["a.pdf"])
    }

    func testDamagedRecordIsNotSilentlyEmptied() throws {
        try Data("not json".utf8).write(to: ledger.url)
        XCTAssertThrowsError(try NotebookLedger(support: root), "starting empty would list everything again")
    }

    func testLibraryFindsOnlyPlainFilesOnDisk() async throws {
        let store = try LibraryStore(documents: root.appendingPathComponent("Documents"), support: root.appendingPathComponent("Support"))
        let temporary = root.appendingPathComponent("incoming")
        try Data("abc".utf8).write(to: temporary)
        let activity = try await store.install(key: "k", desired: folder + "/a.pdf", temporary: temporary,
                                               fingerprint: nil, etag: nil, lastModified: nil)
        let path = try XCTUnwrap(activity.relativePath)
        let found = await store.localFiles([path, folder + "/deleted.pdf", "../outside.pdf", folder])
        XCTAssertEqual(Array(found.keys), [path])
        XCTAssertEqual(found[path]?.size, 3)
    }

    func testEveryNotebookStringIsTranslated() {
        for key in ["Send to NotebookLM", "Send", "All sent", "{n} new file", "{n} new files", "{n} course has new files.",
                    "{n} courses have new files.", "No new files to send.", "No course files to send yet.",
                    "Tap Send, choose NotebookLM, then pick the course's notebook. You need the NotebookLM app on this iPad.",
                    "Could not open the share sheet. Try again.",
                    "Sent, but this iPad could not save that. These files may show as new again."] {
            XCTAssertNotNil(L10n.turkish[key], key)
        }
    }
}
