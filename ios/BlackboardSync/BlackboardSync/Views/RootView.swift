import SwiftUI
import QuickLook

private enum Page: String, Hashable { case home, activity, courses, library }

struct RootView: View {
    @EnvironmentObject var model: AppModel
    @State private var page: Page? = .home
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
                    NavigationLink(value: Page.library) { Label(model.text("Open folder"), systemImage: "folder") }
                    Section {
                        NavigationLink(value: Page.home) { Label(model.text("Home"), systemImage: "house") }
                        NavigationLink(value: Page.activity) { Label(model.text("Sync activity"), systemImage: "arrow.triangle.2.circlepath") }
                        ComingSoon(title: "Announcements", symbol: "megaphone")
                        NavigationLink(value: Page.courses) { Label(model.text("Courses"), systemImage: "books.vertical") }
                        ComingSoon(title: "Calendar", symbol: "calendar")
                    }
                }.listStyle(.sidebar)
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Image(systemName: "person.crop.circle.fill").font(.largeTitle).foregroundStyle(.blue)
                        Text(model.accountName.isEmpty ? model.text("Not signed in") : model.accountName).font(.subheadline.weight(.semibold))
                    }
                    Text(model.text(model.status)).font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                    .background(.background, in: RoundedRectangle(cornerRadius: 16)).padding(14)
            }
            .navigationSplitViewColumnWidth(min: 225, ideal: 255, max: 300)
            .toolbar(.hidden, for: .navigationBar)
        } detail: {
            NavigationStack {
                Group {
                    switch page ?? .home {
                    case .home: HomeView()
                    case .activity: ActivityView()
                    case .courses: CoursesView()
                    case .library: FileBrowser(folder: "", title: model.text("University"))
                    }
                }
                .toolbar {
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        if model.syncing {
                            Button { model.cancel() } label: { Label(model.text("Cancel"), systemImage: "stop.circle") }
                        } else {
                            Button { model.syncNow() } label: { Label(model.text("Sync now"), systemImage: "arrow.triangle.2.circlepath") }.disabled(!model.canSync)
                        }
                        Button { model.showingSettings = true } label: { Label(model.text("Settings"), systemImage: "gearshape") }
                    }
                }
            }
        }
        .tint(Color(red: 0.15, green: 0.36, blue: 0.95))
        .sheet(isPresented: $model.showingSettings) { SettingsView().environmentObject(model) }
        .sheet(isPresented: $model.showingLogin) { SignInView().environmentObject(model) }
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
            .accessibilityElement(children: .combine)
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

struct StatusCard: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Card {
            HStack(spacing: 16) {
                Image(systemName: model.syncing ? "arrow.triangle.2.circlepath.icloud" : model.needsSignIn ? "person.crop.circle.badge.exclamationmark" : model.status == "Up to date" ? "checkmark.icloud" : "icloud")
                    .font(.system(size: 34, weight: .regular)).foregroundStyle(model.needsSignIn ? .orange : .blue)
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.text(model.status)).font(.title3.weight(.semibold))
                    if let last = model.library.lastSync {
                        Text(model.text("Last synced") + ": " + last.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 0)
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
            if model.needsSignIn {
                Button(model.text("Reconnect")) { model.signIn() }.buttonStyle(.borderedProminent).disabled(model.busy)
            } else if model.status == "Sync did not finish" || model.status.hasPrefix("Cancelled") || model.library.interrupted {
                Button(model.text("Retry sync")) { model.syncNow() }.buttonStyle(.bordered).disabled(!model.canSync)
            }
            Text(model.text("Keep Blackboard Sync open while syncing. Completed files stay available offline."))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct HomeView: View {
    @EnvironmentObject var model: AppModel
    @State private var preview: URL?
    @State private var previewError: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if !model.hasSession && !model.needsSignIn && !model.busy { WelcomeCard() }
                StatusCard()
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 20) {
                        recent.frame(minWidth: 300)
                        upcoming.frame(minWidth: 250, maxWidth: 360)
                    }
                    VStack(spacing: 20) { recent; upcoming }
                }
            }.padding(24).frame(maxWidth: 1150)
                .frame(maxWidth: .infinity)
        }.background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle(model.greeting)
            .quickLookPreview($preview)
    }
    private var recent: some View {
        Card {
            HStack {
                Text(model.text("Recent downloads")).font(.headline)
                Spacer()
                NavigationLink(model.text("View all")) { ActivityView() }.font(.caption.weight(.semibold))
            }
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
        }
    }
    private var upcoming: some View {
        VStack(spacing: 20) {
            Card {
                ComingSoon(title: "Announcements", symbol: "megaphone")
                Text(model.text("Things that need your attention will show up here.")).font(.callout).foregroundStyle(.secondary)
            }
            Card {
                ComingSoon(title: "Upcoming deadlines", symbol: "calendar")
                Text(model.text("Deadlines and calendar are coming to iPad.")).font(.callout).foregroundStyle(.secondary)
            }
        }
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
