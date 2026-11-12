import SwiftUI
import QuickLook
import BlackboardSyncFeatures

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
    @State private var columns: NavigationSplitViewVisibility = .all
    @State private var portrait = false
    var body: some View {
        // The full-screen first run (F1) stands in for the whole shell; the sheets below serve both.
        Group {
            if model.firstRunScreen == .fullScreen { FirstRunPage() } else { shell }
        }
        .tint(Color.appAccent)
        .featureTheme(.app)
        .sheet(isPresented: $model.showingSettings, onDismiss: {
            if model.loginAfterSettings { model.loginAfterSettings = false; model.signIn() }
        }) { SettingsView().environmentObject(model) }
        .sheet(isPresented: $model.showingLogin) { SignInView().environmentObject(model) }
        .sheet(item: $model.termConfirm) { card in FirstCoursesCard(card: card, selected: model.selected).environmentObject(model) }
        .signOutConfirmation(isPresented: $model.confirmingSignOut)
    }

    private var shell: some View {
        NavigationSplitView(columnVisibility: $columns) {
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    Image("Logo").resizable().scaledToFit().frame(width: 36, height: 44)
                    Text("Blackboard Sync").font(.headline)
                    Spacer(minLength: 0)
                }.padding(20)
                List(selection: $page) {
                    // The Mac's one big rounded "Open folder" button above the sections.
                    NavigationLink(value: AppPage.library) {
                        Label(model.text("Open folder"), systemImage: AppIcon.folder).padding(.vertical, 8)
                    }
                    .listRowBackground(RoundedRectangle(cornerRadius: Radius.control).fill(.quaternary).padding(.vertical, 2))
                    .accessibilityIdentifier("sidebar.folder")
                    Section {
                        NavigationLink(value: AppPage.home) { Label(model.text("Home"), systemImage: "house") }
                        NavigationLink(value: AppPage.activity) { Label(model.text("Sync activity"), systemImage: AppIcon.sync) }
                        NavigationLink(value: AppPage.announcements) { Label(model.text("Announcements"), systemImage: AppIcon.announcements) }
                            .accessibilityIdentifier("sidebar.announcements")
                        NavigationLink(value: AppPage.courses) {
                            HStack {
                                Label(model.text("Courses"), systemImage: AppIcon.courses)
                                Spacer(minLength: 8)
                                if let courseCount { CourseCountBadge(text: courseCount) }
                            }
                        }
                        NavigationLink(value: AppPage.calendar) { Label(model.text("Calendar"), systemImage: AppIcon.calendar) }
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
            }
            .environment(\.openPage) { page = $0 }
        }
        // Every page, pushed folders included, draws the top bar (`appTopBar`). Set here rather than on
        // the stack, which pages pushed with a destination link do not inherit from; the sheets below
        // sit outside, so Settings keeps plain titles.
        .environment(\.showsTopBar, true)
        // The system bar is hidden, so its sidebar button is drawn in the top bar while in portrait;
        // landscape always shows the sidebar.
        .environment(\.toggleSidebar, portrait ? { withAnimation { columns = columns == .detailOnly ? .all : .detailOnly } } : nil)
        .onGeometryChange(for: Bool.self) { $0.size.height > $0.size.width } action: { tall in
            portrait = tall
            if !tall { columns = .all }
        }
    }
    /// "4/5" beside Courses while some course is unticked, as on the Mac; nothing otherwise.
    private var courseCount: String? {
        let all = model.courses.count, ticked = model.courses.filter { model.selected.contains($0.id) }.count
        return ticked == all ? nil : "\(ticked)/\(all)"
    }
}

private struct ShowsTopBarKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    /// True in the main window's pages, false in sheets such as Settings that reuse them.
    var showsTopBar: Bool {
        get { self[ShowsTopBarKey.self] }
        set { self[ShowsTopBarKey.self] = newValue }
    }
}

extension View {
    /// The top bar (board pick T1): the page title at the left and Pause, Settings and the account as
    /// three equal circles at the right, all on one line. `extra` circles (such as Refresh) come first.
    /// Outside the main window, as in the Settings sheet, the page keeps a plain title and its extras.
    func appTopBar(_ title: String) -> some View { modifier(AppTopBar(title: title, extra: EmptyView())) }
    func appTopBar<Extra: View>(_ title: String, @ViewBuilder extra: () -> Extra) -> some View {
        modifier(AppTopBar(title: title, extra: extra()))
    }
}

private struct SidebarToggleKey: EnvironmentKey { static let defaultValue: (() -> Void)? = nil }
extension EnvironmentValues {
    /// Shows or hides the sidebar; set while the sidebar can be hidden (portrait), nil otherwise.
    var toggleSidebar: (() -> Void)? {
        get { self[SidebarToggleKey.self] }
        set { self[SidebarToggleKey.self] = newValue }
    }
}

/// The bar is drawn here rather than by the system: iPadOS 26 turns toolbar buttons into its own bar
/// buttons with their own gaps and moves a leading title into an overflow menu, so the system bar can
/// not hold one centre line with three equal circles 8 pt apart.
private struct AppTopBar<Extra: View>: ViewModifier {
    let title: String
    let extra: Extra
    @Environment(\.showsTopBar) private var showsTopBar
    /// True on a pushed page, such as a folder inside the file browser.
    @Environment(\.isPresented) private var pushed
    @Environment(\.dismiss) private var dismiss
    @Environment(\.toggleSidebar) private var toggleSidebar

    func body(content: Content) -> some View {
        if showsTopBar {
            content
                // Still names the page for VoiceOver and the back button's long-press menu.
                .navigationTitle(title)
                .toolbar(.hidden, for: .navigationBar)
                .background(SwipeBack())
                .safeAreaInset(edge: .top, spacing: 0) {
                    TopBarRow(title: title, extra: extra, back: pushed ? { dismiss() } : nil,
                              toggleSidebar: pushed ? nil : toggleSidebar)
                }
        } else {
            content
                .navigationTitle(title)
                .toolbar { ToolbarItem(placement: .topBarTrailing) { extra } }
        }
    }
}

/// Keeps the edge swipe back working: hiding the system bar turns it off. A view inside the page finds
/// the stack's navigation controller through the responder chain and turns the swipe back on whenever
/// the page is shown or laid out, since SwiftUI may turn it off again when it updates the hidden bar.
private struct SwipeBack: UIViewRepresentable {
    func makeUIView(context: Context) -> Probe { Probe() }
    func updateUIView(_ probe: Probe, context: Context) { probe.enable() }

    final class Probe: UIView {
        override func didMoveToWindow() {
            super.didMoveToWindow()
            enable()
        }
        override func layoutSubviews() {
            super.layoutSubviews()
            enable()
        }
        func enable() {
            var responder: UIResponder? = self
            while let current = responder, !(current is UINavigationController) { responder = current.next }
            guard let swipe = (responder as? UINavigationController)?.interactivePopGestureRecognizer else { return }
            if swipe.delegate !== SwipeBackRule.shared { swipe.delegate = SwipeBackRule.shared }
            if !swipe.isEnabled { swipe.isEnabled = true }
        }
    }
}

/// Lets the swipe start only when there is a page to go back to; on the first page it would stall the stack.
private final class SwipeBackRule: NSObject, UIGestureRecognizerDelegate {
    static let shared = SwipeBackRule()
    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let navigation = gestureRecognizer.view?.next as? UINavigationController else { return false }
        return navigation.viewControllers.count > 1
    }
}

/// One 50 pt row on one centre line: Back or the sidebar button, the title, then the circles. The
/// first and last circles sit 24 pt from the screen edges, like the page content.
private struct TopBarRow<Extra: View>: View {
    @EnvironmentObject var model: AppModel
    let title: String
    let extra: Extra
    let back: (() -> Void)?
    let toggleSidebar: (() -> Void)?

    var body: some View {
        HStack(spacing: 0) {
            if let back {
                circle("Back", symbol: "chevron.left", id: "toolbar.back", action: back)
            } else if let toggleSidebar {
                circle("Sidebar", symbol: "sidebar.left", id: "toolbar.sidebar", action: toggleSidebar)
            }
            TopBarTitle(title)
                .padding(.leading, back == nil && toggleSidebar == nil ? inset : Spacing.xxs)
            Spacer(minLength: Spacing.xs)
            TopBarCircles(extra: extra)
        }
        // The tap targets reach 4 pt past the circles, so the row's edge is 4 pt inside the margin.
        .padding(.horizontal, Spacing.page - inset)
        .frame(height: 50)
        .frame(maxWidth: .infinity)
        .background(Color(uiColor: .systemGroupedBackground))
    }

    private var inset: CGFloat { (TopBarMetrics.target - TopBarMetrics.circle) / 2 }

    private func circle(_ title: String, symbol: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(model.text(title), systemImage: symbol).font(.system(size: TopBarMetrics.glyph, weight: .semibold))
        }
        .buttonStyle(TopBarCircleStyle())
        .accessibilityIdentifier(id)
    }
}

/// Extra circles, then Pause, Settings and the account, with touching tap targets. With the welcome
/// card (F2) there is nothing to pause or show for the account, so only Settings stays (and a Resume
/// for a pause already set).
private struct TopBarCircles<Extra: View>: View {
    @EnvironmentObject var model: AppModel
    let extra: Extra
    var body: some View {
        let welcome = model.firstRunScreen == .welcomeCard
        HStack(spacing: 0) {
            extra
            if !welcome || model.paused { PauseButton() }
            SettingsButton()
            if !welcome { AccountMenu() }
        }
    }
}

struct PauseButton: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Button { model.togglePause() } label: {
            Label(model.text(model.paused ? "Resume syncing" : "Pause syncing"),
                  systemImage: model.paused ? AppIcon.resume : AppIcon.pause)
                .font(.system(size: TopBarMetrics.playGlyph, weight: .semibold))
        }
        .buttonStyle(TopBarCircleStyle(model.paused ? .filled : .plain))
        .disabled(!model.canTogglePause)
        .accessibilityIdentifier("toolbar.pause")
    }
}

struct SettingsButton: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Button { model.showingSettings = true } label: {
            Label(model.text("Settings"), systemImage: AppIcon.settings)
                .font(.system(size: TopBarMetrics.glyph, weight: .semibold))
        }
        .buttonStyle(TopBarCircleStyle())
        .accessibilityIdentifier("toolbar.settings")
    }
}

/// The Mac's account control: initials in a circle, opening who is signed in and sign in or out.
/// Settings has its own circle beside it, so the menu does not repeat it.
struct AccountMenu: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Menu {
            Section {
                Button {} label: { Label(header, systemImage: AppIcon.account) }.disabled(true)
                if model.hasSession, let host = URL(string: model.tenantText)?.host {
                    Button {} label: { Label(host, systemImage: "building.columns") }.disabled(true)
                }
            }
            Section {
                if model.hasSession || model.hasStoredSession {
                    if model.needsSignIn {
                        Button(model.text("Reconnect")) { model.signIn() }.disabled(model.busy)
                    }
                    Button(model.text("Sign out"), role: .destructive) { model.confirmingSignOut = true }.disabled(model.busy && !model.syncing)
                } else {
                    Button(model.text(model.needsSignIn ? "Reconnect" : "Sign in to Blackboard")) { model.signIn() }.disabled(model.busy)
                }
            }
        } label: {
            TopBarCircle(kind: initials == nil ? .plain : .tinted) {
                if let initials {
                    Text(initials).font(.system(size: TopBarMetrics.initials, weight: .bold))
                } else {
                    Image(systemName: AppIcon.account).font(.system(size: TopBarMetrics.glyph, weight: .semibold))
                }
            }
            // A session that needs signing in again: an orange dot on the circle.
            .overlay(alignment: .topTrailing) {
                if model.needsSignIn {
                    Circle().fill(AppColor.warning).frame(width: 11, height: 11)
                        .overlay(Circle().stroke(Color(uiColor: .systemBackground), lineWidth: 2))
                        .offset(x: -3, y: 3)
                }
            }
        }
        .accessibilityLabel(Text(signedIn ? model.accountName : model.text(model.needsSignIn ? "Sign-in needed" : "Not signed in")))
        .accessibilityIdentifier("toolbar.account")
    }
    private var signedIn: Bool { !model.accountName.isEmpty && !model.needsSignIn }
    /// The account's initials once a name is known, also while it needs signing in again.
    private var initials: String? {
        model.accountName.isEmpty ? nil : AppModel.initials(model.accountName, language: model.language)
    }
    private var header: String {
        if signedIn { return model.text("Signed in as {name}").replacingOccurrences(of: "{name}", with: model.accountName) }
        return model.text(model.needsSignIn ? "Your session expired; sign in again." : "Not signed in yet.")
    }
}

/// The "4/5" beside Courses as a solid accent badge. It stays solid when Courses is selected, because
/// the iPadOS sidebar marks the selected row with a light highlight, not an accent fill.
struct CourseCountBadge: View {
    let text: String
    var body: some View {
        Text(text).font(.caption.weight(.bold)).monospacedDigit().foregroundStyle(.white)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Color.appAccent, in: Capsule())
    }
}

extension View {
    /// Asks before signing out; signing out only goes ahead on the destructive button.
    func signOutConfirmation(isPresented: Binding<Bool>) -> some View { modifier(SignOutConfirmation(isPresented: isPresented)) }
}

private struct SignOutConfirmation: ViewModifier {
    @EnvironmentObject var model: AppModel
    @Binding var isPresented: Bool
    func body(content: Content) -> some View {
        content.alert(model.text("Sign out?"), isPresented: $isPresented) {
            Button(model.text("Cancel"), role: .cancel) {}
            Button(model.text("Sign out"), role: .destructive) { model.signOut() }
        } message: {
            Text(model.text("Downloaded files stay on this iPad."))
        }
    }
}

struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) { content }
            .frame(maxWidth: .infinity, alignment: .leading).padding(Spacing.l)
            .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: Radius.card))
            .overlay(RoundedRectangle(cornerRadius: Radius.card).stroke(.primary.opacity(0.055), lineWidth: 1))
    }
}

/// The Mac's status card on Sync activity: the state symbol, the state in large type and the last sync,
/// with at most one button at the top right. Home has its own strip (`HomeStatusStrip`).
struct StatusCard: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Card {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: symbol.name).font(.system(size: 26)).foregroundStyle(symbol.tint).frame(width: 32)
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.text(model.displayStatus)).font(.title.weight(.light))
                    if let last = model.library.lastSync {
                        Text(model.text("Last synced") + ": " + model.dateTime(last)).font(.callout).foregroundStyle(.secondary)
                    }
                    if model.sessionNoteVisible {
                        Text(model.text("Session refreshed automatically")).font(.callout).foregroundStyle(.secondary)
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
                Text("\(model.progress.downloaded) " + model.text("downloaded") + " · \(model.progress.unchanged) " + model.text("unchanged") + " · \(model.progress.skipped) " + model.text("skipped") + " · " + model.count(model.progress.failed, one: "{n} error", other: "{n} errors"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.errorMessage {
                Text(model.text(error)).font(.callout).foregroundStyle(.orange).textSelection(.enabled)
            }
            Text(model.text("Keep Blackboard Sync open while syncing. Completed files stay available offline."))
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var symbol: (name: String, tint: Color) {
        if model.syncing { return ("arrow.triangle.2.circlepath.icloud", .appAccentText) }
        if model.paused { return ("pause.circle.fill", .secondary) }
        if model.needsSignIn || !model.hasSession { return ("person.crop.circle.badge.exclamationmark", .orange) }
        if retry { return ("exclamationmark.icloud", .orange) }
        return (model.status == "Up to date" ? "checkmark.icloud" : "icloud", model.status == "Up to date" ? .green : .appAccentText)
    }
    private var retry: Bool {
        model.status == "Sync did not finish" || model.status.hasPrefix("Cancelled") || model.library.interrupted
    }

    /// What the state asks for, else Sync now; a pause has none, the top bar's Resume lifts it.
    @ViewBuilder private var action: some View {
        if model.syncing {
            Button(model.text("Cancel")) { model.cancel() }.buttonStyle(.appTertiary)
        } else if model.paused {
            EmptyView()
        } else if model.needsSignIn {
            Button(model.text("Reconnect")) { model.signIn() }.buttonStyle(.appTertiary).disabled(model.busy)
        } else if model.hasSession {
            Button(model.text(retry ? "Retry sync" : "Sync now")) { model.syncNow() }.buttonStyle(.appTertiary).disabled(!model.canSync)
        } else if !model.hasStoredSession {
            // Signed out (this card is on Sync activity, where no welcome card shows): the way back in.
            Button(model.text("Sign in to Blackboard")) { model.signIn() }.buttonStyle(.appTertiary).disabled(model.busy)
        }
    }
}

/// A "View all" (or "Open calendar") pill that switches the sidebar to the page.
struct ViewAllButton: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.openPage) private var openPage
    let page: AppPage
    var title = "View all"
    var body: some View {
        Button(model.text(title)) { openPage(page) }.buttonStyle(.appSecondary)
    }
}

/// Lists the known schools; picking one fills in its Blackboard address.
struct SchoolMenu: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Menu {
            ForEach(Schools.all, id: \.url) { school in
                Button(school.name) { model.tenantText = school.url }
            }
        } label: {
            Label(model.text("Choose your school"), systemImage: "building.columns")
        }
    }
}
