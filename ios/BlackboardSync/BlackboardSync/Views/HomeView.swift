import SwiftUI
import QuickLook
import BlackboardSyncFeatures

/// Home (board pick H1, "Status first"): the sync status as a wide strip with its one button on top,
/// the next due dates and the newest announcements side by side under it, then the last downloaded
/// files as a list. Before the first sign-in the welcome card takes the strip's place.
struct HomeView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.m) {
                // The line under the greeting, as on the Mac: the next due dates.
                if let deadlines = model.features?.deadlines { HomeSubtitle(page: deadlines) }
                if welcome { WelcomeCard() }
                if let status = HomeStatus.make(model) { HomeStatusStrip(status: status) }
                // Signed out there is nothing to show in them but "sign in first".
                if !welcome || model.features != nil { HomeFeatureCards() }
                // A student who signed out keeps the files; before any download the list is not shown.
                if !welcome || !model.library.records.isEmpty { HomeRecentDownloads() }
            }.padding(Spacing.page).frame(maxWidth: 1150)
                .frame(maxWidth: .infinity)
        }.background(Color(uiColor: .systemGroupedBackground))
            .appTopBar(model.greeting)
    }
    /// Never signed in on this iPad, or signed out: the welcome card with the sign-in button.
    private var welcome: Bool { !model.hasSession && !model.needsSignIn && !model.busy }
}

/// What Home's status strip says: the state's symbol and tone, the state in large type, the lines
/// under it and at most one button, which is always the next useful action.
struct HomeStatus: Equatable {
    enum Tone: Equatable { case good, busy, quiet, warning, neutral }
    enum Action: Equatable { case syncNow, retry, cancel, resume, reconnect }

    var tone: Tone
    var symbol: String
    /// Already in the app's language.
    var title: String
    var lines: [String] = []
    var action: Action?
    /// Files downloaded so far, 0 to 1, while a sync downloads; nil otherwise.
    var progress: Double?
    /// Work without a known length is running (checking the account, finding courses or files).
    var spinner = false

    /// Nil when the welcome card stands in for the strip and there is nothing else to say.
    @MainActor static func make(_ model: AppModel) -> HomeStatus? {
        let text = model.text
        if model.syncing {
            let p = model.progress
            var status = HomeStatus(tone: .busy, symbol: AppIcon.sync, title: text("Syncing…"), action: .cancel)
            if p.discovering {
                status.lines = [text("Finding files…")]
                status.spinner = true
            } else {
                status.lines = ["\(p.completed) / \(p.discovered)" + (p.currentName.isEmpty ? "" : " · " + p.currentName)]
                status.progress = Double(p.completed) / Double(max(1, p.discovered))
            }
            status.lines.append(text("Keep Blackboard Sync open while syncing. Completed files stay available offline."))
            return status
        }
        if model.paused {
            return HomeStatus(tone: .quiet, symbol: AppIcon.pause, title: text("Paused"),
                              lines: [text("Syncing is paused. Resume to sync again.")], action: .resume)
        }
        if model.needsSignIn {
            return HomeStatus(tone: .warning, symbol: "person.crop.circle.badge.exclamationmark", title: text("Sign-in needed"),
                              lines: [text("Your session expired; sign in again.")], action: .reconnect)
        }
        if model.busy {
            return HomeStatus(tone: .busy, symbol: AppIcon.sync, title: text(model.status), spinner: true)
        }
        if !model.hasSession {
            // The welcome card has the sign-in button; only a failure still needs saying.
            guard let error = model.errorMessage else { return nil }
            return HomeStatus(tone: .warning, symbol: "exclamationmark.triangle.fill", title: text("Not signed in"),
                              lines: [text(error)])
        }
        if retry(model) {
            var lines: [String] = []
            if let error = model.errorMessage { lines.append(text(error)) }
            else if model.status != "Sync did not finish" { lines.append(text(model.status)) }
            else if model.progress.failed > 0 { lines.append(model.count(model.progress.failed, one: "{n} error", other: "{n} errors")) }
            return HomeStatus(tone: .warning, symbol: "exclamationmark.icloud.fill", title: text("Sync did not finish"),
                              lines: lines, action: .retry)
        }
        if model.status == AppModel.noCoursesFound {
            return HomeStatus(tone: .neutral, symbol: AppIcon.courses, title: text("No current-term courses found."),
                              lines: [text(AppModel.noCoursesFound)])
        }
        if model.status == TermConfirm.waiting {
            return HomeStatus(tone: .neutral, symbol: AppIcon.courses, title: text(TermConfirm.title),
                              lines: [text(TermConfirm.waiting)], action: .syncNow)
        }
        let upToDate = model.status == "Up to date"
        var status = HomeStatus(tone: upToDate ? .good : .neutral, symbol: upToDate ? "checkmark.icloud.fill" : "icloud.fill",
                                title: text(model.status), action: .syncNow)
        if let last = model.library.lastSync {
            var line = text("Last synced") + ": " + model.dateTime(last)
            if upToDate, model.progress.downloaded > 0 {
                line += " · " + model.count(model.progress.downloaded, one: "{n} new file", other: "{n} new files")
            }
            status.lines.append(line)
        }
        if model.selected.isEmpty { status.lines.append(text("Select your courses and tap Sync now.")) }
        if model.sessionNoteVisible { status.lines.append(text("Session refreshed automatically")) }
        return status
    }

    @MainActor private static func retry(_ model: AppModel) -> Bool {
        model.status == "Sync did not finish" || model.status.hasPrefix("Cancelled") || model.library.interrupted
    }
}

/// The strip itself: a tinted symbol tile, the state and its lines, and the one button at the right.
struct HomeStatusStrip: View {
    @EnvironmentObject var model: AppModel
    let status: HomeStatus
    var body: some View {
        HStack(alignment: .center, spacing: Spacing.m) {
            ZStack {
                RoundedRectangle(cornerRadius: Radius.control).fill(tileFill)
                if status.spinner {
                    ProgressView().tint(tint)
                } else {
                    Image(systemName: status.symbol).font(.system(size: 24, weight: .semibold)).foregroundStyle(tint)
                }
            }
            .frame(width: 56, height: 56)
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(status.title).font(.title).lineLimit(3)
                ForEach(status.lines, id: \.self) { line in
                    Text(line).font(.callout).foregroundStyle(.secondary)
                }
                if let progress = status.progress {
                    ProgressView(value: progress).tint(AppColor.accent).padding(.top, Spacing.xxs)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("home.status")
            if let action = status.action { button(action).fixedSize() }
        }
        .padding(.horizontal, Spacing.l).padding(.vertical, Spacing.m + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).stroke(.primary.opacity(0.055), lineWidth: 1))
    }

    @ViewBuilder private func button(_ action: HomeStatus.Action) -> some View {
        switch action {
        case .cancel:
            Button(model.text("Cancel")) { model.cancel() }
                .buttonStyle(AppButtonStyle(.tertiary, large: true)).accessibilityIdentifier("home.action")
        case .resume:
            Button { model.togglePause() } label: { Label(model.text("Resume syncing"), systemImage: AppIcon.resume) }
                .buttonStyle(.appPrimaryLarge).disabled(!model.canTogglePause).accessibilityIdentifier("home.action")
        case .reconnect:
            Button(model.text("Reconnect")) { model.signIn() }
                .buttonStyle(.appPrimaryLarge).disabled(model.busy).accessibilityIdentifier("home.action")
        case .retry, .syncNow:
            Button { model.syncNow() } label: {
                Label(model.text(action == .retry ? "Retry sync" : "Sync now"), systemImage: AppIcon.sync)
            }
            .buttonStyle(.appPrimaryLarge).disabled(!model.canSync).accessibilityIdentifier("home.action")
        }
    }

    private var tint: Color {
        switch status.tone {
        case .good: .green
        case .busy, .neutral: AppColor.accentText
        case .quiet: .secondary
        case .warning: AppColor.warning
        }
    }
    private var tileFill: Color {
        switch status.tone {
        case .good: Color.green.opacity(0.16)
        case .busy, .neutral: AppColor.accentSoft
        case .quiet: AppColor.neutralFill
        case .warning: AppColor.warning.opacity(0.17)
        }
    }
}

/// One of Home's last downloaded files.
struct RecentFile: Identifiable, Equatable {
    var id: String { relativePath }
    let relativePath: String
    let name: String
    /// The course code from the file's course folder ("COE305"), when the path has one.
    let course: String?
    /// "PDF", "PPT", "DOC"; nil for a file without an extension.
    let badge: String?
    let updated: Date

    /// The newest `limit` files, newest first.
    static func newest(_ records: [String: FileRecord], limit: Int = 4) -> [RecentFile] {
        records.values.sorted { $0.updated != $1.updated ? $0.updated > $1.updated : $0.relativePath < $1.relativePath }
            .prefix(limit).map(RecentFile.init)
    }

    init(_ record: FileRecord) {
        relativePath = record.relativePath
        let parts = record.relativePath.split(separator: "/").map(String.init)
        name = parts.last ?? record.relativePath
        // "Term/Course folder/…/file": the course folder starts with its code.
        course = parts.count >= 3 ? parts[1].split(separator: " ").first.map(String.init) : nil
        let ext = (name as NSString).pathExtension
        badge = ext.isEmpty ? nil : String(ext.prefix(3)).uppercased()
        updated = record.updated
    }
}

/// Home's Recent downloads: the last files as rows; a tap opens the file in the Files app.
struct HomeRecentDownloads: View {
    @EnvironmentObject var model: AppModel
    @State private var preview: URL?
    @State private var previewError: String?
    var body: some View {
        let files = RecentFile.newest(model.library.records)
        Card {
            HStack {
                Text(model.text("Recent downloads")).font(.headline)
                Spacer(minLength: Spacing.xs)
                if !files.isEmpty { ViewAllButton(page: .activity) }
            }
            if files.isEmpty {
                Text(model.text("Nothing downloaded yet.")).font(.callout).foregroundStyle(.secondary)
            }
            VStack(spacing: 0) {
                ForEach(Array(files.enumerated()), id: \.element.id) { index, file in
                    if index > 0 { Divider().padding(.leading, 48) }
                    row(file)
                }
            }
            if let previewError { Text(model.text(previewError)).font(.caption).foregroundStyle(AppColor.warning) }
        }.quickLookPreview($preview)
    }

    private func row(_ file: RecentFile) -> some View {
        Button { open(file) } label: {
            HStack(spacing: Spacing.s) {
                FileBadge(text: file.badge)
                VStack(alignment: .leading, spacing: 3) {
                    Text(file.name).font(.subheadline.weight(.medium)).lineLimit(1).truncationMode(.middle).foregroundStyle(.primary)
                    Text([file.course, model.dateTime(file.updated)].compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: Spacing.xs)
                Image(systemName: "arrow.up.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
            }
            .padding(.vertical, Spacing.xs)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("home.recent")
    }

    private func open(_ file: RecentFile) {
        Task {
            do {
                if let url = try await model.store?.url(file.relativePath) {
                    previewError = nil
                    model.openExternally(url) { preview = $0 }
                }
            } catch { previewError = SyncLogic.safeError(error) }
        }
    }
}

/// The file type as a small coloured tile: red for PDF, orange for slides, accent otherwise.
private struct FileBadge: View {
    let text: String?
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: Radius.small).fill(tint.opacity(0.15))
            if let text {
                Text(text).font(.system(size: 10, weight: .heavy)).foregroundStyle(tint)
            } else {
                Image(systemName: "doc.fill").font(.system(size: 15)).foregroundStyle(tint)
            }
        }
        .frame(width: 36, height: 36)
        .accessibilityHidden(true)
    }
    private var tint: Color {
        switch text {
        case "PDF": .red
        case "PPT", "KEY": .orange
        default: AppColor.accentText
        }
    }
}
