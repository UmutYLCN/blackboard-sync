import XCTest

final class NavigationTests: XCTestCase {
    private let signInHint = "Sign in to see announcements and due dates from your selected courses."

    @MainActor
    func testLandscapeNavigationAndPortraitLayout() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-language", "en"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 20))
        capture("Home-landscape")
        // The Mac's top bar: Pause waits for the first sign-in; the account sits at the right, not in the sidebar.
        let pause = app.buttons["toolbar.pause"]
        XCTAssertTrue(pause.waitForExistence(timeout: 5))
        XCTAssertEqual(pause.label, "Pause syncing")
        XCTAssertFalse(pause.isEnabled)
        app.buttons["toolbar.account"].tap()
        XCTAssertTrue(app.buttons["Not signed in yet."].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["Not signed in yet."].isEnabled)
        XCTAssertTrue(app.buttons["Sign in to Blackboard"].exists)
        capture("Account-menu")
        // Settings has its own circle beside the account, so the menu no longer repeats it.
        XCTAssertFalse(app.collectionViews.buttons["Settings"].exists)
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.6, dy: 0.85)).tap()
        XCTAssertTrue(app.buttons["Sign in to Blackboard"].waitForNonExistence(timeout: 5) || !app.collectionViews.buttons["Sign in to Blackboard"].exists)
        app.buttons["toolbar.settings"].tap()
        XCTAssertTrue(app.staticTexts["About & privacy"].waitForExistence(timeout: 5) || app.staticTexts["Account"].exists)
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["Done"].waitForNonExistence(timeout: 5))
        app.descendants(matching: .any)["sidebar.announcements"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts[signInHint].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Your course files start here."].exists)
        capture("Announcements-signed-out")
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts[signInHint].waitForExistence(timeout: 5))
        capture("Calendar-signed-out")
        app.buttons["toolbar.settings"].tap()
        XCTAssertTrue(app.staticTexts["About & privacy"].exists || app.staticTexts["Account"].exists)
        for item in ["Automatic background sync", "Connect Google Calendar", "Choose another folder", "Notes PDFs"] {
            XCTAssertFalse(app.buttons[item].exists, item)
        }
        app.buttons["Done"].tap()
        app.staticTexts["Courses"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["No current-term courses found."].waitForExistence(timeout: 5))
        app.staticTexts["Open folder"].firstMatch.tap()
        // Empty on a fresh simulator; a simulator with files from a run by hand lists them instead.
        XCTAssertTrue(app.staticTexts["No downloaded files yet."].waitForExistence(timeout: 5)
                      || app.staticTexts["Also in Files → On My iPad → Blackboard Sync → University"].exists)
        capture("Library-landscape")
        XCUIDevice.shared.orientation = .portrait
        capture("Library-portrait")
        app.terminate()
    }

    @MainActor
    func testTurkishOnboardingAndFeaturePages() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-language", "tr"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.staticTexts["Ders dosyalarınız burada başlayacak."].waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons["toolbar.pause"].label, "Senkronu duraklat")
        capture("Home-Turkish-landscape")
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Seçili derslerinizin duyurularını ve teslim tarihlerini görmek için giriş yapın."].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Takvim"].exists)
        capture("Calendar-Turkish-signed-out")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    @MainActor
    func testAnnouncementsAndCalendarWithSampleBlackboard() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "-language", "en"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.staticTexts["Exam rooms & times"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Homework 3"].waitForExistence(timeout: 5))
        capture("Home-sample-landscape")
        app.buttons["Open calendar"].tap()
        XCTAssertTrue(app.staticTexts["Past due"].waitForExistence(timeout: 5))
        app.descendants(matching: .any)["sidebar.announcements"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Every announcement from your selected courses."].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Select an announcement"].exists)
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Exam rooms'")).firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Files in this announcement"].waitForExistence(timeout: 5))
        capture("Announcements-sample-landscape")
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Upcoming"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Past due"].exists)
        capture("Calendar-sample-landscape")
        XCUIDevice.shared.orientation = .portrait
        capture("Calendar-sample-portrait")
        app.terminate()
    }

    @MainActor
    func testTurkishSamplePages() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "-language", "tr"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.waitForExistence(timeout: 20)
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Yaklaşan teslimler"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Tarihi geçenler"].exists)
        capture("Calendar-sample-Turkish")
        app.descendants(matching: .any)["sidebar.announcements"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Seçili derslerinizdeki tüm duyurular."].waitForExistence(timeout: 5))
        capture("Announcements-sample-Turkish")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    /// The top bar (board pick T1) on every page, pushed folder pages included: the title and three
    /// equal 44 pt targets on one centre line, the targets touching, the last circle 24 pt from the edge.
    @MainActor
    func testTopBarOnEveryPage() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "-language", "en"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.buttons["toolbar.settings"].waitForExistence(timeout: 20))
        let pages: [(String, XCUIElement)] = [
            ("Home", app.staticTexts["Home"].firstMatch),
            ("Sync activity", app.staticTexts["Sync activity"].firstMatch),
            ("Announcements", app.descendants(matching: .any)["sidebar.announcements"].firstMatch),
            ("Courses", app.staticTexts["Courses"].firstMatch),
            ("Calendar", app.descendants(matching: .any)["sidebar.calendar"].firstMatch),
            ("University", app.descendants(matching: .any)["sidebar.folder"].firstMatch),
        ]
        for (title, row) in pages {
            row.tap()
            assertTopBar(app, title: title)
            capture("TopBar-\(title)-landscape")
        }
        // A folder inside the file browser keeps the bar, with Back in front of the title.
        let folder = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Fall'")).firstMatch
        if folder.waitForExistence(timeout: 3) {
            let name = folder.label
            folder.tap()
            XCTAssertTrue(app.buttons["toolbar.back"].waitForExistence(timeout: 5))
            assertTopBar(app, title: name)
            capture("TopBar-pushed-folder-landscape")
            XCUIDevice.shared.orientation = .portrait
            assertTopBar(app, title: name)
            capture("TopBar-pushed-folder-portrait")
            app.buttons["toolbar.back"].tap()
            XCTAssertTrue(app.buttons["toolbar.back"].waitForNonExistence(timeout: 5))
        }
        XCUIDevice.shared.orientation = .portrait
        app.descendants(matching: .any)["sidebar.folder"].firstMatch.tap()
        assertTopBar(app, title: "University")
        XCTAssertTrue(app.buttons["toolbar.sidebar"].exists)
        capture("TopBar-University-portrait")
        // The sidebar button hides the sidebar; then a swipe from the screen's left edge goes back from a
        // folder although the system bar is hidden.
        let sidebarRow = app.descendants(matching: .any)["sidebar.folder"].firstMatch
        app.buttons["toolbar.sidebar"].tap()
        XCTAssertTrue(sidebarRow.waitForNonExistence(timeout: 5) || !sidebarRow.isHittable, "sidebar hidden")
        let fall = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Fall'")).firstMatch
        if fall.waitForExistence(timeout: 3) {
            fall.tap()
            XCTAssertTrue(app.buttons["toolbar.back"].waitForExistence(timeout: 5))
            let edge = app.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0.5)).withOffset(CGVector(dx: 3, dy: 0))
            edge.press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.85, dy: 0.5)))
            XCTAssertTrue(app.buttons["toolbar.back"].waitForNonExistence(timeout: 5), "swipe back")
        }
        app.buttons["toolbar.sidebar"].tap()
        XCTAssertTrue(sidebarRow.waitForExistence(timeout: 5), "sidebar shown again")
        app.staticTexts["Home"].firstMatch.tap()
        capture("TopBar-Home-portrait")
        app.terminate()
    }

    @MainActor private func assertTopBar(_ app: XCUIApplication, title: String, file: StaticString = #filePath, line: UInt = #line) {
        let pause = app.buttons["toolbar.pause"], settings = app.buttons["toolbar.settings"]
        let account = app.descendants(matching: .any)["toolbar.account"].firstMatch
        XCTAssertTrue(settings.waitForExistence(timeout: 5), "top bar on \(title)", file: file, line: line)
        // The title in the bar, not the same word in the sidebar or a list below it.
        let headings = app.staticTexts.matching(NSPredicate(format: "label == %@", title)).allElementsBoundByIndex
        guard let heading = headings.first(where: { abs($0.frame.midY - settings.frame.midY) < 10 }) else {
            return XCTFail("title \(title) not on the bar's line", file: file, line: line)
        }
        for control in [pause, account] {
            XCTAssertEqual(control.frame.size, settings.frame.size, title, file: file, line: line)
            XCTAssertEqual(control.frame.midY, settings.frame.midY, accuracy: 0.5, title, file: file, line: line)
        }
        XCTAssertEqual(settings.frame.width, 44, accuracy: 0.5, file: file, line: line)
        XCTAssertEqual(settings.frame.minX, pause.frame.maxX, accuracy: 0.5, file: file, line: line)
        XCTAssertEqual(account.frame.minX, settings.frame.maxX, accuracy: 0.5, file: file, line: line)
        XCTAssertEqual(app.frame.maxX - account.frame.maxX, 20, accuracy: 0.5, "24 pt to the circle, 20 to its target", file: file, line: line)
        XCTAssertEqual(heading.frame.midY, settings.frame.midY, accuracy: 2, "one centre line on \(title)", file: file, line: line)
    }

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
