import XCTest
@testable import BlackboardSyncFeatures

final class DesignTests: XCTestCase {
    /// WCAG AA for text: 4.5:1.
    private let textContrast = 4.5

    func testAccentTextIsReadableOnPagesAndCardsInBothModes() {
        XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.accentText.light, Palette.card.light), textContrast)
        XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.accentText.light, Palette.page.light), textContrast)
        XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.accentText.dark, Palette.card.dark), textContrast)
        XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.accentText.dark, Palette.page.dark), textContrast)
    }

    func testWhiteTextIsReadableOnTheSolidAccent() {
        XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.white, Palette.accent.light), textContrast)
        XCTAssertGreaterThanOrEqual(RGB.contrast(Palette.white, Palette.accent.dark), textContrast)
    }

    func testTheOldFixedBlueFailsOnDarkCards() {
        // Why dark mode needs its own accent text: the app's blue as text on a dark card.
        XCTAssertLessThan(RGB.contrast(RGB(0x265CF2), Palette.card.dark), textContrast)
    }

    func testContrastMatchesKnownValues() {
        XCTAssertEqual(RGB.contrast(RGB(0x000000), RGB(0xFFFFFF)), 21, accuracy: 0.01)
        XCTAssertEqual(RGB.contrast(RGB(0x777777), RGB(0xFFFFFF)), 4.48, accuracy: 0.01)
    }

    func testTopBarGeometry() {
        // 44 pt targets holding 36 pt circles with no gap leave 8 pt between circles.
        XCTAssertEqual(TopBarMetrics.target - TopBarMetrics.circle, 8)
        XCTAssertEqual(TopBarMetrics.margin, 24)
    }

    func testIconSetThreeNames() {
        XCTAssertEqual([AppIcon.pause, AppIcon.resume, AppIcon.settings, AppIcon.account],
                       ["pause.fill", "play.fill", "gearshape.fill", "person.crop.circle.fill"])
        XCTAssertEqual([AppIcon.folder, AppIcon.courses, AppIcon.announcements, AppIcon.calendar, AppIcon.sync],
                       ["folder.fill", "graduationcap.fill", "megaphone.fill", "calendar", "arrow.triangle.2.circlepath"])
    }
}

final class DisplayFormatTests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!
    /// 2026-11-11 10:43 UTC
    private let date = Date(timeIntervalSince1970: 1_794_393_780)

    func testTurkishDateIsTurkish() {
        let text = DisplayFormat.dateTime(date, language: .turkish, timeZone: utc, region: Locale.Region("TR"))
        XCTAssertTrue(text.contains("Kas"), text)
        XCTAssertTrue(text.contains("10:43"), text)
        XCTAssertFalse(text.contains("Nov"), text)
        XCTAssertFalse(text.contains(" at "), text)
    }

    func testTurkishDateStaysTurkishOnAnEnglishDevice() {
        let text = DisplayFormat.dateTime(date, language: .turkish, timeZone: utc, region: Locale.Region("US"))
        XCTAssertTrue(text.contains("Kas"), text)
        XCTAssertFalse(text.contains("Nov"), text)
    }

    func testEnglishDate() {
        let text = DisplayFormat.dateTime(date, language: .english, timeZone: utc, region: Locale.Region("US"))
        XCTAssertTrue(text.contains("Nov 11, 2026"), text)
        XCTAssertTrue(text.contains("10:43"), text)
    }

    func testEnglishPlurals() {
        XCTAssertEqual(DisplayFormat.count(0, one: "{n} error", other: "{n} errors"), "0 errors")
        XCTAssertEqual(DisplayFormat.count(1, one: "{n} error", other: "{n} errors"), "1 error")
        XCTAssertEqual(DisplayFormat.count(2, one: "{n} error", other: "{n} errors"), "2 errors")
    }

    func testTurkishCountsUseTheTranslation() {
        let turkish = ["{n} error": "{n} hata", "{n} errors": "{n} hata"]
        XCTAssertEqual(DisplayFormat.count(1, one: "{n} error", other: "{n} errors") { turkish[$0] ?? $0 }, "1 hata")
        XCTAssertEqual(DisplayFormat.count(3, one: "{n} error", other: "{n} errors") { turkish[$0] ?? $0 }, "3 hata")
    }
}
