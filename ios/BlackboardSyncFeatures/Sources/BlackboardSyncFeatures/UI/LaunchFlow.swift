import SwiftUI

/// What a launch shows over the app: the splash, then the introduction while `showingOnboarding` is
/// true (first launch, or opened again from Settings), then the app. The app is built underneath from
/// the start, so it is ready when the splash fades; it is hidden from VoiceOver while the
/// introduction covers it.
public struct LaunchFlow<Content: View>: View {
    let logo: Image
    let strings: OnboardingStrings
    @Binding var showingOnboarding: Bool
    /// Debug screenshots only: keeps the splash on screen.
    let holdSplash: Bool
    let finishOnboarding: () -> Void
    @ViewBuilder let content: Content
    @State private var splash = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(logo: Image, strings: OnboardingStrings, showingOnboarding: Binding<Bool>, holdSplash: Bool = false,
                finishOnboarding: @escaping () -> Void, @ViewBuilder content: () -> Content) {
        self.logo = logo
        self.strings = strings
        self._showingOnboarding = showingOnboarding
        self.holdSplash = holdSplash
        self.finishOnboarding = finishOnboarding
        self.content = content()
    }

    public var body: some View {
        let timeline = SplashTimeline.standard(reduceMotion: reduceMotion)
        ZStack {
            // Unseen under the introduction, and faded back in as it closes.
            content
                .opacity(showingOnboarding ? 0 : 1)
                .accessibilityHidden(showingOnboarding)
            if showingOnboarding {
                OnboardingView(strings: strings) {
                    withAnimation(.easeOut(duration: 0.3)) { finishOnboarding() }
                }
                .transition(.opacity)
                .accessibilityAddTraits(.isModal)
                .zIndex(1)
            }
            if splash {
                SplashView(logo: logo, timeline: timeline)
                    .transition(.opacity)
                    .zIndex(2)
            }
        }
        .task {
            guard !holdSplash else { return }
            try? await Task.sleep(for: .seconds(timeline.hold))
            withAnimation(.easeOut(duration: timeline.fade)) { splash = false }
        }
    }
}
