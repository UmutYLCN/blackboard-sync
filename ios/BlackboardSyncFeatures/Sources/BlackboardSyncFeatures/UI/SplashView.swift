import SwiftUI

/// The splash (design board, section 5): the logo on the app icon's navy with the name under it, the
/// same in light and dark mode. Its first frame is the launch screen (`UILaunchScreen`: the
/// `LaunchBackground` colour and the `LaunchLogo` image centred on the screen), so the hand-off from
/// the system shows no jump and no white flash; then `timeline` plays.
public struct SplashView: View {
    let logo: Image
    let timeline: SplashTimeline
    @State private var revealed = false

    public init(logo: Image, timeline: SplashTimeline) {
        self.logo = logo
        self.timeline = timeline
    }

    public var body: some View {
        ZStack {
            AppColor.splashBase
            // The glow behind the logo and the darker corners, faded in over the launch screen's flat colour.
            EllipticalGradient(stops: [.init(color: AppColor.splashGlow, location: 0),
                                       .init(color: AppColor.splashBase, location: 0.56),
                                       .init(color: AppColor.splashEdge, location: 1)],
                               center: UnitPoint(x: 0.5, y: 0.45), endRadiusFraction: 0.7)
                .opacity(revealed ? 1 : 0)
                .animation(.easeOut(duration: timeline.haloDuration), value: revealed)
            RadialGradient(colors: [AppColor.splashHalo.opacity(0.28), AppColor.splashHalo.opacity(0)],
                           center: .center, startRadius: 0, endRadius: SplashMetrics.halo * 0.48)
                .frame(width: SplashMetrics.halo, height: SplashMetrics.halo)
                .scaleEffect(revealed ? 1 : 0.6)
                .opacity(revealed ? 1 : 0)
                .animation(.easeOut(duration: timeline.haloDuration), value: revealed)
            logo.resizable().scaledToFit()
                .scaleEffect(revealed ? 1 : timeline.logoStartScale)
                .animation(.spring(duration: timeline.logoDuration, bounce: 0.35), value: revealed)
                .frame(width: SplashMetrics.logo, height: SplashMetrics.logo)
                // The name hangs below the logo, so the logo stays in the middle of the screen like the launch screen's.
                .overlay(alignment: .bottom) {
                    Text(verbatim: "Blackboard Sync")
                        .font(.system(size: SplashMetrics.wordmarkSize, weight: .bold))
                        .tracking(-0.4)
                        .foregroundStyle(.white)
                        .fixedSize()
                        .offset(y: revealed ? 0 : 10)
                        .opacity(revealed ? 1 : 0)
                        .alignmentGuide(.bottom) { $0[.top] - SplashMetrics.wordmarkGap }
                        .animation(.easeOut(duration: timeline.wordmarkDuration).delay(timeline.wordmarkDelay), value: revealed)
                }
        }
        .ignoresSafeArea()
        // Decorative and brief: VoiceOver and touches go to the screen underneath.
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .task {
            guard timeline.moves else { return }
            // One frame on the launch screen's picture first, then the motion.
            try? await Task.sleep(for: .milliseconds(16))
            revealed = true
        }
    }
}

#Preview("Splash") {
    SplashView(logo: Image(systemName: "folder.fill"), timeline: .standard(reduceMotion: false))
}
