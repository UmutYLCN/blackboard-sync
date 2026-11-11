import XCTest
import BlackboardSyncFeatures
@testable import BlackboardSync

/// The first-run screens' wiring in `AppModel`: F1 on a fresh install until Blackboard is signed in,
/// then F2 once signed out, unless files are downloaded. No school request runs.
final class FirstRunWiringTests: XCTestCase {
    private let suite = "FirstRunWiringTests"
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        UserDefaults().removePersistentDomain(forName: suite)
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDown() {
        UserDefaults().removePersistentDomain(forName: suite)
        super.tearDown()
    }

    @MainActor
    func testFreshInstallShowsF1UntilBlackboardIsSignedInThenF2AfterSignOut() {
        let model = AppModel(firstRun: FirstRun(defaults: defaults))
        // A library that never had an account is a fresh install; one that had is an update without F1.
        XCTAssertEqual(model.firstRunScreen, model.scope.isEmpty ? .fullScreen : .welcomeCard)
        model.appAccountDidSignIn()
        XCTAssertEqual(model.firstRunScreen, .fullScreen)
        XCTAssertEqual(AppModel(firstRun: FirstRun(defaults: defaults)).firstRunScreen, .fullScreen, "survives relaunch")
        model.hasStoredSession = true
        XCTAssertEqual(model.firstRunScreen, .none)
        XCTAssertFalse(FirstRun(defaults: defaults).isPending, "signing in ends the first run for good")
        model.hasStoredSession = false
        XCTAssertEqual(model.firstRunScreen, .welcomeCard, "signed out later: the in-app card")
        XCTAssertEqual(AppModel(firstRun: FirstRun(defaults: defaults)).firstRunScreen, .welcomeCard)
    }

    @MainActor
    func testDownloadedFilesKeepTheNormalAppWhenSignedOut() {
        FirstRun(defaults: defaults).finish()
        let model = AppModel(firstRun: FirstRun(defaults: defaults))
        XCTAssertEqual(model.firstRunScreen, .welcomeCard)
        model.library.records["University/Fall/COE305/Slides.pdf"] = FileRecord(relativePath: "University/Fall/COE305/Slides.pdf", hash: "h", updated: Date(), size: 1)
        XCTAssertEqual(model.firstRunScreen, .none)
    }

    @MainActor
    func testAppAccountSignInHookShowsF1OnlyWhileBlackboardIsSignedOut() {
        FirstRun(defaults: defaults).finish()
        let model = AppModel(firstRun: FirstRun(defaults: defaults))
        model.appAccountDidSignIn()
        XCTAssertEqual(model.firstRunScreen, .fullScreen)
        model.hasSession = true
        XCTAssertEqual(model.firstRunScreen, .none)
        model.appAccountDidSignIn()
        model.hasSession = false
        XCTAssertEqual(model.firstRunScreen, .welcomeCard, "the hook does nothing while Blackboard is signed in")
        model.needsSignIn = true
        XCTAssertEqual(model.firstRunScreen, .none, "Reconnect keeps the normal app")
    }

    func testFirstRunWordingIsTranslated() {
        for key in ["Your course files, on your iPad.",
                    "Sign in once with your school account. Your files, due dates and announcements show up here.",
                    "School", "Other school…", "Sign in to Blackboard", "Language",
                    "You sign in on your school's own page. Your password is never stored.",
                    "Your password is never stored."] {
            XCTAssertNotNil(L10n.turkish[key], key)
        }
        XCTAssertEqual(L10n.text("Sign in to Blackboard", language: "tr"), "Blackboard'a giriş yapın")
    }
}
