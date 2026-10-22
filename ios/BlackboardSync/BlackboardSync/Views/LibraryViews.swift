import SwiftUI
import QuickLook

struct CoursesView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
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
                                    Label(model.text("Open folder"), systemImage: "folder").font(.callout)
                                }.fixedSize(horizontal: false, vertical: true)
                            }
                        }.padding(.vertical, 6)
                    }
                }
            }
        }.navigationTitle(model.text("Courses"))
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { model.refreshCourses() } label: { Label(model.text("Refresh courses"), systemImage: "arrow.clockwise") }
                        .disabled(model.busy || !model.hasSession)
                }
            }
    }
}

private struct CourseCheckbox: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(spacing: 12) {
                Image(systemName: configuration.isOn ? "checkmark.square.fill" : "square").font(.title2).foregroundStyle(.blue)
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
                            Image(systemName: activity.status == .failed ? "exclamationmark.circle" : activity.status == .skipped ? "minus.circle" : "doc.richtext")
                                .font(.title2).foregroundStyle(activity.status == .failed ? .orange : .blue)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(activity.name).font(.subheadline.weight(.medium))
                                Text(model.text(activity.status.rawValue)).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if let relative = activity.relativePath {
                                Button(model.text("Open")) {
                                    Task {
                                        do { preview = try await model.store?.url(relative) }
                                        catch { errorMessage = SyncLogic.safeError(error) }
                                    }
                                }.buttonStyle(.bordered)
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
        }.navigationTitle(model.text("Sync activity")).quickLookPreview($preview)
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
                    ContentUnavailableView(model.text("No downloaded files yet."), systemImage: "folder",
                                           description: Text(model.text("Select your courses and tap Sync now.")))
                }
                ForEach(entries) { entry in
                    if entry.isDirectory {
                        NavigationLink {
                            FileBrowser(folder: folder.isEmpty ? entry.url.lastPathComponent : folder + "/" + entry.url.lastPathComponent,
                                        title: entry.url.lastPathComponent)
                        } label: { Label(entry.url.lastPathComponent, systemImage: "folder.fill").padding(.vertical, 5) }
                    } else {
                        HStack(spacing: 14) {
                            Image(systemName: "doc.richtext").foregroundStyle(.blue).font(.title2)
                            Text(entry.url.lastPathComponent).font(.callout).frame(maxWidth: .infinity, alignment: .leading)
                            Button(model.text("Open")) { preview = entry.url }.buttonStyle(.bordered)
                            ShareLink(item: entry.url) { Label(model.text("Share"), systemImage: "square.and.arrow.up") }.buttonStyle(.bordered)
                        }.padding(.vertical, 5)
                    }
                }
                if let errorMessage { Text(model.text(errorMessage)).foregroundStyle(.orange) }
            }
        }.navigationTitle(title)
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
