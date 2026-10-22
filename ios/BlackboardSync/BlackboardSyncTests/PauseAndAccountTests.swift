import XCTest
@testable import BlackboardSync

final class PauseAndAccountTests: XCTestCase {
    private var saved: [String: Any?] = [:]

    override func setUp() {
        super.setUp()
        for key in ["paused", "syncOnOpen"] { saved[key] = UserDefaults.standard.object(forKey: key) }
        UserDefaults.standard.removeObject(forKey: "paused")
        UserDefaults.standard.set(false, forKey: "syncOnOpen")
    }

    override func tearDown() {
        for (key, value) in saved { UserDefaults.standard.set(value ?? nil, forKey: key) }
        super.tearDown()
    }

    @MainActor
    private func waitUntil(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = Date().addingTimeInterval(5)
        while !condition() && Date() < deadline { try? await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(condition(), file: file, line: line)
    }

    @MainActor
    func testPauseWaitsForSignInAndCanAlwaysBeLifted() {
        let model = AppModel()
        XCTAssertFalse(model.paused)
        XCTAssertFalse(model.canTogglePause)
        model.togglePause()
        XCTAssertFalse(model.paused)
        model.hasSession = true
        XCTAssertTrue(model.canTogglePause)
        model.togglePause()
        XCTAssertTrue(model.paused)
        XCTAssertEqual(model.displayStatus, "Paused")
        XCTAssertEqual(model.text(model.displayStatus), "Paused")
        model.language = "tr"
        XCTAssertEqual(model.text(model.displayStatus), "Duraklatıldı")
        XCTAssertEqual(model.text("Resume syncing"), "Senkronu sürdür")
        model.hasSession = false
        XCTAssertTrue(model.canTogglePause, "a pause already set can be lifted while signed out")
        model.togglePause()
        XCTAssertFalse(model.paused)
        XCTAssertEqual(model.displayStatus, model.status)
    }

    @MainActor
    func testPauseSurvivesRelaunchAndBlocksSync() {
        let model = AppModel()
        model.hasSession = true
        model.togglePause()
        XCTAssertTrue(UserDefaults.standard.bool(forKey: "paused"))
        let relaunched = AppModel()
        XCTAssertTrue(relaunched.paused)
        XCTAssertFalse(relaunched.canSync)
        relaunched.hasSession = true
        relaunched.togglePause()
        XCTAssertFalse(UserDefaults.standard.bool(forKey: "paused"))
    }

    @MainActor
    func testPauseEndsARunningSyncAndShowsPaused() async {
        let model = AppModel()
        model.hasSession = true
        model.run {
            model.syncing = true
            model.status = "Syncing…"
            try await Task.sleep(for: .seconds(30))
        }
        await waitUntil { model.syncing }
        XCTAssertEqual(model.displayStatus, "Syncing…")
        model.togglePause()
        XCTAssertTrue(model.paused)
        await waitUntil { !model.busy }
        XCTAssertFalse(model.syncing)
        XCTAssertEqual(model.displayStatus, "Paused")
        model.togglePause()
        XCTAssertEqual(model.displayStatus, "Cancelled. Sync now to continue.")
    }

    func testInitialsFollowTheMacAndTheAppLanguage() {
        XCTAssertEqual(AppModel.initials("Umut Yalçın", language: "en"), "UY")
        XCTAssertEqual(AppModel.initials("ada lovelace byron", language: "en"), "AL")
        XCTAssertEqual(AppModel.initials("ilker", language: "tr"), "İ")
        XCTAssertEqual(AppModel.initials("ilker", language: "en"), "I")
        XCTAssertEqual(AppModel.initials("", language: "en"), "?")
    }

    func testTopBarAndAccountWordingIsTranslated() {
        for key in ["Pause syncing", "Resume syncing", "Paused", "Syncing is paused. Resume to sync again.",
                    "Signed in as {name}", "Not signed in yet.", "Your session expired; sign in again.",
                    "Open calendar", "Sign out", "Settings"] {
            XCTAssertNotNil(L10n.turkish[key], key)
        }
    }
}
