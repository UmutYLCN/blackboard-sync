import SwiftUI

/// The few colors and sizes these pages need. The default follows the Mac app's main window
/// (`menubar/main_window.py`) with semantic system colors; the shell injects its own with
/// `.featureTheme(_:)`.
public struct FeatureTheme: Sendable {
    /// Selection, primary buttons.
    public var accent: Color
    /// Behind the page.
    public var pageBackground: Color
    /// A card (the Mac's `controlBackgroundColor` box).
    public var cardFill: Color
    /// A card's 1 pt border (`separatorColor`).
    public var cardBorder: Color
    /// Past-due day cards are tinted with this (`systemOrangeColor` at 12% / 45%).
    public var warning: Color
    public var secondaryText: Color
    public var cornerRadius: CGFloat
    /// Space around and between cards.
    public var spacing: CGFloat

    public init(accent: Color, pageBackground: Color, cardFill: Color, cardBorder: Color, warning: Color,
                secondaryText: Color, cornerRadius: CGFloat = 10, spacing: CGFloat = 12) {
        self.accent = accent
        self.pageBackground = pageBackground
        self.cardFill = cardFill
        self.cardBorder = cardBorder
        self.warning = warning
        self.secondaryText = secondaryText
        self.cornerRadius = cornerRadius
        self.spacing = spacing
    }

    public static let standard: FeatureTheme = {
        #if canImport(UIKit)
        FeatureTheme(accent: .accentColor, pageBackground: Color(uiColor: .systemGroupedBackground),
                     cardFill: Color(uiColor: .secondarySystemGroupedBackground),
                     cardBorder: Color(uiColor: .separator), warning: .orange, secondaryText: .secondary)
        #else
        FeatureTheme(accent: .accentColor, pageBackground: Color(nsColor: .windowBackgroundColor),
                     cardFill: Color(nsColor: .controlBackgroundColor),
                     cardBorder: Color(nsColor: .separatorColor), warning: .orange, secondaryText: .secondary)
        #endif
    }()
}

private struct FeatureThemeKey: EnvironmentKey {
    static let defaultValue = FeatureTheme.standard
}

extension EnvironmentValues {
    public var featureTheme: FeatureTheme {
        get { self[FeatureThemeKey.self] }
        set { self[FeatureThemeKey.self] = newValue }
    }
}

extension View {
    /// Draws these pages with the shell's theme.
    public func featureTheme(_ theme: FeatureTheme) -> some View {
        environment(\.featureTheme, theme)
    }
}

/// A rounded box like the Mac's `_card`; `warning` tints it orange like a past-due day.
struct Card<Content: View>: View {
    var warning = false
    var selected = false
    @ViewBuilder var content: Content
    @Environment(\.featureTheme) private var theme

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: theme.cornerRadius, style: .continuous)
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(shape.fill(warning ? theme.warning.opacity(0.12) : theme.cardFill))
            .overlay {
                shape.strokeBorder(selected ? theme.accent : warning ? theme.warning.opacity(0.45) : theme.cardBorder,
                                   lineWidth: selected ? 2 : 1)
            }
    }
}

/// The page title and the small hint under it (`MainWindow._header` + `_wrapping`).
struct PageHeader: View {
    let title: String
    let hint: String
    @Environment(\.featureTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.title2.bold())
            Text(hint).font(.subheadline).foregroundStyle(theme.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A list beside its detail when there is room (iPad full screen, landscape split view), a
/// list whose detail opens as a sheet when there is not (Slide Over, narrow split view).
struct MasterDetail<Master: View, Detail: View, Item: Identifiable>: View {
    @Binding var selection: Item.ID?
    let selected: Item?
    @ViewBuilder var master: Master
    @ViewBuilder var detail: (Item?) -> Detail
    let closeTitle: String
    @Environment(\.featureTheme) private var theme
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    private var wide: Bool { sizeClass != .compact }
    #else
    private let wide = true
    #endif

    var body: some View {
        if wide {
            HStack(spacing: 0) {
                master.frame(minWidth: 320, idealWidth: 420, maxWidth: 480)
                Divider()
                detail(selected).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .background(theme.pageBackground)
        } else {
            master
                .background(theme.pageBackground)
                .sheet(isPresented: Binding(get: { selected != nil }, set: { if !$0 { selection = nil } })) {
                    NavigationStack {
                        detail(selected)
                            .toolbar {
                                ToolbarItem(placement: .confirmationAction) {
                                    Button(closeTitle) { selection = nil }
                                }
                            }
                    }
                }
        }
    }
}

/// A short notice above a list (`data.message` on the Mac's calendar page).
struct Notice: View {
    let text: String
    var warning = false
    @Environment(\.featureTheme) private var theme

    var body: some View {
        Label {
            Text(text).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: warning ? "exclamationmark.triangle" : "info.circle")
                .foregroundStyle(warning ? theme.warning : theme.secondaryText)
        }
        .font(.subheadline)
        .foregroundStyle(theme.secondaryText)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
