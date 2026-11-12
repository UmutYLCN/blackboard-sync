import XCTest

final class NavigationTests: XCTestCase {
    private let signInHint = "Sign in to see announcements and due dates from your selected courses."

    @MainActor
    func testLandscapeNavigationAndPortraitLayout() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-firstRunPending", "NO", "-language", "en"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        // Signed out with nothing downloaded: Home is the welcome card (F2) and the top bar shows only Settings.
        XCTAssertTrue(app.descendants(matching: .any)["firstRun.card"].firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Your course files, on your iPad."].exists)
        XCTAssertTrue(app.buttons["firstRun.signIn"].exists)
        XCTAssertFalse(app.staticTexts["Recent downloads"].exists)
        XCTAssertTrue(app.buttons["toolbar.settings"].exists)
        XCTAssertFalse(app.buttons["toolbar.pause"].exists)
        XCTAssertFalse(app.descendants(matching: .any)["toolbar.account"].firstMatch.exists)
        capture("Home-landscape")
        app.buttons["toolbar.settings"].tap()
        XCTAssertTrue(app.staticTexts["About & privacy"].waitForExistence(timeout: 5) || app.staticTexts["Account"].exists)
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["Done"].waitForNonExistence(timeout: 5))
        app.descendants(matching: .any)["sidebar.announcements"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts[signInHint].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Your course files, on your iPad."].exists)
        capture("Announcements-signed-out")
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts[signInHint].waitForExistence(timeout: 5))
        capture("Calendar-signed-out")
        app.buttons["toolbar.settings"].tap()
        XCTAssertTrue(app.staticTexts["About & privacy"].exists || app.staticTexts["Account"].exists)
        XCTAssertEqual(labelled("Coming soon", in: app).count, 0)
        capture("Settings-signed-out")
        // The Sync section is followed directly by Folder, with no Coming soon rows in between.
        app.collectionViews.firstMatch.swipeUp()
        XCTAssertTrue(app.staticTexts["Folder"].waitForExistence(timeout: 5))
        XCTAssertEqual(labelled("Coming soon", in: app).count, 0)
        capture("Settings-signed-out-scrolled")
        app.buttons["Done"].tap()
        app.staticTexts["Courses"].firstMatch.tap()
        XCTAssertTrue(app.descendants(matching: .any)["firstRun.card"].firstMatch.waitForExistence(timeout: 5))
        capture("Courses-welcome-card")
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
        app.launchArguments = ["--ui-testing", "-firstRunPending", "NO", "-language", "tr"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        XCTAssertTrue(app.staticTexts["Ders dosyalarınız iPad’inizde."].waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["Blackboard'a giriş yapın"].exists)
        XCTAssertEqual(app.buttons["toolbar.settings"].label, "Ayarlar")
        capture("Home-Turkish-landscape")
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Seçili derslerinizin duyurularını ve teslim tarihlerini görmek için giriş yapın."].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Takvim"].exists)
        capture("Calendar-Turkish-signed-out")
        app.buttons["toolbar.settings"].tap()
        XCTAssertTrue(app.buttons["Bitti"].waitForExistence(timeout: 5))
        XCTAssertEqual(labelled("Çok yakında", in: app).count, 0)
        capture("Settings-Turkish-signed-out")
        app.collectionViews.firstMatch.swipeUp()
        XCTAssertTrue(app.staticTexts["Klasör"].waitForExistence(timeout: 5))
        XCTAssertEqual(labelled("Çok yakında", in: app).count, 0)
        capture("Settings-Turkish-signed-out-scrolled")
        app.buttons["Bitti"].tap()
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    @MainActor
    func testAnnouncementsAndCalendarWithSampleBlackboard() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "-firstRunPending", "NO", "-language", "en"]
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
        // Board pick H2: the week strip with today marked, then the due dates grouped by when they are due.
        XCTAssertTrue(app.staticTexts["This week"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["calendar.today"].exists)
        XCTAssertEqual(app.buttons.matching(identifier: "calendar.day").count + 1, 7)
        XCTAssertTrue(app.buttons["calendar.today"].label.hasPrefix("Today, "))
        XCTAssertTrue(["Today", "Later this week", "Next week"].contains { app.staticTexts[$0].exists })
        XCTAssertTrue(app.staticTexts["Past due"].exists)
        XCTAssertTrue(app.staticTexts["Select a due date"].exists)
        capture("Calendar-sample-landscape")
        // A due date opens its details beside the list, as before.
        let homework = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Homework 3,'")).firstMatch
        XCTAssertTrue(homework.waitForExistence(timeout: 5))
        homework.tap()
        XCTAssertTrue(app.links["Open in Blackboard"].waitForExistence(timeout: 5) || app.buttons["Open in Blackboard"].exists)
        XCTAssertTrue(app.staticTexts["Points: 100"].exists)
        capture("Calendar-sample-selected-landscape")
        XCUIDevice.shared.orientation = .portrait
        XCTAssertTrue(app.staticTexts["This week"].waitForExistence(timeout: 5))
        capture("Calendar-sample-portrait")
        app.terminate()
    }

    @MainActor
    func testTurkishSamplePages() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "-firstRunPending", "NO", "-language", "tr"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.waitForExistence(timeout: 20)
        app.descendants(matching: .any)["sidebar.calendar"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Bu hafta"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["calendar.today"].label.hasPrefix("Bugün, "))
        XCTAssertTrue(app.staticTexts["Tarihi geçenler"].exists)
        XCTAssertTrue(app.staticTexts["Bir teslim tarihi seçin"].exists)
        capture("Calendar-sample-Turkish")
        app.descendants(matching: .any)["sidebar.announcements"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Seçili derslerinizdeki tüm duyurular."].waitForExistence(timeout: 5))
        capture("Announcements-sample-Turkish")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    /// Home (board pick H1) over the sample Blackboard: the status strip first with its one button, the
    /// due dates and announcements, then the last files as rows; each state from `--ui-testing-home`.
    @MainActor
    func testHomeStatusFirstInEveryState() throws {
        let app = launchHome("up-to-date")
        let status = app.descendants(matching: .any)["home.status"].firstMatch
        XCTAssertTrue(status.waitForExistence(timeout: 20))
        XCTAssertTrue(status.label.hasPrefix("Up to date"), status.label)
        XCTAssertTrue(status.label.contains("3 new files"), status.label)
        let action = app.buttons["home.action"]
        XCTAssertEqual(action.label, "Sync now")
        XCTAssertTrue(action.isEnabled)
        XCTAssertTrue(app.staticTexts["Homework 3"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Exam rooms & times"].exists)
        XCTAssertTrue(app.buttons["Open calendar"].exists)
        // The status strip sits above the due dates, which sit above the files.
        let recent = app.buttons.matching(identifier: "home.recent")
        XCTAssertEqual(recent.count, 4)
        XCTAssertTrue(recent.firstMatch.label.contains("SPM Slides-3.pdf"), recent.firstMatch.label)
        XCTAssertTrue(recent.firstMatch.isHittable, "the whole row is the button")
        XCTAssertLessThan(status.frame.maxY, app.staticTexts["Homework 3"].frame.minY)
        XCTAssertLessThan(app.staticTexts["Homework 3"].frame.maxY, app.staticTexts["Recent downloads"].frame.minY)
        // Due dates and announcements share one row in landscape and in portrait.
        XCTAssertTrue(sideBySide(app), "side by side in landscape")
        capture("Home-H1-landscape")
        XCUIDevice.shared.orientation = .portrait
        XCTAssertTrue(app.buttons["home.action"].waitForExistence(timeout: 5))
        // With the sidebar open the page is too narrow for two cards, so they stack.
        XCTAssertFalse(sideBySide(app), "stacked in portrait with the sidebar open")
        capture("Home-H1-portrait-sidebar")
        // As drawn on the board: the sidebar hidden behind its button, the two cards side by side.
        app.buttons["toolbar.sidebar"].tap()
        let sidebarRow = app.descendants(matching: .any)["sidebar.folder"].firstMatch
        XCTAssertTrue(sidebarRow.waitForNonExistence(timeout: 5) || !sidebarRow.isHittable, "sidebar hidden")
        XCTAssertTrue(sideBySide(app), "side by side in portrait")
        capture("Home-H1-portrait")
        app.buttons["toolbar.sidebar"].tap()
        app.terminate()

        for (state, title, button) in [("syncing", "Syncing…", "Cancel"), ("failed", "Sync did not finish", "Retry sync"),
                                       ("signin", "Sign-in needed", "Reconnect"), ("empty", "Ready to sync", "Sync now")] {
            let app = launchHome(state)
            let status = app.descendants(matching: .any)["home.status"].firstMatch
            XCTAssertTrue(status.waitForExistence(timeout: 20), state)
            XCTAssertTrue(status.label.hasPrefix(title), "\(state): \(status.label)")
            XCTAssertEqual(app.buttons["home.action"].label, button, state)
            if state == "empty" {
                XCTAssertTrue(app.staticTexts["Nothing downloaded yet."].exists)
                XCTAssertEqual(app.buttons.matching(identifier: "home.recent").count, 0)
            }
            capture("Home-H1-\(state)")
            app.terminate()
        }

        let loading = launchHome("loading")
        let loadingStatus = loading.descendants(matching: .any)["home.status"].firstMatch
        XCTAssertTrue(loadingStatus.waitForExistence(timeout: 20))
        XCTAssertTrue(loadingStatus.label.hasPrefix("Finding your courses…"), loadingStatus.label)
        XCTAssertFalse(loading.buttons["home.action"].exists, "nothing to tap while loading")
        capture("Home-H1-loading")
        loading.terminate()

        // Paused: the strip itself offers Resume; tapping it lifts the pause, as the top bar's play button does.
        let paused = launchHome("up-to-date", extra: ["-paused", "1"])
        let pausedStatus = paused.descendants(matching: .any)["home.status"].firstMatch
        XCTAssertTrue(pausedStatus.waitForExistence(timeout: 20))
        XCTAssertTrue(pausedStatus.label.hasPrefix("Paused"), pausedStatus.label)
        XCTAssertEqual(paused.buttons["home.action"].label, "Resume syncing")
        capture("Home-H1-paused")
        paused.buttons["home.action"].tap()
        XCTAssertTrue(paused.buttons["home.action"].waitForExistence(timeout: 5))
        XCTAssertEqual(paused.buttons["home.action"].label, "Sync now")
        XCTAssertEqual(paused.buttons["toolbar.pause"].label, "Pause syncing")
        paused.terminate()
    }

    @MainActor
    func testHomeInTurkish() throws {
        let app = launchHome("up-to-date", language: "tr")
        let status = app.descendants(matching: .any)["home.status"].firstMatch
        XCTAssertTrue(status.waitForExistence(timeout: 20))
        XCTAssertTrue(status.label.hasPrefix("Güncel"), status.label)
        XCTAssertTrue(status.label.contains("3 yeni dosya"), status.label)
        XCTAssertTrue(status.label.contains("Son senkronizasyon"), status.label)
        XCTAssertEqual(app.buttons["home.action"].label, "Şimdi senkronize et")
        XCTAssertTrue(app.staticTexts["Son indirilenler"].exists)
        XCTAssertTrue(app.staticTexts["Yaklaşan teslim tarihleri"].exists)
        XCTAssertTrue(app.buttons["Takvimi aç"].exists)
        capture("Home-H1-Turkish-landscape")
        XCUIDevice.shared.orientation = .portrait
        XCTAssertTrue(app.buttons["home.action"].waitForExistence(timeout: 5))
        app.buttons["toolbar.sidebar"].tap()
        capture("Home-H1-Turkish-portrait")
        app.buttons["toolbar.sidebar"].tap()
        app.terminate()
        let paused = launchHome("syncing", language: "tr")
        XCTAssertTrue(paused.descendants(matching: .any)["home.status"].firstMatch.waitForExistence(timeout: 20))
        XCTAssertEqual(paused.buttons["home.action"].label, "Vazgeç")
        capture("Home-H1-Turkish-syncing")
        paused.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    /// The Announcements card's heading sits to the right of the due dates' heading, not under it.
    @MainActor private func sideBySide(_ app: XCUIApplication) -> Bool {
        let deadlines = app.staticTexts["Upcoming deadlines"].frame
        let headings = app.staticTexts.matching(NSPredicate(format: "label == 'Announcements'")).allElementsBoundByIndex
        // The sidebar row has the same label; the card's heading is the one right of the due dates' heading.
        return headings.contains { $0.frame.minX > deadlines.maxX && $0.frame.minY < deadlines.maxY + 30 }
    }

    @MainActor private func launchHome(_ state: String, language: String = "en", extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "--ui-testing-home", state, "-firstRunPending", "NO", "-language", language] + extra
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        return app
    }

    /// The full-screen first run (F1) on a fresh install: no sidebar or top bar, the language menu, the
    /// school menu with "Other school…" and the button into sign-in. No school page is loaded.
    @MainActor
    func testFullScreenFirstRun() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-firstRunPending", "YES", "-language", "en"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        let page = app.descendants(matching: .any)["firstRun.page"].firstMatch
        XCTAssertTrue(page.waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Your course files, on your iPad."].exists)
        XCTAssertTrue(app.staticTexts["Istanbul Health and Technology University"].exists)
        XCTAssertFalse(app.descendants(matching: .any)["sidebar.folder"].firstMatch.exists)
        XCTAssertFalse(app.buttons["toolbar.settings"].exists)
        XCTAssertFalse(app.descendants(matching: .any)["firstRun.address"].firstMatch.exists)
        capture("FirstRun-landscape")
        XCUIDevice.shared.orientation = .portrait
        // The button stays in reach after the rotation settles.
        expectation(for: NSPredicate(format: "isHittable == true"), evaluatedWith: app.buttons["firstRun.signIn"])
        waitForExpectations(timeout: 10)
        capture("FirstRun-portrait")
        // Language is the only other control.
        app.buttons["firstRun.language"].tap()
        app.buttons["Türkçe"].tap()
        XCTAssertTrue(app.staticTexts["Ders dosyalarınız iPad’inizde."].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Blackboard'a giriş yapın"].exists)
        XCTAssertTrue(app.staticTexts["Okul"].exists)
        capture("FirstRun-Turkish-portrait")
        XCUIDevice.shared.orientation = .landscapeLeft
        capture("FirstRun-Turkish-landscape")
        app.buttons["firstRun.language"].tap()
        app.buttons["English"].tap()
        XCTAssertTrue(app.staticTexts["Your course files, on your iPad."].waitForExistence(timeout: 5))
        // "Other school…" shows the address field. An address that is not HTTPS stops before any page loads.
        app.buttons["firstRun.school"].tap()
        app.buttons["Other school…"].tap()
        let address = app.textFields["firstRun.address"]
        XCTAssertTrue(address.waitForExistence(timeout: 5))
        address.tap()
        address.typeText("http://school.invalid")
        app.buttons["firstRun.signIn"].tap()
        XCTAssertTrue(app.staticTexts["Enter an HTTPS tenant origin, without a path, query, or credentials."].waitForExistence(timeout: 5))
        XCTAssertTrue(page.exists, "the first run stays until Blackboard is signed in")
        capture("FirstRun-other-school")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    /// The first run's last step (`--ui-testing-sample-school`, a school answered from memory): Sign in
    /// to Blackboard leads to the card with the term and courses found, under the top bar, before anything
    /// downloads. Unticking and Change term update it; Confirm and start syncs, and Courses keeps the ticks.
    @MainActor
    func testFirstRunEndsWithTheCardBeforeTheFirstDownload() throws {
        let app = launchSampleSchool("en", .landscapeLeft)
        let card = app.descendants(matching: .any)["termConfirm.card"].firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 20), "the card opens right after sign-in")
        XCTAssertFalse(app.descendants(matching: .any)["firstRun.page"].firstMatch.exists)
        XCTAssertTrue(app.staticTexts["Check your courses before the first download"].exists)
        // Longer than a query by label may be, so matched by its start.
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Blackboard Sync found your current term")).firstMatch.exists)
        XCTAssertEqual(app.staticTexts["termConfirm.term"].label, "Term, Fall 2026")
        XCTAssertEqual(app.staticTexts["termConfirm.count"].label, "3 of 3 courses selected")
        XCTAssertTrue(app.buttons["toolbar.settings"].exists, "the top bar stays")
        XCTAssertTrue(app.buttons["termConfirm.confirm"].isEnabled)
        XCTAssertFalse(app.staticTexts["Up to date"].exists, "nothing synced yet")
        sleep(1)
        capture("TermConfirm-landscape-en")
        XCUIDevice.shared.orientation = .portrait
        expectation(for: NSPredicate(format: "isHittable == true"), evaluatedWith: app.buttons["termConfirm.confirm"])
        waitForExpectations(timeout: 10)
        capture("TermConfirm-portrait-en")

        let project = app.descendants(matching: .any)["termConfirm.course._103_1"].firstMatch
        project.tap()
        XCTAssertTrue(waitFor(app.staticTexts["termConfirm.count"], label: "2 of 3 courses selected"))
        app.buttons["termConfirm.change"].tap()
        app.buttons["Spring 2026 · 2 courses"].tap()
        XCTAssertTrue(waitFor(app.staticTexts["termConfirm.term"], label: "Term, Spring 2026"))
        XCTAssertEqual(app.staticTexts["termConfirm.count"].label, "2 of 2 courses selected")
        XCTAssertTrue(app.descendants(matching: .any)["termConfirm.course._201_1"].firstMatch.exists)
        capture("TermConfirm-changed-term-portrait-en")
        app.buttons["termConfirm.change"].tap()
        app.buttons["Fall 2026"].tap()
        XCTAssertTrue(waitFor(app.staticTexts["termConfirm.term"], label: "Term, Fall 2026"))
        XCTAssertEqual(app.staticTexts["termConfirm.count"].label, "3 of 3 courses selected")
        project.tap()
        XCTAssertTrue(waitFor(app.staticTexts["termConfirm.count"], label: "2 of 3 courses selected"))

        XCUIDevice.shared.orientation = .landscapeLeft
        app.buttons["termConfirm.confirm"].tap()
        XCTAssertTrue(card.waitForNonExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Up to date"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["2/3"].exists, "Courses shows the ticks kept")
        capture("TermConfirm-confirmed-landscape-en")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    /// The same card in Turkish, with Turkish counts.
    @MainActor
    func testTheCardBeforeTheFirstDownloadInTurkish() throws {
        let app = launchSampleSchool("tr", .portrait)
        XCTAssertTrue(app.descendants(matching: .any)["termConfirm.card"].firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["İlk indirmeden önce derslerinizi kontrol edin"].exists)
        XCTAssertEqual(app.staticTexts["termConfirm.count"].label, "3 dersin 3 tanesi seçili")
        XCTAssertEqual(app.buttons["termConfirm.confirm"].label, "Onayla ve başlat")
        XCTAssertEqual(app.buttons["termConfirm.change"].label, "Dönemi değiştir")
        sleep(1)
        capture("TermConfirm-portrait-tr")
        app.buttons["termConfirm.change"].tap()
        XCTAssertTrue(app.buttons["Spring 2026 · 2 ders"].waitForExistence(timeout: 5))
        capture("TermConfirm-menu-portrait-tr")
        app.buttons["Spring 2026 · 2 ders"].tap()
        XCTAssertTrue(waitFor(app.staticTexts["termConfirm.count"], label: "2 dersin 2 tanesi seçili"))
        XCUIDevice.shared.orientation = .landscapeLeft
        sleep(1)
        capture("TermConfirm-landscape-tr")
        app.terminate()
        XCUIDevice.shared.orientation = .portrait
    }

    /// A fresh install at the first run, whose Sign in to Blackboard signs in to the sample school.
    @MainActor private func launchSampleSchool(_ language: String, _ orientation: UIDeviceOrientation) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-sample-school", "-firstRunPending", "YES", "-language", language]
        XCUIDevice.shared.orientation = orientation
        app.launch()
        let signIn = app.buttons["firstRun.signIn"]
        XCTAssertTrue(signIn.waitForExistence(timeout: 20))
        signIn.tap()
        return app
    }

    @MainActor private func waitFor(_ element: XCUIElement, label: String) -> Bool {
        let expectation = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", label), object: element)
        return XCTWaiter().wait(for: [expectation], timeout: 5) == .completed
    }

    /// The top bar (board pick T1) on every page, pushed folder pages included: the title and three
    /// equal 44 pt targets on one centre line, the targets touching, the last circle 24 pt from the edge.
    @MainActor
    func testTopBarOnEveryPage() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--ui-testing-features", "-firstRunPending", "NO", "-language", "en"]
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

    /// Every element whose label contains the text, including rows that merge their children into one label.
    @MainActor private func labelled(_ text: String, in app: XCUIApplication) -> [XCUIElement] {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).allElementsBoundByIndex
    }

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
