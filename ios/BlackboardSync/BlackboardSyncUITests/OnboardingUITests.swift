import XCTest

/// The splash and the five-page introduction. `--ui-testing-onboarding` shows the introduction
/// whatever this simulator saved before; plain `--ui-testing` runs, like the other UI tests, skip it.
final class OnboardingUITests: XCTestCase {
    private let titles = ["All your course files, in one place", "You choose the courses", "Never miss a due date",
                          "Every announcement in one list", "Yours, and available offline"]
    private let turkishTitles = ["Tüm ders dosyalarınız tek yerde", "Dersleri siz seçin", "Teslim tarihlerini kaçırmayın",
                                 "Tüm duyurular tek listede", "Sizde kalır, çevrimdışı açılır"]

    override func tearDown() {
        XCUIDevice.shared.orientation = .portrait
        super.tearDown()
    }

    @MainActor
    private func launch(_ language: String, _ orientation: UIDeviceOrientation, extra: [String] = ["--ui-testing-onboarding"]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"] + extra + ["-language", language]
        XCUIDevice.shared.orientation = orientation
        app.launch()
        return app
    }

    @MainActor
    func testContinueStepsThroughAllFivePagesThenGetStartedOpensHome() throws {
        let app = launch("en", .landscapeLeft)
        let next = app.buttons["onboarding.next"], indicator = app.descendants(matching: .any)["onboarding.indicator"]
        XCTAssertTrue(app.staticTexts[titles[0]].waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["onboarding.skip"].exists)
        XCTAssertEqual(app.buttons["onboarding.skip"].label, "Skip the introduction")
        // The app underneath is hidden from VoiceOver while the introduction covers it.
        XCTAssertFalse(app.buttons["toolbar.settings"].exists)
        sleep(2)  // the splash has faded
        capture("Onboarding-1-landscape-en")
        for (index, title) in titles.enumerated() {
            XCTAssertTrue(app.staticTexts[title].waitForExistence(timeout: 5), title)
            XCTAssertEqual(indicator.label, "Page \(index + 1) of 5")
            XCTAssertEqual(next.label, index == titles.count - 1 ? "Get started" : "Continue")
            if index > 0 { capture("Onboarding-\(index + 1)-landscape-en") }
            next.tap()
        }
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 5))
        XCTAssertTrue(next.waitForNonExistence(timeout: 5))
        XCTAssertTrue(app.buttons["toolbar.settings"].exists)
        app.terminate()
    }

    @MainActor
    func testSwipingAndTheIndicatorInPortrait() throws {
        let app = launch("en", .portrait)
        let indicator = app.descendants(matching: .any)["onboarding.indicator"]
        XCTAssertTrue(app.staticTexts[titles[0]].waitForExistence(timeout: 20))
        sleep(2)
        capture("Onboarding-1-portrait-en")
        app.staticTexts[titles[0]].swipeLeft()
        XCTAssertTrue(app.staticTexts[titles[1]].waitForExistence(timeout: 5))
        XCTAssertEqual(indicator.label, "Page 2 of 5")
        app.staticTexts[titles[1]].swipeRight()
        XCTAssertTrue(app.staticTexts[titles[0]].waitForExistence(timeout: 5))
        XCTAssertEqual(indicator.label, "Page 1 of 5")
        app.buttons["onboarding.skip"].tap()
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 5))
        app.terminate()
    }

    @MainActor
    func testTurkishSkipThenSettingsOpensTheIntroductionAgain() throws {
        let app = launch("tr", .landscapeLeft)
        XCTAssertTrue(app.staticTexts[turkishTitles[0]].waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons["onboarding.next"].label, "Devam")
        XCTAssertEqual(app.buttons["onboarding.skip"].label, "Tanıtımı geç")
        XCTAssertEqual(app.descendants(matching: .any)["onboarding.indicator"].label, "Sayfa 1 / 5")
        sleep(2)
        capture("Onboarding-1-landscape-tr")
        for title in turkishTitles.dropFirst() {
            app.buttons["onboarding.next"].tap()
            XCTAssertTrue(app.staticTexts[title].waitForExistence(timeout: 5), title)
        }
        XCTAssertEqual(app.buttons["onboarding.next"].label, "Başlayın")
        capture("Onboarding-5-landscape-tr")
        app.buttons["onboarding.skip"].tap()
        XCTAssertTrue(app.staticTexts["Ders dosyalarınız burada başlayacak."].waitForExistence(timeout: 5))
        // Settings › About & privacy › Show the introduction: the sheet closes onto page 1.
        app.buttons["toolbar.settings"].tap()
        let again = app.buttons["settings.showOnboarding"]
        XCTAssertTrue(app.staticTexts["Hakkında ve gizlilik"].waitForExistence(timeout: 5) || again.exists)
        var swipes = 0
        while !again.isHittable && swipes < 8 { app.swipeUp(); swipes += 1 }
        XCTAssertEqual(again.label, "Tanıtımı göster")
        capture("Settings-show-introduction-tr")
        again.tap()
        XCTAssertTrue(app.staticTexts[turkishTitles[0]].waitForExistence(timeout: 5))
        XCTAssertEqual(app.descendants(matching: .any)["onboarding.indicator"].label, "Sayfa 1 / 5")
        app.buttons["onboarding.next"].tap()
        XCTAssertTrue(app.staticTexts[turkishTitles[1]].waitForExistence(timeout: 5))
        capture("Onboarding-2-landscape-tr-again")
        app.terminate()
    }

    @MainActor
    func testNotShownToTheOtherUITests() throws {
        let app = launch("en", .landscapeLeft, extra: [])
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["onboarding.next"].exists)
        app.terminate()
    }

    /// The splash held on screen, for its screenshots.
    @MainActor
    func testSplashScreenshots() throws {
        for orientation in [UIDeviceOrientation.landscapeLeft, .portrait] {
            let app = launch("en", orientation, extra: ["--ui-testing-hold-splash"])
            XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 20))
            sleep(2)
            capture("Splash-\(orientation == .portrait ? "portrait" : "landscape")")
            app.terminate()
        }
    }

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
