import SwiftUI
import BlackboardSyncFeatures

struct AnnouncementsPage: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        FeaturePage(title: "Announcements", symbol: AppIcon.announcements) { features in
            AnnouncementsView(model: features.announcements).id(ObjectIdentifier(features.announcements))
        }
    }
}

struct DeadlinesPage: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        FeaturePage(title: "Calendar", symbol: AppIcon.calendar) { features in
            DeadlinesView(model: features.deadlines).id(ObjectIdentifier(features.deadlines))
        }
    }
}

/// A package page once signed in; otherwise the sign-in or reconnect step it needs.
private struct FeaturePage<Content: View>: View {
    @EnvironmentObject var model: AppModel
    let title: String
    let symbol: String
    @ViewBuilder var content: (FeatureModels) -> Content
    var body: some View {
        Group {
            if let features = model.features {
                content(features)
                    .safeAreaInset(edge: .top, spacing: 0) { if model.needsSignIn { ReconnectBar() } }
            } else if model.hasStoredSession && model.busy && !model.needsSignIn {
                ProgressView(model.text(model.status)).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView {
                    Label(model.text(title), systemImage: symbol)
                } description: {
                    Text(model.text("Sign in to see announcements and due dates from your selected courses."))
                } actions: {
                    Button(model.text(model.needsSignIn ? "Reconnect" : "Sign in to Blackboard")) { model.signIn() }
                        .buttonStyle(.appPrimaryLarge).disabled(model.busy)
                }
            }
        }.background(Color(uiColor: .systemGroupedBackground))
            .appTopBar(model.text(title))
    }
}

private struct ReconnectBar: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "person.crop.circle.badge.exclamationmark").foregroundStyle(.orange)
            Text(model.text("Session expired. Sign in again.")).font(.callout)
            Spacer(minLength: 8)
            Button(model.text("Reconnect")) { model.signIn() }.buttonStyle(.appPrimary).disabled(model.busy)
        }
        .padding(.horizontal, Spacing.l).padding(.vertical, Spacing.xs)
        .background(.bar)
    }
}

/// Home's middle row (board pick H1): the next four due dates and the newest announcements side by
/// side, one above the other when the page is too narrow for both (portrait with the sidebar open) or
/// the text is set to an accessibility size.
struct HomeFeatureCards: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var width: CGFloat = 0
    /// Two cards of at least 312 pt each and the gap between them.
    static let sideBySideWidth: CGFloat = 640
    var body: some View {
        Group {
            if width >= Self.sideBySideWidth && !typeSize.isAccessibilitySize {
                HStack(alignment: .top, spacing: Spacing.m) { deadlines; announcements }
            } else {
                VStack(spacing: Spacing.m) { deadlines; announcements }
            }
        }
        .frame(maxWidth: .infinity)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .task(id: model.features.map(ObjectIdentifier.init)) {
            await model.features?.announcements.loadIfNeeded()
            await model.features?.deadlines.loadIfNeeded()
        }
    }

    @ViewBuilder private var deadlines: some View {
        if let features = model.features { HomeDeadlines(page: features.deadlines) }
        else { signedOut("Upcoming deadlines", symbol: AppIcon.calendar) }
    }
    @ViewBuilder private var announcements: some View {
        if let features = model.features { HomeAnnouncements(page: features.announcements) }
        else { signedOut("Announcements", symbol: AppIcon.announcements) }
    }
    private func signedOut(_ title: String, symbol: String) -> some View {
        Card {
            HomeCardHeader(title: model.text(title), symbol: symbol) { EmptyView() }
            Text(model.text("Sign in to see announcements and due dates from your selected courses."))
                .font(.callout).foregroundStyle(.secondary)
        }
    }
}

/// A Home card's title with its symbol, and its "View all" pill at the right.
private struct HomeCardHeader<Trailing: View>: View {
    let title: String
    let symbol: String
    @ViewBuilder var trailing: Trailing
    var body: some View {
        HStack(spacing: Spacing.xs) {
            Image(systemName: symbol).foregroundStyle(AppColor.accentText).accessibilityHidden(true)
            Text(title).font(.headline).lineLimit(2).accessibilityAddTraits(.isHeader)
            Spacer(minLength: Spacing.xs)
            // The pill keeps its full label; a long title wraps instead.
            trailing.fixedSize()
        }
    }
}

private struct HomeAnnouncements: View {
    @EnvironmentObject var model: AppModel
    let page: AnnouncementsViewModel
    var body: some View {
        Card {
            HomeCardHeader(title: page.strings.announcementsTab, symbol: AppIcon.announcements) {
                ViewAllButton(page: .announcements)
            }
            let latest = page.announcements.prefix(3)
            if latest.isEmpty {
                HomeCardState(phase: page.phase, message: page.message, empty: page.strings.announcementsEmpty,
                              loading: page.strings.loading)
            } else if let message = page.message {
                Text(message).font(.caption).foregroundStyle(AppColor.warning)
            }
            VStack(spacing: 0) {
                ForEach(Array(latest.enumerated()), id: \.element.id) { index, announcement in
                    if index > 0 { Divider().padding(.leading, 48) }
                    HStack(spacing: Spacing.s) {
                        HomeTile(width: 36) {
                            Text(HomeFormat.courseInitials(announcement.course, language: model.language))
                                .font(.caption.weight(.bold)).foregroundStyle(AppColor.accentText)
                        }
                        VStack(alignment: .leading, spacing: 3) {
                            Text(announcement.title).font(.subheadline.weight(.medium)).lineLimit(2)
                            Text(page.detail(for: announcement)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, Spacing.xs)
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }
}

/// Home's line under the greeting: "1 deadline today · 3 this week" once the due dates are in.
struct HomeSubtitle: View {
    let page: DeadlinesViewModel
    var body: some View {
        if page.phase == .loaded, !page.subtitle.isEmpty {
            Text(page.subtitle).font(.title3).foregroundStyle(.secondary).padding(.top, -Spacing.xs)
        }
    }
}

private struct HomeDeadlines: View {
    @EnvironmentObject var model: AppModel
    let page: DeadlinesViewModel
    var body: some View {
        Card {
            HomeCardHeader(title: page.strings.upcomingDeadlines, symbol: AppIcon.calendar) {
                ViewAllButton(page: .calendar, title: "Open calendar")
            }
            let next = DeadlineCalendar.upcomingRows(page.page, limit: 4)
            if next.isEmpty {
                HomeCardState(phase: page.phase, message: page.error, empty: page.strings.noUpcomingDeadlines,
                              loading: page.strings.loading)
            } else if let error = page.error {
                Text(error).font(.caption).foregroundStyle(AppColor.warning)
            }
            VStack(spacing: 0) {
                ForEach(Array(next.enumerated()), id: \.element.id) { index, row in
                    if index > 0 { Divider().padding(.leading, 56) }
                    let today = DisplayFormat.isToday(row.day, timeZone: page.timeZone)
                    HStack(spacing: Spacing.s) {
                        // The day and month in a tile, orange when it is due today.
                        HomeTile(width: 44, fill: today ? AppColor.warning.opacity(0.17) : AppColor.neutralFill) {
                            VStack(spacing: 1) {
                                Text(String(row.day.day)).font(.headline).monospacedDigit()
                                Text(DisplayFormat.shortMonth(row.day.month, language: page.strings.language))
                                    .font(.system(size: 9.5, weight: .bold))
                                    .foregroundStyle(today ? AppColor.warning : .secondary)
                            }
                        }
                        VStack(alignment: .leading, spacing: 3) {
                            Text(row.title).font(.subheadline.weight(.medium)).lineLimit(2)
                            Text(row.course).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer(minLength: Spacing.xs)
                        Text(page.whenText(for: row)).font(.caption.weight(.semibold))
                            .foregroundStyle(today ? AppColor.warning : AppColor.accentText)
                    }
                    .padding(.vertical, Spacing.xs)
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }
}

/// A small rounded square holding a row's date or course initials.
private struct HomeTile<Content: View>: View {
    var width: CGFloat
    var fill: Color = AppColor.accentSoft
    @ViewBuilder var content: Content
    var body: some View {
        content
            .frame(width: width, height: width)
            .background(fill, in: RoundedRectangle(cornerRadius: Radius.small))
            .accessibilityHidden(true)
    }
}

enum HomeFormat {
    /// "CS" for "CSE301 Database Management": the first two letters of the course's first word.
    static func courseInitials(_ course: String, language: String) -> String {
        let word = course.split(separator: " ").first.map(String.init) ?? ""
        let letters = word.filter(\.isLetter).prefix(2)
        return letters.isEmpty ? "?" : String(letters).uppercased(with: Locale(identifier: language))
    }
}

private struct HomeCardState: View {
    let phase: LoadPhase
    let message: String?
    let empty: String
    let loading: String
    var body: some View {
        if phase == .idle || phase == .loading {
            ProgressView(loading).frame(maxWidth: .infinity, alignment: .leading)
        } else if let message {
            Text(message).font(.callout).foregroundStyle(phase == .loaded ? Color.secondary : AppColor.warning)
        } else {
            Text(empty).font(.callout).foregroundStyle(.secondary)
        }
    }
}
