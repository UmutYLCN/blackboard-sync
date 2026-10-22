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
        app.descendants(matching: .any)["sidebar.announcements"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts[signInHint].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Your course files start here."].exists)
        capture("Announcements-signed-out")
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts[signInHint].waitForExistence(timeout: 5))
        capture("Calendar-signed-out")
        app.buttons["Settings"].tap()
        XCTAssertTrue(app.staticTexts["About & privacy"].exists || app.staticTexts["Account"].exists)
        for item in ["Automatic background sync", "Connect Google Calendar", "Choose another folder", "Past terms", "Notes PDFs"] {
            XCTAssertFalse(app.buttons[item].exists, item)
        }
        app.buttons["Done"].tap()
        app.staticTexts["Courses"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["No current-term courses found."].waitForExistence(timeout: 5))
        app.staticTexts["Open folder"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["No downloaded files yet."].waitForExistence(timeout: 5))
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

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
