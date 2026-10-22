import SwiftUI
import QuickLook

enum AppPage: String, Hashable { case home, activity, announcements, courses, calendar, library }

private struct OpenPageKey: EnvironmentKey { static let defaultValue: (AppPage) -> Void = { _ in } }
extension EnvironmentValues {
    /// Switches the sidebar to a page, like the Mac's "View all" and "Open calendar".
    var openPage: (AppPage) -> Void {
        get { self[OpenPageKey.self] }
        set { self[OpenPageKey.self] = newValue }
    }
}

struct RootView: View {
    @EnvironmentObject var model: AppModel
    @State private var page: AppPage? = .home
    var body: some View {
        NavigationSplitView {
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    Image("Logo").resizable().scaledToFit().frame(width: 36, height: 44)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Blackboard Sync").font(.headline)
                        Text("iPad · 0.1").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                }.padding(20)
                List(selection: $page) {
                    // The Mac's one big rounded "Open folder" button above the sections.
                    NavigationLink(value: AppPage.library) {
                        Label(model.text("Open folder"), systemImage: "folder").padding(.vertical, 8)
                    }
                    .listRowBackground(RoundedRectangle(cornerRadius: 16).fill(.quaternary).padding(.vertical, 2))
                    .accessibilityIdentifier("sidebar.folder")
                    Section {
                        NavigationLink(value: AppPage.home) { Label(model.text("Home"), systemImage: "house") }
                        NavigationLink(value: AppPage.activity) { Label(model.text("Sync activity"), systemImage: "arrow.triangle.2.circlepath") }
                        NavigationLink(value: AppPage.announcements) { Label(model.text("Announcements"), systemImage: "megaphone") }
                            .accessibilityIdentifier("sidebar.announcements")
                        NavigationLink(value: AppPage.courses) {
                            HStack {
                                Label(model.text("Courses"), systemImage: "books.vertical")
                                Spacer(minLength: 8)
                                if let courseCount { Text(courseCount).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                        NavigationLink(value: AppPage.calendar) { Label(model.text("Calendar"), systemImage: "calendar") }
                            .accessibilityIdentifier("sidebar.calendar")
                    }
                }.listStyle(.sidebar)
            }
            .navigationSplitViewColumnWidth(min: 225, ideal: 255, max: 300)
            .toolbar(.hidden, for: .navigationBar)
        } detail: {
            NavigationStack {
                Group {
                    switch page ?? .home {
                    case .home: HomeView()
                    case .activity: ActivityView()
                    case .announcements: AnnouncementsPage()
                    case .courses: CoursesView()
                    case .calendar: DeadlinesPage()
                    case .library: FileBrowser(folder: "", title: model.text("University"))
                    }
                }
                .toolbar {
                    // The Mac's top bar: Pause / Resume, Settings and the account, at the right of every page.
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        PauseButton()
                        Button { model.showingSettings = true } label: { Label(model.text("Settings"), systemImage: "gearshape") }
                        AccountMenu()
                    }
                }
            }
            .environment(\.openPage) { page = $0 }
        }
        .tint(Color.appAccent)
        .featureTheme(.app)
        .sheet(isPresented: $model.showingSettings, onDismiss: {
            if model.loginAfterSettings { model.loginAfterSettings = false; model.signIn() }
        }) { SettingsView().environmentObject(model) }
        .sheet(isPresented: $model.showingLogin) { SignInView().environmentObject(model) }
    }
    /// "4/5" beside Courses while some course is unticked, as on the Mac; nothing otherwise.
    private var courseCount: String? {
        let all = model.courses.count, ticked = model.courses.filter { model.selected.contains($0.id) }.count
        return ticked == all ? nil : "\(ticked)/\(all)"
    }
}

struct PauseButton: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Button { model.togglePause() } label: {
            Label(model.text(model.paused ? "Resume syncing" : "Pause syncing"),
                  systemImage: model.paused ? "play.circle.fill" : "pause.circle")
        }
        .foregroundStyle(model.paused ? Color.appAccent : Color.secondary)
        .disabled(!model.canTogglePause)
        .accessibilityIdentifier("toolbar.pause")
    }
}

/// The Mac's account control: initials in a circle, opening who is signed in, sign in or out, and Settings.
struct AccountMenu: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Menu {
            Section {
                Button {} label: { Label(header, systemImage: "person.crop.circle") }.disabled(true)
                if model.hasSession, let host = URL(string: model.tenantText)?.host {
                    Button {} label: { Label(host, systemImage: "building.columns") }.disabled(true)
                }
            }
            Section {
                if model.hasSession || model.hasStoredSession {
                    if model.needsSignIn {
                        Button(model.text("Reconnect")) { model.signIn() }.disabled(model.busy)
                    }
                    Button(model.text("Sign out"), role: .destructive) { model.signOut() }.disabled(model.busy && !model.syncing)
                } else {
                    Button(model.text(model.needsSignIn ? "Reconnect" : "Sign in to Blackboard")) { model.signIn() }.disabled(model.busy)
                }
                Button { model.showingSettings = true } label: { Label(model.text("Settings"), systemImage: "gearshape") }
            }
        } label: {
            Text(signedIn ? AppModel.initials(model.accountName, language: model.language) : "!")
                .font(.footnote.weight(.bold)).foregroundStyle(warning ? Color.orange : Color.appAccent)
                .frame(width: 32, height: 32)
                .background((warning ? Color.orange : Color.appAccent).opacity(0.18), in: Circle())
        }
        .accessibilityLabel(Text(signedIn ? model.accountName : model.text(model.needsSignIn ? "Sign-in needed" : "Not signed in")))
        .accessibilityIdentifier("toolbar.account")
    }
    private var signedIn: Bool { !model.accountName.isEmpty && !model.needsSignIn }
    private var warning: Bool { !signedIn }
    private var header: String {
        if signedIn { return model.text("Signed in as {name}").replacingOccurrences(of: "{name}", with: model.accountName) }
        return model.text(model.needsSignIn ? "Your session expired; sign in again." : "Not signed in yet.")
    }
}

struct ComingSoon: View {
    @EnvironmentObject var model: AppModel
    let title: String
    let symbol: String
    var body: some View {
        HStack(spacing: 10) {
            Label(model.text(title), systemImage: symbol)
            Spacer(minLength: 8)
            Text(model.text("Coming soon")).font(.caption2.weight(.medium)).padding(.horizontal, 7).padding(.vertical, 4)
                .background(.quaternary, in: Capsule())
        }.foregroundStyle(.secondary).opacity(0.75)
            .accessibilityElement(children: .combine).accessibilityAddTraits(.isStaticText)
            .allowsHitTesting(false)
    }
}

struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 18) { content }
            .frame(maxWidth: .infinity, alignment: .leading).padding(22)
            .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(.primary.opacity(0.055), lineWidth: 1))
    }
}

/// The Mac's rounded "View all" button: a capsule 36 pt high with a bold title, tinted with the accent;
/// `neutral` (gray) is for the status card's own button.
struct PillButtonStyle: ButtonStyle {
    var neutral = false
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        let ink = neutral ? Color.primary : Color.appAccent
        configuration.label
            .font(.subheadline.weight(.bold)).foregroundStyle(ink).lineLimit(1)
            .padding(.horizontal, 20).frame(minHeight: 36)
            .background(ink.opacity(neutral ? 0.1 : 0.22), in: Capsule())
            .overlay(Capsule().fill(Color.primary.opacity(configuration.isPressed ? 0.1 : 0)))
            .opacity(isEnabled ? 1 : 0.45)
            .contentShape(Capsule())
    }
}
extension ButtonStyle where Self == PillButtonStyle {
    static var pill: PillButtonStyle { PillButtonStyle() }
    static var neutralPill: PillButtonStyle { PillButtonStyle(neutral: true) }
}

/// The Mac's status card: the state symbol, the state in large type and the last sync, with at most one
/// button at the top right. Home also lists the last files in it.
struct StatusCard: View {
    @EnvironmentObject var model: AppModel
    var recent: Bool = false
    @State private var preview: URL?
    @State private var previewError: String?
    var body: some View {
        Card {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: symbol.name).font(.system(size: 26)).foregroundStyle(symbol.tint).frame(width: 32)
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.text(model.displayStatus)).font(.title.weight(.light))
                    if let last = model.library.lastSync {
                        Text(model.text("Last synced") + ": " + last.formatted(date: .abbreviated, time: .shortened)).font(.callout).foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 8)
                action
            }
            if model.paused && !model.syncing {
                Text(model.text("Syncing is paused. Resume to sync again.")).font(.callout).foregroundStyle(.secondary)
            }
            if model.syncing {
                if model.progress.discovering { ProgressView(model.text("Finding files…")) }
                else {
                    ProgressView(value: Double(model.progress.completed), total: Double(max(1, model.progress.discovered)))
                    Text("\(model.progress.completed) / \(model.progress.discovered) · \(model.progress.currentName)").font(.caption).lineLimit(2)
                }
            }
            if model.progress.completed > 0 {
                Text("\(model.progress.downloaded) " + model.text("downloaded") + " · \(model.progress.unchanged) " + model.text("unchanged") + " · \(model.progress.skipped) " + model.text("skipped") + " · \(model.progress.failed) " + model.text("errors"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.errorMessage {
                Text(model.text(error)).font(.callout).foregroundStyle(.orange).textSelection(.enabled)
            }
            if recent { recentFiles }
            Text(model.text("Keep Blackboard Sync open while syncing. Completed files stay available offline."))
                .font(.caption).foregroundStyle(.secondary)
        }.quickLookPreview($preview)
    }

    private var symbol: (name: String, tint: Color) {
        if model.syncing { return ("arrow.triangle.2.circlepath.icloud", .blue) }
        if model.paused { return ("pause.circle", .secondary) }
        if model.needsSignIn || !model.hasSession { return ("person.crop.circle.badge.exclamationmark", .orange) }
        if retry { return ("exclamationmark.icloud", .orange) }
        return (model.status == "Up to date" ? "checkmark.icloud" : "icloud", model.status == "Up to date" ? .green : .blue)
    }
    private var retry: Bool {
        model.status == "Sync did not finish" || model.status.hasPrefix("Cancelled") || model.library.interrupted
    }

    /// What the state asks for, else Sync now; a pause has none, the top bar's Resume lifts it.
    @ViewBuilder private var action: some View {
        if model.syncing {
            Button(model.text("Cancel")) { model.cancel() }.buttonStyle(.neutralPill)
        } else if model.paused {
            EmptyView()
        } else if model.needsSignIn {
            Button(model.text("Reconnect")) { model.signIn() }.buttonStyle(.neutralPill).disabled(model.busy)
        } else if model.hasSession {
            Button(model.text(retry ? "Retry sync" : "Sync now")) { model.syncNow() }.buttonStyle(.neutralPill).disabled(!model.canSync)
        }
    }

    @ViewBuilder private var recentFiles: some View {
        Divider()
        Text(model.text("Recent downloads")).font(.headline)
        let records = model.library.records.values.sorted { $0.updated > $1.updated }.prefix(4)
        if records.isEmpty { Text(model.text("Nothing downloaded yet.")).foregroundStyle(.secondary).font(.callout) }
        ForEach(Array(records), id: \.relativePath) { record in
            Button {
                Task {
                    do { preview = try await model.store?.url(record.relativePath) }
                    catch { previewError = SyncLogic.safeError(error) }
                }
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "doc.richtext").font(.title2).foregroundStyle(record.relativePath.lowercased().hasSuffix(".pdf") ? .red : .blue)
                    VStack(alignment: .leading, spacing: 5) {
                        Text((record.relativePath as NSString).lastPathComponent).font(.subheadline.weight(.medium)).lineLimit(2).foregroundStyle(.primary)
                        Text(record.updated.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "arrow.up.right").foregroundStyle(.tertiary)
                }.padding(.vertical, 5)
            }.buttonStyle(.plain)
            Divider()
        }
        if let previewError { Text(model.text(previewError)).font(.caption).foregroundStyle(.orange) }
        ViewAllButton(page: .activity)
    }
}

/// A "View all" (or "Open calendar") pill that switches the sidebar to the page.
struct ViewAllButton: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.openPage) private var openPage
    let page: AppPage
    var title = "View all"
    var body: some View {
        Button(model.text(title)) { openPage(page) }.buttonStyle(.pill)
    }
}

struct HomeView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // The line under the greeting, as on the Mac: the next due dates.
                if let deadlines = model.features?.deadlines { HomeSubtitle(page: deadlines) }
                if !model.hasSession && !model.needsSignIn && !model.busy { WelcomeCard() }
                // Left: the status card with the last files; right: announcements and the next due dates.
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 20) {
                        StatusCard(recent: true).frame(minWidth: 340)
                        HomeFeatureCards().frame(minWidth: 260, maxWidth: 380)
                    }
                    VStack(spacing: 20) { StatusCard(recent: true); HomeFeatureCards() }
                }
            }.padding(24).frame(maxWidth: 1150)
                .frame(maxWidth: .infinity)
        }.background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle(model.greeting)
    }
}

struct WelcomeCard: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Card {
            Text(model.text("Your course files start here.")).font(.largeTitle.weight(.bold))
            Text(model.text("Connect your Blackboard account and bring your course files to this iPad.")).foregroundStyle(.secondary)
            Text(model.text("1. Sign in to Blackboard\n2. Choose your courses\n3. Sync now and open your files offline"))
                .font(.callout).lineSpacing(8)
            TextField(model.text("Your school's Blackboard address"), text: $model.tenantText)
                .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL).textFieldStyle(.roundedBorder)
            Button(model.text("Sign in to Blackboard")) { model.signIn() }.buttonStyle(.borderedProminent).disabled(model.busy)
        }
    }
}
