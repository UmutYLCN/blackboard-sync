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
        XCTAssertTrue(app.staticTexts[titles[0]].waitForExistence(timeout: 60))
        XCTAssertTrue(app.buttons["onboarding.skip"].exists)
        XCTAssertEqual(app.buttons["onboarding.skip"].label, "Skip the introduction")
        // The app underneath can not be reached while the introduction covers it.
        XCTAssertFalse(app.buttons["toolbar.settings"].exists && app.buttons["toolbar.settings"].isHittable)
        sleep(3)  // the splash has faded
        capture("Onboarding-1-landscape-en")
        for (index, title) in titles.enumerated() {
            XCTAssertTrue(app.staticTexts[title].waitForExistence(timeout: 15), title)
            XCTAssertTrue(waitFor(indicator, label: "Page \(index + 1) of 5"), title)
            XCTAssertEqual(next.label, index == titles.count - 1 ? "Get started" : "Continue")
            if index > 0 { capture("Onboarding-\(index + 1)-landscape-en") }
            next.tap()
        }
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 15))
        XCTAssertTrue(next.waitForNonExistence(timeout: 15))
        XCTAssertTrue(app.buttons["toolbar.settings"].isHittable)
        app.terminate()
    }

    @MainActor
    func testSwipingAndTheIndicatorInPortrait() throws {
        let app = launch("en", .portrait)
        let indicator = app.descendants(matching: .any)["onboarding.indicator"]
        XCTAssertTrue(app.staticTexts[titles[0]].waitForExistence(timeout: 60))
        sleep(3)
        capture("Onboarding-1-portrait-en")
        swipe(app, on: titles[0], left: true)
        XCTAssertTrue(waitFor(indicator, label: "Page 2 of 5"))
        XCTAssertTrue(app.staticTexts[titles[1]].exists)
        capture("Onboarding-2-portrait-en")
        swipe(app, on: titles[1], left: false)
        XCTAssertTrue(waitFor(indicator, label: "Page 1 of 5"))
        app.buttons["onboarding.skip"].tap()
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 15))
        app.terminate()
    }

    @MainActor
    func testTurkishSkipThenSettingsOpensTheIntroductionAgain() throws {
        let app = launch("tr", .landscapeLeft)
        XCTAssertTrue(app.staticTexts[turkishTitles[0]].waitForExistence(timeout: 60))
        XCTAssertEqual(app.buttons["onboarding.next"].label, "Devam")
        XCTAssertEqual(app.buttons["onboarding.skip"].label, "Tanıtımı geç")
        XCTAssertEqual(app.descendants(matching: .any)["onboarding.indicator"].label, "Sayfa 1 / 5")
        sleep(3)
        capture("Onboarding-1-landscape-tr")
        for title in turkishTitles.dropFirst() {
            app.buttons["onboarding.next"].tap()
            XCTAssertTrue(app.staticTexts[title].waitForExistence(timeout: 15), title)
        }
        XCTAssertEqual(app.buttons["onboarding.next"].label, "Başlayın")
        capture("Onboarding-5-landscape-tr")
        app.buttons["onboarding.skip"].tap()
        XCTAssertTrue(app.staticTexts["Ders dosyalarınız burada başlayacak."].waitForExistence(timeout: 15))
        // Settings › About & privacy › Show the introduction: the sheet closes onto page 1.
        app.buttons["toolbar.settings"].tap()
        let again = app.buttons["settings.showOnboarding"]
        // The row is at the bottom of a lazy list, so it exists only once scrolled to.
        XCTAssertTrue(app.buttons["Bitti"].waitForExistence(timeout: 15))
        var swipes = 0
        while !(again.exists && again.isHittable) && swipes < 8 { app.swipeUp(); swipes += 1 }
        sleep(2)  // a tap while the list still scrolls only stops it
        XCTAssertEqual(again.label, "Tanıtımı göster")
        capture("Settings-show-introduction-tr")
        again.tap()
        XCTAssertTrue(app.staticTexts[turkishTitles[0]].waitForExistence(timeout: 15))
        XCTAssertTrue(waitFor(app.descendants(matching: .any)["onboarding.indicator"], label: "Sayfa 1 / 5"))
        app.buttons["onboarding.next"].tap()
        XCTAssertTrue(app.staticTexts[turkishTitles[1]].waitForExistence(timeout: 15))
        capture("Onboarding-2-landscape-tr-again")
        app.terminate()
    }

    @MainActor
    func testNotShownToTheOtherUITests() throws {
        let app = launch("en", .landscapeLeft, extra: [])
        XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 60))
        XCTAssertFalse(app.buttons["onboarding.next"].exists)
        app.terminate()
    }

    /// The splash held on screen, for its screenshots.
    @MainActor
    func testSplashScreenshots() throws {
        for orientation in [UIDeviceOrientation.landscapeLeft, .portrait] {
            let app = launch("en", orientation, extra: ["--ui-testing-hold-splash"])
            XCTAssertTrue(app.staticTexts["Your course files start here."].waitForExistence(timeout: 60))
            sleep(4)
            capture("Splash-\(orientation == .portrait ? "portrait" : "landscape")")
            app.terminate()
        }
    }

    /// Drags across most of the screen at the text's height, like a finger turning the page.
    @MainActor private func swipe(_ app: XCUIApplication, on text: String, left: Bool) {
        let frame = app.staticTexts[text].frame, screen = app.frame
        let y = frame.midY / screen.height
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: left ? 0.9 : 0.1, dy: y))
        let end = app.coordinate(withNormalizedOffset: CGVector(dx: left ? 0.1 : 0.9, dy: y))
        start.press(forDuration: 0.05, thenDragTo: end, withVelocity: .fast, thenHoldForDuration: 0)
    }

    @MainActor private func waitFor(_ element: XCUIElement, label: String, timeout: TimeInterval = 10) -> Bool {
        let expectation = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", label), object: element)
        return XCTWaiter().wait(for: [expectation], timeout: timeout) == .completed
    }

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
