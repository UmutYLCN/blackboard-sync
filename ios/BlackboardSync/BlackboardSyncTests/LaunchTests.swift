import XCTest
import UIKit
import BlackboardSyncFeatures
@testable import BlackboardSync

/// The launch screen, the splash that takes over from it, and the introduction's first-launch flag.
final class LaunchTests: XCTestCase {
    private var savedSeen: Any?

    override func setUp() {
        super.setUp()
        savedSeen = UserDefaults.standard.object(forKey: OnboardingRecord.key)
    }

    override func tearDown() {
        UserDefaults.standard.set(savedSeen, forKey: OnboardingRecord.key)
        super.tearDown()
    }

    private var launchScreen: [String: String] {
        Bundle.main.object(forInfoDictionaryKey: "UILaunchScreen") as? [String: String] ?? [:]
    }

    func testLaunchScreenIsTheSplashsFirstFrame() throws {
        // No white flash: the launch screen is the splash's navy, in light and dark mode alike.
        let name = try XCTUnwrap(launchScreen["UIColorName"])
        let color = try XCTUnwrap(UIColor(named: name, in: .main, compatibleWith: nil))
        for style in [UIUserInterfaceStyle.light, .dark] {
            var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
            color.resolvedColor(with: UITraitCollection(userInterfaceStyle: style)).getRed(&red, green: &green, blue: &blue, alpha: &alpha)
            let navy = Palette.splash.base
            XCTAssertEqual(red * 255, CGFloat(navy.red), accuracy: 0.5)
            XCTAssertEqual(green * 255, CGFloat(navy.green), accuracy: 0.5)
            XCTAssertEqual(blue * 255, CGFloat(navy.blue), accuracy: 0.5)
            XCTAssertEqual(alpha, 1)
        }
        // The splash starts with its logo at the launch logo's size, in the middle of the screen.
        let logo = try XCTUnwrap(UIImage(named: try XCTUnwrap(launchScreen["UIImageName"]), in: .main, compatibleWith: nil))
        XCTAssertEqual(logo.size, CGSize(width: SplashMetrics.launchLogo, height: SplashMetrics.launchLogo))
        XCTAssertNotNil(UIImage(named: "Logo", in: .main, compatibleWith: nil))
    }

    func testEveryOnboardingPictureIsInTheApp() throws {
        for page in OnboardingPage.allCases {
            let image = try XCTUnwrap(UIImage(named: page.illustration, in: .main, compatibleWith: nil), page.illustration)
            // Drawn at 400 × 300.
            XCTAssertEqual(image.size.width / image.size.height, 4 / 3, accuracy: 0.01, page.illustration)
        }
    }

    @MainActor
    func testOnboardingShowsUntilFinishedThenStaysClosed() {
        UserDefaults.standard.removeObject(forKey: OnboardingRecord.key)
        let first = AppModel()
        XCTAssertTrue(first.showingOnboarding)
        first.finishOnboarding()
        XCTAssertFalse(first.showingOnboarding)
        XCTAssertFalse(AppModel().showingOnboarding, "Seen once, not shown on the next launch")
    }

    @MainActor
    func testOnboardingFollowsTheAppLanguage() {
        let model = AppModel()
        let saved = model.language
        defer { model.language = saved }
        model.language = "tr"
        XCTAssertEqual(model.onboardingStrings.primary(.offline), "Başlayın")
        model.language = "en"
        XCTAssertEqual(model.onboardingStrings.showAgain, "Show the introduction")
    }
}
