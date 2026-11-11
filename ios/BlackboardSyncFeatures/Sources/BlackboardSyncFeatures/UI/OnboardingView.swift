import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// The five-page introduction (design board, section 6): one picture, a short title and a sentence
/// per page, swiped or stepped with Continue, with the page indicator and the button under the text
/// and Skip always at the top right. The last page's button says Get started; it and Skip call `finish`.
public struct OnboardingView: View {
    let strings: OnboardingStrings
    let illustrations: Bundle
    let finish: () -> Void
    @State private var page: OnboardingPage = .files
    @AccessibilityFocusState private var focusedTitle: OnboardingPage?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// `illustrations` is the bundle holding the pages' pictures (`OnboardingPage.illustration`).
    public init(strings: OnboardingStrings, illustrations: Bundle = .main, finish: @escaping () -> Void) {
        self.strings = strings
        self.illustrations = illustrations
        self.finish = finish
    }

    /// The text column's width and the picture's, as drawn.
    private static let column: CGFloat = 500
    private static let picture: CGFloat = 400

    public var body: some View {
        GeometryReader { geometry in
            let column = min(Self.column, geometry.size.width - 2 * Spacing.page)
            ScrollView {
                VStack(spacing: 0) {
                    pages(column: column, screenWidth: geometry.size.width)
                    indicator.padding(.bottom, Spacing.xl)
                    Button(action: advance) {
                        Text(strings.primary(page)).frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.appPrimaryLarge)
                    .frame(maxWidth: 320)
                    .accessibilityIdentifier("onboarding.next")
                }
                .padding(.vertical, Spacing.xxl + TopBarMetrics.target)
                .frame(maxWidth: .infinity, minHeight: geometry.size.height)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .overlay(alignment: .topTrailing) {
            Button(strings.skip, action: finish)
                .buttonStyle(.appTertiary)
                .accessibilityLabel(strings.skipLabel)
                .accessibilityIdentifier("onboarding.skip")
                .padding(.top, Spacing.m)
                .padding(.trailing, Spacing.page)
        }
        .background(Self.background.ignoresSafeArea())
    }

    /// The pages, swiped across the whole screen. The tallest page, laid out unseen, sets the height,
    /// so the indicator and button stay put from page to page and in either language.
    private func pages(column: CGFloat, screenWidth: CGFloat) -> some View {
        ZStack {
            ForEach(OnboardingPage.allCases) { content($0, column: column).hidden() }
        }
        .overlay {
            TabView(selection: $page) {
                ForEach(OnboardingPage.allCases) { page in
                    content(page, column: column)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                        .tag(page)
                }
            }
            #if os(iOS)
            .tabViewStyle(.page(indexDisplayMode: .never))
            #endif
            .frame(width: screenWidth)
        }
    }

    private func content(_ page: OnboardingPage, column: CGFloat) -> some View {
        VStack(spacing: 0) {
            Image(page.illustration, bundle: illustrations)
                .resizable().scaledToFit()
                .frame(maxWidth: min(Self.picture, column))
                .padding(.bottom, Spacing.s)
                // The title and sentence say what the picture shows.
                .accessibilityHidden(true)
            VStack(spacing: Spacing.s) {
                Text(strings.title(page))
                    .font(.largeTitle.weight(.bold))
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityFocused($focusedTitle, equals: page)
                Text(strings.body(page))
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.bottom, Spacing.xl)
        }
        .frame(width: column)
    }

    /// The page indicator: a long accent dash for this page, dots for the others. VoiceOver reads
    /// "Page 2 of 5" and swipes up or down to change the page.
    private var indicator: some View {
        HStack(spacing: Spacing.xs) {
            ForEach(OnboardingPage.allCases) { dot in
                Capsule()
                    .fill(dot == page ? AnyShapeStyle(AppColor.accent) : AnyShapeStyle(.tertiary))
                    .frame(width: dot == page ? 22 : 8, height: 8)
            }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.2), value: page)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(strings.pageIndicator(page))
        .accessibilityAddTraits(.updatesFrequently)
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: if let next = page.next { show(next) }
            case .decrement: if let previous = page.previous { show(previous) }
            @unknown default: break
            }
        }
        .accessibilityIdentifier("onboarding.indicator")
    }

    private func advance() {
        switch OnboardingStep.after(page) {
        case .show(let next): show(next)
        case .finish: finish()
        }
    }

    /// Moves to a page, sliding unless Reduce Motion is on, and puts VoiceOver on its title.
    private func show(_ next: OnboardingPage) {
        if reduceMotion { page = next } else { withAnimation(.easeInOut(duration: 0.3)) { page = next } }
        focusedTitle = next
    }

    private static var background: Color {
        #if canImport(UIKit)
        Color(uiColor: .systemGroupedBackground)
        #else
        Color(nsColor: .windowBackgroundColor)
        #endif
    }
}

#Preview("Onboarding") {
    OnboardingView(strings: OnboardingStrings(.english)) {}
}

#Preview("Onboarding, Turkish") {
    OnboardingView(strings: OnboardingStrings(.turkish)) {}
}
