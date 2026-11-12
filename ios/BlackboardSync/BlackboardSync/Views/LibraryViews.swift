import SwiftUI
import QuickLook
import BlackboardSyncFeatures

struct CoursesView: View {
    @EnvironmentObject var model: AppModel
    /// False in the Settings sheet, which keeps the plain list.
    @Environment(\.showsTopBar) private var inMainWindow
    var body: some View {
        Group {
            if inMainWindow && model.firstRunScreen == .welcomeCard {
                // Signed out with nothing downloaded: the welcome card (F2) instead of an empty list.
                ScrollView { WelcomeCard().padding(Spacing.page) }
                    .background(Color(uiColor: .systemGroupedBackground))
            } else if inMainWindow, let draft = model.termConfirm {
                // Before the first download at a new school the card holds the ticks, so the list waits.
                ScrollView { FirstDownloadCard(draft: draft).padding(Spacing.page).frame(maxWidth: 1150).frame(maxWidth: .infinity) }
                    .background(Color(uiColor: .systemGroupedBackground))
            } else {
                courseList
            }
        }.appTopBar(model.text("Courses")) {
            Button { model.refreshCourses() } label: {
                Label(model.text("Refresh courses"), systemImage: "arrow.clockwise")
                    .font(.system(size: TopBarMetrics.glyph, weight: .semibold))
            }
            .buttonStyle(TopBarCircleStyle())
            .disabled(model.busy || !model.hasSession)
        }
    }

    private var courseList: some View {
        List {
            Section {
                Text(model.text("Choose the courses to sync. Your downloaded files remain when a course is turned off."))
                    .font(.callout).foregroundStyle(.secondary)
                if !model.hasSession { Text(model.text("Sign in to refresh your current-term courses.")).font(.callout) }
                if model.courses.isEmpty && !model.busy { Text(model.text("No current-term courses found.")) }
            }
            ForEach(model.terms) { term in
                Section(term.name) {
                    ForEach(term.courses.sorted { $0.name < $1.name }) { course in
                        HStack(spacing: 18) {
                            Toggle(course.name, isOn: Binding(get: { model.selected.contains(course.id) },
                                                             set: { model.setSelected(course, enabled: $0) }))
                                .toggleStyle(.checkboxStyle).disabled(model.busy)
                            if let folder = model.folder(for: course) {
                                NavigationLink { FileBrowser(folder: folder, title: course.name) } label: {
                                    Label(model.text("Open folder"), systemImage: AppIcon.folder).font(.callout)
                                }.fixedSize(horizontal: false, vertical: true)
                            }
                        }.padding(.vertical, 6)
                    }
                }
            }
        }
    }
}

/// The card before the first download at a new school (`TermConfirm`), the first run's last step: the
/// term found and its courses, ticked as in Courses. Change term switches to another term Blackboard
/// lists; Confirm and start saves the ticks and syncs. Home and Courses show it full width in place of
/// their content until then, under the top bar.
struct FirstDownloadCard: View {
    @EnvironmentObject var model: AppModel
    let draft: TermConfirm.Draft

    var body: some View {
        Card {
            HStack(alignment: .top, spacing: Spacing.m) {
                ZStack {
                    RoundedRectangle(cornerRadius: Radius.control).fill(AppColor.accentSoft)
                    Image(systemName: AppIcon.courses).font(.system(size: 24, weight: .semibold)).foregroundStyle(AppColor.accentText)
                }
                .frame(width: 56, height: 56)
                .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Spacing.xxs) {
                    Text(model.text(TermConfirm.title)).font(.title).accessibilityAddTraits(.isHeader)
                    Text(TermConfirm.message(draft.card, language: model.language)).font(.callout).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Divider()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Spacing.m) { term; Spacer(minLength: Spacing.xs); changeTerm }
                VStack(alignment: .leading, spacing: Spacing.s) { term; changeTerm }
            }
            VStack(spacing: 0) {
                ForEach(draft.rows) { row in
                    Toggle(row.label, isOn: Binding(get: { draft.ticked.contains(row.id) }, set: { _ in model.toggleFirstCourse(row.id) }))
                        .toggleStyle(.checkboxStyle).padding(.vertical, Spacing.s)
                        .accessibilityIdentifier("termConfirm.course." + row.id)
                    if row.id != draft.rows.last?.id { Divider() }
                }
            }
            .padding(.horizontal, Spacing.m)
            .background(Color(uiColor: .systemGroupedBackground), in: RoundedRectangle(cornerRadius: Radius.control))
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Spacing.m) { summary; Spacer(minLength: Spacing.xs); confirm }
                VStack(alignment: .leading, spacing: Spacing.s) { summary; confirm }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("termConfirm.card")
    }

    private var term: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(model.text(TermConfirm.termLabel)).font(.caption).foregroundStyle(.secondary)
            Text(draft.termName).font(.headline).accessibilityIdentifier("termConfirm.term")
        }
        .accessibilityElement(children: .combine)
    }

    /// Another term Blackboard lists; nothing to offer when it lists only the one found.
    @ViewBuilder private var changeTerm: some View {
        if !draft.card.others.isEmpty {
            Menu {
                Picker(model.text(TermConfirm.changeTerm), selection: Binding(get: { draft.choice ?? "" },
                                                                            set: { model.chooseFirstTerm($0.isEmpty ? nil : $0) })) {
                    Section(model.text(TermConfirm.detectedLabel)) {
                        Text(TermConfirm.Draft(card: draft.card, selected: []).termName).tag("")
                    }
                    Section(model.text(TermConfirm.otherTerms)) {
                        ForEach(draft.card.others) { term in
                            Text(TermConfirm.optionLabel(term, language: model.language)).tag(term.id)
                        }
                    }
                }
            } label: {
                Label(model.text(TermConfirm.changeTerm), systemImage: "arrow.left.arrow.right")
            }
            .menuStyle(.button)
            .buttonStyle(.appSecondary)
            .disabled(model.busy)
            .accessibilityIdentifier("termConfirm.change")
        }
    }

    private var summary: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(TermConfirm.selectedLine(draft, language: model.language)).font(.callout.weight(.semibold))
                .accessibilityIdentifier("termConfirm.count")
            if !draft.canConfirm {
                Text(model.text(TermConfirm.tickOne)).font(.callout).foregroundStyle(AppColor.warning)
            }
        }
    }

    private var confirm: some View {
        Button { model.confirmFirstCourses() } label: { Text(model.text(TermConfirm.confirmLabel)) }
            .buttonStyle(.appPrimaryLarge)
            .disabled(!draft.canConfirm || model.busy)
            .accessibilityIdentifier("termConfirm.confirm")
    }
}

private struct CourseCheckbox: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(spacing: 12) {
                Image(systemName: configuration.isOn ? "checkmark.square.fill" : "square").font(.title2).foregroundStyle(Color.appAccentText)
                configuration.label.foregroundStyle(.primary).frame(maxWidth: .infinity, alignment: .leading)
            }.contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityValue(configuration.isOn ? Text("✓") : Text("—"))
            .accessibilityAddTraits(configuration.isOn ? [.isSelected] : [])
    }
}
private extension ToggleStyle where Self == CourseCheckbox { static var checkboxStyle: CourseCheckbox { CourseCheckbox() } }

struct ActivityView: View {
    @EnvironmentObject var model: AppModel
    @State private var preview: URL?
    @State private var errorMessage: String?
    var body: some View {
        List {
            Section { StatusCard().listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            Section(model.text("Sync activity")) {
                if model.library.activities.isEmpty { Text(model.text("Nothing downloaded yet.")).foregroundStyle(.secondary) }
                ForEach(model.library.activities) { activity in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 12) {
                            // A row with a file opens it in Files / Preview when tapped anywhere; a quiet
                            // chevron says so. Rows without a file (skipped, failed) do not react to a tap.
                            if let relative = activity.relativePath {
                                Button { open(relative) } label: {
                                    HStack(spacing: 12) {
                                        summary(activity)
                                        Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                                    }.contentShape(Rectangle())
                                }.buttonStyle(.plain)
                            } else {
                                summary(activity)
                            }
                            if activity.status == .failed {
                                Button(model.text("Retry sync")) { model.syncNow() }.buttonStyle(.bordered).disabled(!model.canSync)
                            }
                        }
                        if let error = activity.error { Text(model.text(error)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                    }.padding(.vertical, 6)
                }
                if let errorMessage { Text(model.text(errorMessage)).foregroundStyle(.orange) }
            }
        }.appTopBar(model.text("Sync activity")).quickLookPreview($preview)
    }
    private func summary(_ activity: Activity) -> some View {
        HStack(spacing: 12) {
            Image(systemName: activity.status == .failed ? "exclamationmark.circle" : activity.status == .skipped ? "minus.circle" : "doc.richtext")
                .font(.title2).foregroundStyle(activity.status == .failed ? Color.orange : .appAccentText)
            VStack(alignment: .leading, spacing: 4) {
                Text(activity.name).font(.subheadline.weight(.medium))
                Text(model.text(activity.status.rawValue)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
    }
    private func open(_ relative: String) {
        Task {
            do {
                if let url = try await model.store?.url(relative) {
                    model.openExternally(url) { preview = $0 }
                }
            } catch { errorMessage = SyncLogic.safeError(error) }
        }
    }
}

struct FileBrowser: View {
    @EnvironmentObject var model: AppModel
    let folder: String
    let title: String
    @State private var entries: [LocalEntry] = []
    @State private var preview: URL?
    @State private var errorMessage: String?
    var body: some View {
        List {
            Section {
                Text(model.text("Also in Files → On My iPad → Blackboard Sync → University"))
                    .font(.caption).foregroundStyle(.secondary)
                if entries.isEmpty && errorMessage == nil {
                    ContentUnavailableView(model.text("No downloaded files yet."), systemImage: AppIcon.folder,
                                           description: Text(model.text("Select your courses and tap Sync now.")))
                }
                ForEach(entries) { entry in
                    if entry.isDirectory {
                        NavigationLink {
                            FileBrowser(folder: folder.isEmpty ? entry.url.lastPathComponent : folder + "/" + entry.url.lastPathComponent,
                                        title: entry.url.lastPathComponent)
                        } label: { Label(entry.url.lastPathComponent, systemImage: AppIcon.folder).padding(.vertical, 5) }
                    } else {
                        HStack(spacing: 14) {
                            Button {
                                model.openExternally(entry.url) { preview = $0 }
                            } label: {
                                HStack(spacing: 14) {
                                    Image(systemName: "doc.richtext").foregroundStyle(Color.appAccentText).font(.title2)
                                    Text(entry.url.lastPathComponent).font(.callout).frame(maxWidth: .infinity, alignment: .leading)
                                }.contentShape(Rectangle())
                            }.buttonStyle(.plain)
                            ShareLink(item: entry.url) { Label(model.text("Share"), systemImage: "square.and.arrow.up") }.buttonStyle(.bordered)
                        }.padding(.vertical, 5)
                    }
                }
                if let errorMessage { Text(model.text(errorMessage)).foregroundStyle(.orange) }
            }
        }.appTopBar(title)
            .task(id: model.libraryRevision) { await refresh() }
            .refreshable { await refresh() }
            .quickLookPreview($preview)
    }
    private func refresh() async {
        do {
            entries = try await model.store?.files(in: folder) ?? []
            errorMessage = nil
        } catch { errorMessage = SyncLogic.safeError(error) }
    }
}
