import XCTest
@testable import BlackboardSync

/// Home's status strip (board pick H1): one state, its lines and at most one button, the next useful action.
final class HomeTests: XCTestCase {
    private var saved: [String: Any?] = [:]

    override func setUp() {
        super.setUp()
        for key in ["paused", "syncOnOpen", "language"] { saved[key] = UserDefaults.standard.object(forKey: key) }
        UserDefaults.standard.removeObject(forKey: "paused")
        UserDefaults.standard.set(false, forKey: "syncOnOpen")
        UserDefaults.standard.set("en", forKey: "language")
    }

    override func tearDown() {
        for (key, value) in saved { UserDefaults.standard.set(value ?? nil, forKey: key) }
        super.tearDown()
    }

    @MainActor
    private func signedIn() -> AppModel {
        let model = AppModel()
        model.hasSession = true
        model.selected = ["course"]
        model.status = "Ready to sync"
        return model
    }

    @MainActor
    func testNeverSignedInShowsOnlyTheWelcomeCard() {
        let model = AppModel()
        XCTAssertNil(HomeStatus.make(model))
        model.errorMessage = "Complete school sign-in, then try again."
        let status = HomeStatus.make(model)
        XCTAssertEqual(status?.tone, .warning)
        XCTAssertEqual(status?.lines, ["Complete school sign-in, then try again."])
        XCTAssertNil(status?.action, "the welcome card has the sign-in button")
    }

    @MainActor
    func testLoadingHasASpinnerAndNoButton() {
        let model = AppModel()
        model.busy = true
        model.status = "Checking your account…"
        let status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Checking your account…")
        XCTAssertEqual(status?.spinner, true)
        XCTAssertNil(status?.action)
    }

    @MainActor
    func testReadyAndEmpty() {
        let model = signedIn()
        var status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Ready to sync")
        XCTAssertEqual(status?.tone, .neutral)
        XCTAssertEqual(status?.action, .syncNow)
        XCTAssertEqual(status?.lines, [], "no sync yet, so no Last synced line")
        model.selected = []
        status = HomeStatus.make(model)
        XCTAssertEqual(status?.lines, ["Select your courses and tap Sync now."])
    }

    @MainActor
    func testUpToDateCountsNewFilesWithPlurals() {
        let model = signedIn()
        model.status = "Up to date"
        let last = Date(timeIntervalSince1970: 1_794_393_780)
        model.library.lastSync = last
        model.progress.downloaded = 1
        var status = HomeStatus.make(model)
        XCTAssertEqual(status?.tone, .good)
        XCTAssertEqual(status?.symbol, "checkmark.icloud.fill")
        XCTAssertEqual(status?.lines, ["Last synced: " + model.dateTime(last) + " · 1 new file"])
        model.progress.downloaded = 3
        XCTAssertEqual(HomeStatus.make(model)?.lines.first?.hasSuffix(" · 3 new files"), true)
        model.progress.downloaded = 0
        XCTAssertEqual(HomeStatus.make(model)?.lines, ["Last synced: " + model.dateTime(last)])
        model.language = "tr"
        model.progress.downloaded = 3
        status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Güncel")
        XCTAssertEqual(status?.lines, ["Son senkronizasyon: " + model.dateTime(last) + " · 3 yeni dosya"])
        XCTAssertTrue(model.dateTime(last).contains("Kas"), "the date follows the app's language")
    }

    @MainActor
    func testSyncingShowsProgressAndCancel() {
        let model = signedIn()
        model.busy = true
        model.syncing = true
        var status = HomeStatus.make(model)
        XCTAssertEqual(status?.lines.first, "Finding files…")
        XCTAssertEqual(status?.spinner, true)
        XCTAssertNil(status?.progress)
        model.progress = SyncProgress(discovered: 40, completed: 12, currentName: "Lecture 4.pptx", discovering: false)
        status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Syncing…")
        XCTAssertEqual(status?.lines.first, "12 / 40 · Lecture 4.pptx")
        XCTAssertEqual(status?.progress ?? 0, 0.3, accuracy: 0.0001)
        XCTAssertEqual(status?.action, .cancel)
        XCTAssertEqual(status?.tone, .busy)
    }

    @MainActor
    func testPausedOffersResumeOnTheStrip() {
        let model = signedIn()
        model.togglePause()
        let status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Paused")
        XCTAssertEqual(status?.action, .resume)
        XCTAssertEqual(status?.tone, .quiet)
        model.togglePause()
        XCTAssertEqual(HomeStatus.make(model)?.action, .syncNow)
    }

    @MainActor
    func testSignInNeededOffersReconnect() {
        let model = signedIn()
        model.hasSession = false
        model.needsSignIn = true
        model.status = "Sign-in needed"
        let status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Sign-in needed")
        XCTAssertEqual(status?.action, .reconnect)
        XCTAssertEqual(status?.tone, .warning)
    }

    @MainActor
    func testFailedSyncOffersRetryWithTheReason() {
        let model = signedIn()
        model.status = "Sync did not finish"
        model.errorMessage = "Incomplete download. Retry sync."
        var status = HomeStatus.make(model)
        XCTAssertEqual(status?.title, "Sync did not finish")
        XCTAssertEqual(status?.lines, ["Incomplete download. Retry sync."])
        XCTAssertEqual(status?.action, .retry)
        model.errorMessage = nil
        model.progress.failed = 2
        XCTAssertEqual(HomeStatus.make(model)?.lines, ["2 errors"])
        model.status = "Cancelled. Sync now to continue."
        status = HomeStatus.make(model)
        XCTAssertEqual(status?.lines, ["Cancelled. Sync now to continue."])
        XCTAssertEqual(status?.action, .retry)
    }

    @MainActor
    func testNoCoursesAndTermConfirmation() {
        let model = signedIn()
        model.status = AppModel.noCoursesFound
        XCTAssertEqual(HomeStatus.make(model)?.title, "No current-term courses found.")
        XCTAssertNil(HomeStatus.make(model)?.action)
        model.status = TermConfirm.waiting
        XCTAssertEqual(HomeStatus.make(model)?.title, TermConfirm.title)
        XCTAssertEqual(HomeStatus.make(model)?.action, .syncNow)
    }

    func testRecentFilesNewestFirstWithCourseAndBadge() {
        let base = Date(timeIntervalSince1970: 1_794_393_780)
        func record(_ path: String, _ minutes: Double) -> FileRecord {
            FileRecord(relativePath: path, hash: "", updated: base.addingTimeInterval(-minutes * 60), size: 1)
        }
        let records = Dictionary(uniqueKeysWithValues: [
            record("Fall 2026/COE305 Software Project Management/SPM Slides-3.pdf", 1),
            record("Fall 2026/CSE301 Database Management/Week 2/Lecture 4.pptx", 2),
            record("Fall 2026/CSE301 Database Management/README", 3),
            record("loose.docx", 4),
            record("Fall 2026/MTH201 Linear Algebra/old.pdf", 50),
        ].map { ($0.relativePath, $0) })
        let files = RecentFile.newest(records)
        XCTAssertEqual(files.map(\.name), ["SPM Slides-3.pdf", "Lecture 4.pptx", "README", "loose.docx"])
        XCTAssertEqual(files.map(\.course), ["COE305", "CSE301", "CSE301", nil])
        XCTAssertEqual(files.map(\.badge), ["PDF", "PPT", nil, "DOC"])
        XCTAssertEqual(RecentFile.newest(records, limit: 2).count, 2)
        XCTAssertTrue(RecentFile.newest([:]).isEmpty)
    }

    func testCourseInitials() {
        XCTAssertEqual(HomeFormat.courseInitials("CSE301 Database Management", language: "en"), "CS")
        XCTAssertEqual(HomeFormat.courseInitials("işletme 101", language: "tr"), "İŞ")
        XCTAssertEqual(HomeFormat.courseInitials("", language: "en"), "?")
    }
}
