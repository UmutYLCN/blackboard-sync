import Foundation

// The five-page introduction shown once, between the splash and the first screen, and again from
// Settings. Everything it decides lives here: the pages and their copy, where the pager goes next,
// whether it has been seen, and the splash's timing.

/// The introduction's pages, in order (design board, section 6).
public enum OnboardingPage: Int, CaseIterable, Identifiable, Sendable {
    case files, courses, deadlines, announcements, offline

    public var id: Int { rawValue }

    /// The picture's name in the app's asset catalog (a vector asset, the same in light and dark mode).
    public var illustration: String {
        switch self {
        case .files: "OnboardingFiles"
        case .courses: "OnboardingCourses"
        case .deadlines: "OnboardingDeadlines"
        case .announcements: "OnboardingAnnouncements"
        case .offline: "OnboardingOffline"
        }
    }

    /// The page after this one, nil on the last.
    public var next: OnboardingPage? { OnboardingPage(rawValue: rawValue + 1) }
    public var previous: OnboardingPage? { OnboardingPage(rawValue: rawValue - 1) }
    public var isLast: Bool { next == nil }
    /// 1-based, for the page indicator.
    public var number: Int { rawValue + 1 }
}

/// What the primary button does on a page: move on, or close the introduction on the last page.
public enum OnboardingStep: Equatable, Sendable {
    case show(OnboardingPage)
    case finish

    public static func after(_ page: OnboardingPage) -> OnboardingStep {
        page.next.map { .show($0) } ?? .finish
    }
}

/// The introduction's copy in English and Turkish (formal "siz", like the rest of the app).
public struct OnboardingStrings: Sendable {
    public let language: FeatureLanguage

    public init(_ language: FeatureLanguage = .english) {
        self.language = language
    }

    public func tr(_ text: String) -> String {
        language == .english ? text : Self.turkish[text] ?? text
    }

    public func title(_ page: OnboardingPage) -> String {
        switch page {
        case .files: tr("All your course files, in one place")
        case .courses: tr("You choose the courses")
        case .deadlines: tr("Never miss a due date")
        case .announcements: tr("Every announcement in one list")
        case .offline: tr("Yours, and available offline")
        }
    }

    public func body(_ page: OnboardingPage) -> String {
        switch page {
        case .files: tr("Blackboard Sync downloads the files from your courses and keeps them tidy by term and course.")
        case .courses: tr("Tick the courses you want. Change your mind at any time; files you already have stay put.")
        case .deadlines: tr("Upcoming deadlines from all your courses, day by day, right on Home.")
        case .announcements: tr("What your instructors post in each course, without opening Blackboard.")
        case .offline: tr("Files stay on this iPad and open without internet. You sign in on your school’s own page; no password is stored and nothing is tracked.")
        }
    }

    /// The primary button: Continue, or Get started on the last page.
    public func primary(_ page: OnboardingPage) -> String { tr(page.isLast ? "Get started" : "Continue") }
    public var skip: String { tr("Skip") }
    /// VoiceOver label of Skip, which says what it skips.
    public var skipLabel: String { tr("Skip the introduction") }
    /// VoiceOver label of the page indicator: "Page 2 of 5".
    public func pageIndicator(_ page: OnboardingPage) -> String {
        tr("Page {n} of {total}")
            .replacingOccurrences(of: "{n}", with: String(page.number))
            .replacingOccurrences(of: "{total}", with: String(OnboardingPage.allCases.count))
    }
    /// The Settings row that opens the introduction again.
    public var showAgain: String { tr("Show the introduction") }

    static let turkish: [String: String] = [
        "All your course files, in one place": "Tüm ders dosyalarınız tek yerde",
        "You choose the courses": "Dersleri siz seçin",
        "Never miss a due date": "Teslim tarihlerini kaçırmayın",
        "Every announcement in one list": "Tüm duyurular tek listede",
        "Yours, and available offline": "Sizde kalır, çevrimdışı açılır",
        "Blackboard Sync downloads the files from your courses and keeps them tidy by term and course.":
            "Blackboard Sync derslerinizin dosyalarını indirir, dönem ve derse göre düzenli tutar.",
        "Tick the courses you want. Change your mind at any time; files you already have stay put.":
            "İstediğiniz dersleri işaretleyin. Seçiminizi istediğiniz zaman değiştirebilirsiniz; indirdiğiniz dosyalar yerinde kalır.",
        "Upcoming deadlines from all your courses, day by day, right on Home.":
            "Tüm derslerinizin yaklaşan teslim tarihleri, gün gün, Ana sayfada.",
        "What your instructors post in each course, without opening Blackboard.":
            "Hocalarınızın her derste paylaştıkları, Blackboard’u açmadan önünüzde.",
        "Files stay on this iPad and open without internet. You sign in on your school’s own page; no password is stored and nothing is tracked.":
            "Dosyalar bu iPad’de durur ve internetsiz açılır. Girişi okulunuzun kendi sayfasında yaparsınız; parola saklanmaz, hiçbir şey izlenmez.",
        "Continue": "Devam",
        "Get started": "Başlayın",
        "Skip": "Geç",
        "Skip the introduction": "Tanıtımı geç",
        "Page {n} of {total}": "Sayfa {n} / {total}",
        "Show the introduction": "Tanıtımı göster",
    ]
}

/// Whether the introduction has been seen, kept in the app's defaults. A later version of the pages
/// can raise `version` to show them once more.
public struct OnboardingRecord {
    public static let key = "onboardingSeenVersion"
    public static let version = 1
    private let defaults: UserDefaults

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    public var seen: Bool { defaults.integer(forKey: Self.key) >= Self.version }

    public func markSeen() { defaults.set(Self.version, forKey: Self.key) }

    /// Shown at launch until it has been seen. Debug UI tests pass `--ui-testing`, which skips it so
    /// they start on Home, and `--ui-testing-onboarding` to show it whatever was saved; the app passes
    /// no arguments in Release builds.
    public func showsOnLaunch(arguments: [String] = []) -> Bool {
        if arguments.contains("--ui-testing-onboarding") { return true }
        if arguments.contains("--ui-testing") { return false }
        return !seen
    }
}

/// Sizes shared by the launch screen and the in-app splash. The launch screen shows the logo at
/// `launchLogo` points in the middle of the screen; the splash starts from that same frame and grows
/// the logo to `logo`, so nothing jumps when the app takes over.
public enum SplashMetrics {
    public static let logo: CGFloat = 196
    /// The `LaunchLogo` asset's size in points.
    public static let launchLogo: CGFloat = 168
    public static let wordmarkGap: CGFloat = 14
    public static let wordmarkSize: CGFloat = 30
    public static let halo: CGFloat = 330
}

/// The splash's motion after the launch screen: the logo grows from the launch frame's size, the halo
/// and the name come in, then the splash fades to the app. With Reduce Motion nothing moves; the launch
/// frame only fades to the app.
public struct SplashTimeline: Equatable, Sendable {
    public let moves: Bool
    /// The logo's scale on the first frame, the launch screen's logo size over the splash's.
    public let logoStartScale: CGFloat
    public let logoDuration: Double
    public let wordmarkDelay: Double
    public let wordmarkDuration: Double
    public let haloDuration: Double
    /// From the first frame until the fade starts.
    public let hold: Double
    public let fade: Double

    public var total: Double { hold + fade }

    public static func standard(reduceMotion: Bool) -> SplashTimeline {
        let start = SplashMetrics.launchLogo / SplashMetrics.logo
        return reduceMotion
            ? SplashTimeline(moves: false, logoStartScale: start, logoDuration: 0, wordmarkDelay: 0, wordmarkDuration: 0,
                             haloDuration: 0, hold: 0.15, fade: 0.3)
            : SplashTimeline(moves: true, logoStartScale: start, logoDuration: 0.8, wordmarkDelay: 0.28, wordmarkDuration: 0.6,
                             haloDuration: 0.9, hold: 0.95, fade: 0.35)
    }
}
