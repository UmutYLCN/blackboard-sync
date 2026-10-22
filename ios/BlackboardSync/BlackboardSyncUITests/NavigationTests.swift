import XCTest

final class NavigationTests: XCTestCase {
    @MainActor
    func testLandscapeNavigationAndPortraitLayout() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-language", "en"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["Announcements"].exists)
        XCTAssertFalse(app.buttons["Calendar"].exists)
        capture("Home-landscape")
        app.buttons["Settings"].tap()
        XCTAssertTrue(app.staticTexts["About & privacy"].exists || app.staticTexts["Account"].exists)
        XCTAssertFalse(app.buttons["Automatic background sync"].exists)
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
    func testTurkishOnboardingAndDisabledFeatures() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-language", "tr"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.staticTexts["Ders dosyalarınız burada başlayacak."].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["Duyurular"].exists)
        XCTAssertFalse(app.buttons["Takvim"].exists)
        capture("Home-Turkish-landscape")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
