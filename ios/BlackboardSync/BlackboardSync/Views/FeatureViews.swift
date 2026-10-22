import SwiftUI
import BlackboardSyncFeatures

struct AnnouncementsPage: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        FeaturePage(title: "Announcements", symbol: "megaphone") { features in
            AnnouncementsView(model: features.announcements).id(ObjectIdentifier(features.announcements))
        }
    }
}

struct DeadlinesPage: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        FeaturePage(title: "Calendar", symbol: "calendar") { features in
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
                        .buttonStyle(.borderedProminent).disabled(model.busy)
                }
            }
        }.background(Color(uiColor: .systemGroupedBackground))
    }
}

private struct ReconnectBar: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "person.crop.circle.badge.exclamationmark").foregroundStyle(.orange)
            Text(model.text("Session expired. Sign in again.")).font(.callout)
            Spacer(minLength: 8)
            Button(model.text("Reconnect")) { model.signIn() }.buttonStyle(.borderedProminent).disabled(model.busy)
        }
        .padding(.horizontal, 20).padding(.vertical, 10)
        .background(.bar)
    }
}

/// Home's two small cards, as on the Mac's main window: the newest announcements and the next four due dates.
struct HomeFeatureCards: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(spacing: 20) {
            if let features = model.features {
                HomeAnnouncements(page: features.announcements)
                HomeDeadlines(page: features.deadlines)
            } else {
                Card {
                    Label(model.text("Announcements"), systemImage: "megaphone").font(.headline)
                    signInHint
                }
                Card {
                    Label(model.text("Upcoming deadlines"), systemImage: "calendar").font(.headline)
                    signInHint
                }
            }
        }
        .task(id: model.features.map(ObjectIdentifier.init)) {
            await model.features?.announcements.loadIfNeeded()
            await model.features?.deadlines.loadIfNeeded()
        }
    }
    private var signInHint: some View {
        Text(model.text("Sign in to see announcements and due dates from your selected courses."))
            .font(.callout).foregroundStyle(.secondary)
    }
}

private struct HomeAnnouncements: View {
    @EnvironmentObject var model: AppModel
    let page: AnnouncementsViewModel
    var body: some View {
        Card {
            Label(page.strings.announcementsTab, systemImage: "megaphone").font(.headline)
            let latest = page.announcements.prefix(3)
            if latest.isEmpty {
                HomeCardState(phase: page.phase, message: page.message, empty: page.strings.announcementsEmpty,
                              loading: page.strings.loading)
            } else if let message = page.message {
                Text(message).font(.caption).foregroundStyle(.orange)
            }
            ForEach(Array(latest)) { announcement in
                VStack(alignment: .leading, spacing: 5) {
                    Text(page.detail(for: announcement)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    Text(announcement.title).font(.subheadline.weight(.medium)).lineLimit(2)
                }.accessibilityElement(children: .combine)
                Divider()
            }
            ViewAllButton(page: .announcements)
        }
    }
}

/// Home's line under the greeting: "1 deadline today · 3 this week" once the due dates are in.
struct HomeSubtitle: View {
    let page: DeadlinesViewModel
    var body: some View {
        if page.phase == .loaded, !page.subtitle.isEmpty {
            Text(page.subtitle).font(.title3).foregroundStyle(.secondary).padding(.top, -12)
        }
    }
}

private struct HomeDeadlines: View {
    @EnvironmentObject var model: AppModel
    let page: DeadlinesViewModel
    var body: some View {
        Card {
            Label(page.strings.upcomingDeadlines, systemImage: "calendar").font(.headline)
            let next = DeadlineCalendar.upcomingRows(page.page, limit: 4)
            if next.isEmpty {
                HomeCardState(phase: page.phase, message: page.error, empty: page.strings.noUpcomingDeadlines,
                              loading: page.strings.loading)
            } else if let error = page.error {
                Text(error).font(.caption).foregroundStyle(.orange)
            }
            ForEach(next) { row in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(row.title).font(.subheadline.weight(.medium)).lineLimit(2)
                        Text(row.course).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    Text(page.whenText(for: row)).font(.caption.weight(.semibold)).foregroundStyle(Color.appAccent)
                }.accessibilityElement(children: .combine)
                Divider()
            }
            ViewAllButton(page: .calendar, title: "Open calendar")
        }
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
            Text(message).font(.callout).foregroundStyle(phase == .loaded ? Color.secondary : Color.orange)
        } else {
            Text(empty).font(.callout).foregroundStyle(.secondary)
        }
    }
}
