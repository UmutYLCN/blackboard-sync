import XCTest
@testable import BlackboardSyncFeatures

final class OnboardingTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite: String!

    override func setUp() {
        super.setUp()
        suite = "OnboardingTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
        super.tearDown()
    }

    // MARK: Pages

    func testFivePagesInTheBoardsOrder() {
        XCTAssertEqual(OnboardingPage.allCases, [.files, .courses, .deadlines, .announcements, .offline])
        XCTAssertEqual(OnboardingPage.allCases.map(\.number), [1, 2, 3, 4, 5])
        XCTAssertEqual(Set(OnboardingPage.allCases.map(\.illustration)).count, 5)
    }

    func testContinueStepsThroughThePagesAndTheLastOneFinishes() {
        var step = OnboardingStep.show(.files)
        var seen: [OnboardingPage] = []
        while case .show(let page) = step {
            seen.append(page)
            step = .after(page)
        }
        XCTAssertEqual(seen, OnboardingPage.allCases)
        XCTAssertEqual(step, .finish)
        XCTAssertTrue(OnboardingPage.offline.isLast)
        XCTAssertNil(OnboardingPage.files.previous)
        XCTAssertEqual(OnboardingPage.courses.previous, .files)
    }

    // MARK: Copy

    func testEveryStringHasATurkishTranslation() {
        let english = OnboardingStrings(.english), turkish = OnboardingStrings(.turkish)
        for page in OnboardingPage.allCases {
            XCTAssertNotNil(OnboardingStrings.turkish[english.title(page)], english.title(page))
            XCTAssertNotNil(OnboardingStrings.turkish[english.body(page)], english.body(page))
            XCTAssertNotEqual(turkish.title(page), english.title(page))
            XCTAssertNotEqual(turkish.body(page), english.body(page))
            XCTAssertNotEqual(turkish.primary(page), english.primary(page))
            XCTAssertNotEqual(turkish.pageIndicator(page), english.pageIndicator(page))
        }
        for key in ["Skip", "Skip the introduction", "Show the introduction"] {
            XCTAssertNotNil(OnboardingStrings.turkish[key], key)
        }
        // No unused entries: every Turkish key is shown somewhere.
        var used = Set(["Continue", "Get started", "Skip", "Skip the introduction", "Page {n} of {total}", "Show the introduction"])
        for page in OnboardingPage.allCases { used.formUnion([english.title(page), english.body(page)]) }
        XCTAssertEqual(Set(OnboardingStrings.turkish.keys), used)
    }

    func testCopyMatchesTheBoard() {
        let english = OnboardingStrings(.english), turkish = OnboardingStrings(.turkish)
        XCTAssertEqual(english.title(.files), "All your course files, in one place")
        XCTAssertEqual(turkish.title(.offline), "Sizde kalır, çevrimdışı açılır")
        XCTAssertEqual(turkish.body(.deadlines), "Tüm derslerinizin yaklaşan teslim tarihleri, gün gün, Ana sayfada.")
        XCTAssertEqual(english.primary(.files), "Continue")
        XCTAssertEqual(english.primary(.offline), "Get started")
        XCTAssertEqual(turkish.primary(.announcements), "Devam")
        XCTAssertEqual(turkish.primary(.offline), "Başlayın")
        XCTAssertEqual(turkish.skip, "Geç")
    }

    func testPageIndicatorLabel() {
        XCTAssertEqual(OnboardingStrings(.english).pageIndicator(.courses), "Page 2 of 5")
        XCTAssertEqual(OnboardingStrings(.turkish).pageIndicator(.offline), "Sayfa 5 / 5")
    }

    // MARK: Seen once

    func testShownOnFirstLaunchOnlyUntilSeen() {
        let record = OnboardingRecord(defaults: defaults)
        XCTAssertFalse(record.seen)
        XCTAssertTrue(record.showsOnLaunch())
        record.markSeen()
        XCTAssertTrue(record.seen)
        XCTAssertFalse(record.showsOnLaunch())
        // A fresh record over the same defaults, as on the next launch.
        XCTAssertFalse(OnboardingRecord(defaults: defaults).showsOnLaunch())
    }

    func testANewerVersionOfThePagesShowsAgain() {
        defaults.set(OnboardingRecord.version - 1, forKey: OnboardingRecord.key)
        XCTAssertFalse(OnboardingRecord(defaults: defaults).seen)
        defaults.set(OnboardingRecord.version + 1, forKey: OnboardingRecord.key)
        XCTAssertTrue(OnboardingRecord(defaults: defaults).seen)
    }

    func testUITestArguments() {
        let record = OnboardingRecord(defaults: defaults)
        XCTAssertFalse(record.showsOnLaunch(arguments: ["--ui-testing"]))
        XCTAssertTrue(record.showsOnLaunch(arguments: ["--ui-testing", "--ui-testing-onboarding"]))
        record.markSeen()
        XCTAssertTrue(record.showsOnLaunch(arguments: ["--ui-testing", "--ui-testing-onboarding"]))
        XCTAssertFalse(record.showsOnLaunch(arguments: []))
    }

    // MARK: Splash

    func testSplashStartsFromTheLaunchScreensLogo() {
        let timeline = SplashTimeline.standard(reduceMotion: false)
        XCTAssertTrue(timeline.moves)
        XCTAssertEqual(timeline.logoStartScale * SplashMetrics.logo, SplashMetrics.launchLogo, accuracy: 0.001)
        // The name comes in before the fade starts, and the whole splash stays short.
        XCTAssertLessThanOrEqual(timeline.wordmarkDelay + timeline.wordmarkDuration, timeline.hold)
        XCTAssertLessThanOrEqual(timeline.logoDuration, timeline.hold)
        XCTAssertLessThanOrEqual(timeline.total, 1.5)
    }

    func testReduceMotionOnlyFadesTheLaunchFrame() {
        let timeline = SplashTimeline.standard(reduceMotion: true)
        XCTAssertFalse(timeline.moves)
        XCTAssertEqual(timeline.logoStartScale, SplashTimeline.standard(reduceMotion: false).logoStartScale)
        XCTAssertLessThan(timeline.total, SplashTimeline.standard(reduceMotion: false).total)
        XCTAssertLessThanOrEqual(timeline.total, 0.5)
    }

    func testWhiteNameIsReadableOnTheSplashNavy() {
        for navy in [Palette.splash.base, Palette.splash.glow, Palette.splash.edge] {
            XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.white, navy), 4.5)
        }
    }
}
