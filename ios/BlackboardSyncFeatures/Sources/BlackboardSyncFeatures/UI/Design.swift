import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

// The app's shared look: colours, spacing, corner radii, button tiers, the top bar's circles and
// icon names. The shell and these pages use these instead of literal values.

/// An sRGB colour as 0–255 components, so the palette's contrast can be checked in tests.
public struct RGB: Sendable, Equatable {
    public let red: UInt8
    public let green: UInt8
    public let blue: UInt8

    /// `RGB(0x265CF2)`
    public init(_ hex: UInt32) {
        red = UInt8((hex >> 16) & 0xFF)
        green = UInt8((hex >> 8) & 0xFF)
        blue = UInt8(hex & 0xFF)
    }

    /// WCAG 2 relative luminance.
    public var luminance: Double {
        func channel(_ value: UInt8) -> Double {
            let c = Double(value) / 255
            return c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)
    }

    /// WCAG 2 contrast ratio between two opaque colours, 1 to 21.
    public static func contrast(_ a: RGB, _ b: RGB) -> Double {
        let (light, dark) = a.luminance > b.luminance ? (a.luminance, b.luminance) : (b.luminance, a.luminance)
        return (light + 0.05) / (dark + 0.05)
    }
}

/// The palette behind `AppColor`, as light/dark pairs.
public enum Palette {
    /// Solid accent: selection, primary buttons, the paused circle. White text sits on it.
    public static let accent = (light: RGB(0x265CF2), dark: RGB(0x346CF6))
    /// Accent as text or a glyph on a page or card. The app's blue is too dark as text on dark
    /// cards, so dark mode uses a lighter blue.
    public static let accentText = (light: RGB(0x265CF2), dark: RGB(0x739FFF))
    /// The system backgrounds the accent sits on: grouped page and its cards.
    public static let page = (light: RGB(0xF2F2F7), dark: RGB(0x000000))
    public static let card = (light: RGB(0xFFFFFF), dark: RGB(0x1C1C1E))
    public static let white = RGB(0xFFFFFF)
    /// The launch screen and splash: the app icon's navy, the same in light and dark mode. `base` is
    /// also the `LaunchBackground` colour asset; the splash brightens it to `glow` behind the logo,
    /// darkens it to `edge` at the corners and lights the logo with a `halo`.
    public static let splash = (base: RGB(0x141D31), glow: RGB(0x1D2E52), edge: RGB(0x0F1626), halo: RGB(0x3DB4FF))
}

/// The app's colours; each follows light and dark mode.
public enum AppColor {
    public static let accent = Color.adaptive(light: Palette.accent.light, dark: Palette.accent.dark)
    public static let accentText = Color.adaptive(light: Palette.accentText.light, dark: Palette.accentText.dark)
    /// The tinted fill behind accent text: secondary buttons, the account initials.
    public static let accentSoft = Color.adaptive(light: Palette.accent.light, lightAlpha: 0.14,
                                                  dark: RGB(0x4C7DFF), darkAlpha: 0.24)
    /// The plain fill of a neutral control (the system's tertiary fill).
    public static let neutralFill = Color.adaptive(light: RGB(0x767680), lightAlpha: 0.12,
                                                   dark: RGB(0x767680), darkAlpha: 0.24)
    public static let warning = Color.orange
    /// The splash's navy (`Palette.splash`), which does not change with the appearance.
    public static let splashBase = Color.fixed(Palette.splash.base)
    public static let splashGlow = Color.fixed(Palette.splash.glow)
    public static let splashEdge = Color.fixed(Palette.splash.edge)
    public static let splashHalo = Color.fixed(Palette.splash.halo)
    /// Course marks (the Calendar's dots), told apart by colour; system colours, so each follows
    /// light and dark mode. Orange comes late because it also marks what is due today.
    public static let courses: [Color] = [accentText, .green, .purple, .pink, .teal, .orange, .brown]

    /// The colour of the course at `index` in `DeadlineWeek.courseColors`; repeats after the last.
    public static func course(_ index: Int) -> Color {
        courses[((index % courses.count) + courses.count) % courses.count]
    }
}

extension Color {
    /// A colour that switches between two values with the appearance.
    static func adaptive(light: RGB, lightAlpha: Double = 1, dark: RGB, darkAlpha: Double = 1) -> Color {
        #if canImport(UIKit)
        Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? dark.uiColor(darkAlpha) : light.uiColor(lightAlpha)
        })
        #elseif canImport(AppKit)
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark.nsColor(darkAlpha) : light.nsColor(lightAlpha)
        })
        #endif
    }

    /// A colour that stays the same in light and dark mode.
    static func fixed(_ rgb: RGB) -> Color {
        Color(.sRGB, red: Double(rgb.red) / 255, green: Double(rgb.green) / 255, blue: Double(rgb.blue) / 255)
    }
}

extension RGB {
    #if canImport(UIKit)
    func uiColor(_ alpha: Double) -> UIColor {
        UIColor(red: CGFloat(red) / 255, green: CGFloat(green) / 255, blue: CGFloat(blue) / 255, alpha: alpha)
    }
    #elseif canImport(AppKit)
    func nsColor(_ alpha: Double) -> NSColor {
        NSColor(srgbRed: CGFloat(red) / 255, green: CGFloat(green) / 255, blue: CGFloat(blue) / 255, alpha: alpha)
    }
    #endif
}

/// Spacing on a 4 pt grid.
public enum Spacing {
    public static let xxs: CGFloat = 4
    public static let xs: CGFloat = 8
    public static let s: CGFloat = 12
    public static let m: CGFloat = 16
    public static let l: CGFloat = 20
    public static let xl: CGFloat = 24
    public static let xxl: CGFloat = 32
    /// Page margin, and the top bar's distance from the screen edges.
    public static let page: CGFloat = xl
}

/// Corner radii.
public enum Radius {
    /// Small tiles and file badges.
    public static let small: CGFloat = 10
    /// Rounded rows and fields.
    public static let control: CGFloat = 14
    /// Cards.
    public static let card: CGFloat = 18
}

/// SF Symbol names for the app's roles (icon set 3, bold filled).
public enum AppIcon {
    public static let pause = "pause.fill"
    public static let resume = "play.fill"
    public static let settings = "gearshape.fill"
    public static let account = "person.crop.circle.fill"
    public static let sync = "arrow.triangle.2.circlepath"
    public static let folder = "folder.fill"
    public static let courses = "graduationcap.fill"
    public static let calendar = "calendar"
    public static let announcements = "megaphone.fill"
}

// MARK: Buttons

/// The app's three button tiers, all capsules: primary (solid accent, white text) for the one main
/// action on a screen, secondary (tinted accent) for other actions, tertiary (neutral grey) for quiet ones.
public struct AppButtonStyle: ButtonStyle {
    public enum Tier: Sendable { case primary, secondary, tertiary }
    public var tier: Tier
    /// 44 pt high instead of 36, for a screen's main call to action.
    public var large: Bool

    public init(_ tier: Tier, large: Bool = false) {
        self.tier = tier
        self.large = large
    }

    public func makeBody(configuration: Configuration) -> some View {
        AppButton(configuration: configuration, tier: tier, large: large)
    }

    private struct AppButton: View {
        let configuration: Configuration
        let tier: Tier
        let large: Bool
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            configuration.label
                .font(large ? .body.weight(.semibold) : .subheadline.weight(.bold))
                .foregroundStyle(ink)
                .lineLimit(1)
                .padding(.horizontal, large ? Spacing.xl : Spacing.l)
                .frame(minHeight: large ? 44 : 36)
                .background(fill, in: Capsule())
                .overlay(Capsule().fill(Color.primary.opacity(configuration.isPressed ? 0.12 : 0)))
                .opacity(isEnabled ? 1 : 0.45)
                .contentShape(Capsule())
        }

        private var ink: Color {
            switch tier {
            case .primary: .white
            case .secondary: AppColor.accentText
            case .tertiary: .primary
            }
        }

        private var fill: Color {
            switch tier {
            case .primary: AppColor.accent
            case .secondary: AppColor.accentSoft
            case .tertiary: AppColor.neutralFill
            }
        }
    }
}

extension ButtonStyle where Self == AppButtonStyle {
    public static var appPrimary: AppButtonStyle { AppButtonStyle(.primary) }
    public static var appPrimaryLarge: AppButtonStyle { AppButtonStyle(.primary, large: true) }
    public static var appSecondary: AppButtonStyle { AppButtonStyle(.secondary) }
    public static var appTertiary: AppButtonStyle { AppButtonStyle(.tertiary) }
}

// MARK: Top bar

/// The top bar's sizes: one 50 pt row, 44 pt tap targets with no gap, each holding a 36 pt circle
/// (so circles sit 8 pt apart), 24 pt from the screen edges.
public enum TopBarMetrics {
    public static let target: CGFloat = 44
    public static let circle: CGFloat = 36
    public static let glyph: CGFloat = 17
    /// Pause and play are optically heavy.
    public static let playGlyph: CGFloat = 15
    public static let initials: CGFloat = 13
    public static let margin: CGFloat = Spacing.page
}

/// A top-bar control: the label centred in a 36 pt circle inside a 44 pt tap target.
public struct TopBarCircleStyle: ButtonStyle {
    public enum Kind: Sendable {
        /// Neutral grey circle, primary glyph.
        case plain
        /// Solid accent circle, white glyph (Resume while paused).
        case filled
        /// Tinted accent circle, accent text (the account initials).
        case tinted
    }
    public var kind: Kind

    public init(_ kind: Kind = .plain) { self.kind = kind }

    public func makeBody(configuration: Configuration) -> some View {
        TopBarCircle(kind: kind, pressed: configuration.isPressed) { configuration.label }
    }
}

/// The circle itself, also used as a `Menu` label.
public struct TopBarCircle<Label: View>: View {
    let kind: TopBarCircleStyle.Kind
    var pressed = false
    @ViewBuilder var label: Label
    @Environment(\.isEnabled) private var isEnabled

    public init(kind: TopBarCircleStyle.Kind, pressed: Bool = false, @ViewBuilder label: () -> Label) {
        self.kind = kind
        self.pressed = pressed
        self.label = label()
    }

    public var body: some View {
        label
            .labelStyle(.iconOnly)
            .foregroundStyle(ink)
            .frame(width: TopBarMetrics.circle, height: TopBarMetrics.circle)
            .background(fill, in: Circle())
            .overlay(Circle().fill(Color.primary.opacity(pressed ? 0.14 : 0)))
            .opacity(isEnabled ? 1 : 0.4)
            .frame(width: TopBarMetrics.target, height: TopBarMetrics.target)
            .contentShape(Rectangle())
    }

    private var ink: Color {
        switch kind {
        case .plain: .primary
        case .filled: .white
        case .tinted: AppColor.accentText
        }
    }

    private var fill: Color {
        switch kind {
        case .plain: AppColor.neutralFill
        case .filled: AppColor.accent
        case .tinted: AppColor.accentSoft
        }
    }
}

/// The page title on the top bar's centre line: 28 pt bold, one line, shrinking to 80% before truncating.
public struct TopBarTitle: View {
    let text: String

    public init(_ text: String) { self.text = text }

    public var body: some View {
        Text(text)
            .font(.system(size: 28, weight: .bold))
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .accessibilityAddTraits(.isHeader)
    }
}
