import XCTest
@testable import BlackboardSyncFeatures

final class FirstRunTests: XCTestCase {
    private var defaults: UserDefaults!
    private let suite = "FirstRunTests"

    override func setUp() {
        super.setUp()
        UserDefaults().removePersistentDomain(forName: suite)
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDown() {
        UserDefaults().removePersistentDomain(forName: suite)
        super.tearDown()
    }

    func testFreshInstallIsReportedOnceAndBeginsF1UntilFinished() {
        let firstRun = FirstRun(defaults: defaults)
        XCTAssertFalse(firstRun.isPending)
        XCTAssertTrue(firstRun.firstLaunchOfFreshInstall(signedInBefore: false))
        XCTAssertFalse(firstRun.firstLaunchOfFreshInstall(signedInBefore: false), "only the first launch")
        firstRun.begin()
        XCTAssertTrue(FirstRun(defaults: defaults).isPending, "survives relaunch")
        firstRun.finish()
        XCTAssertFalse(FirstRun(defaults: defaults).isPending)
        XCTAssertFalse(firstRun.firstLaunchOfFreshInstall(signedInBefore: false))
    }

    func testAnUpdateWhereBlackboardWasSignedInIsNotAFreshInstall() {
        let firstRun = FirstRun(defaults: defaults)
        XCTAssertFalse(firstRun.firstLaunchOfFreshInstall(signedInBefore: true))
        XCTAssertFalse(firstRun.isPending)
    }

    func testScreenDecision() {
        XCTAssertEqual(FirstRun.screen(pending: true, blackboardAccount: false, downloadedFiles: false), .fullScreen)
        XCTAssertEqual(FirstRun.screen(pending: false, blackboardAccount: false, downloadedFiles: false), .welcomeCard)
        for pending in [true, false] {
            XCTAssertEqual(FirstRun.screen(pending: pending, blackboardAccount: true, downloadedFiles: false), .none)
            XCTAssertEqual(FirstRun.screen(pending: pending, blackboardAccount: false, downloadedFiles: true), .none,
                           "downloaded files keep the normal app")
        }
    }
}
