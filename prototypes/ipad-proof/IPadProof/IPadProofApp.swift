import SwiftUI
import QuickLook

@main
struct IPadProofApp: App {
    var body: some Scene { WindowGroup { ProofView() } }
}

struct ProofView: View {
    @StateObject private var model = ProofModel()
    @State private var preview: URL?

    var body: some View {
        NavigationStack {
            List {
                Section("1 · Sign in") {
                    TextField("HTTPS Blackboard tenant", text: $model.tenantText)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .keyboardType(.URL).disabled(model.busy || model.hasSession)
                    Button("Open school sign-in") { model.signIn() }.disabled(model.busy)
                    Text("Complete SSO/MFA yourself, then capture cookies. No passwords or cookie values appear in diagnostics.")
                        .font(.caption)
                }
                Section("2 · Verify / session survival") {
                    Button("Verify stored session (also after relaunch)") { model.verify() }
                        .disabled(model.busy || !model.hasSession)
                    Text(model.identity).textSelection(.enabled)
                    Button("Sign out and clear session + web data", role: .destructive) { model.signOut() }
                    Text("Sign out keeps downloaded course files.").font(.caption)
                }
                Section("3 · Current-term courses") {
                    Button("List current-term courses") { model.listCourses() }
                        .disabled(model.busy || !model.hasSession)
                    if !model.courses.isEmpty {
                        Picker("Course", selection: $model.selectedCourseID) {
                            ForEach(model.courses) { course in Text(course.name).tag(course.id) }
                        }.disabled(model.busy)
                            .onChange(of: model.selectedCourseID) { _, _ in model.contents = [] }
                        Button("List top-level contents + attachments") { model.listContents() }.disabled(model.busy)
                    }
                }
                Section("4 · Download one attachment") {
                    ForEach(model.contents) { content in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(content.title).font(.headline)
                            if content.hasChildren { Text("Folder: nested children are outside this proof.").font(.caption) }
                            if let note = content.note { Text(note).font(.caption) }
                            if content.attachments.isEmpty { Text("No top-level attachments listed.").font(.caption) }
                            ForEach(content.attachments) { attachment in
                                Button("Download: " + attachment.name) { model.download(attachment) }.disabled(model.busy)
                            }
                        }
                    }
                }
                Section("5 · Local files") {
                    Text("Files → On My iPad → Blackboard Proof → University").font(.caption)
                    Button("Refresh file list") { model.refreshFiles() }
                    ForEach(model.files, id: \.self) { file in
                        VStack(alignment: .leading) {
                            Text(file.lastPathComponent)
                            HStack {
                                Button("Open") { preview = file }.buttonStyle(.bordered)
                                ShareLink("Share", item: file).buttonStyle(.bordered)
                            }
                        }
                    }
                }
                Section("Result") {
                    if model.busy { ProgressView() }
                    Text(model.status).textSelection(.enabled)
                }
                Section("Copyable plain-text diagnostics") {
                    Button("Copy log") { UIPasteboard.general.string = model.logText }
                    Text(model.logText).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                }
            }
            .navigationTitle("Blackboard iPad Proof")
            .quickLookPreview($preview)
            .sheet(isPresented: $model.showingLogin, onDismiss: { model.webView?.stopLoading() }) {
                NavigationStack {
                    VStack(spacing: 8) {
                        Text(model.browserOrigin).font(.caption).textSelection(.enabled)
                        Text("After sign-in returns to Blackboard, press Capture cookies.").font(.caption)
                        if let view = model.webView {
                            LoginBrowser(webView: view, origin: { model.browserOrigin = $0 }, event: {
                                model.status = $0; model.log($0)
                            })
                        }
                        Text(model.status).font(.caption).padding(.horizontal)
                    }
                    .navigationTitle("School sign-in")
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Close") { model.showingLogin = false }
                        }
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Capture cookies") { model.capture() }.disabled(model.busy)
                        }
                    }
                }.interactiveDismissDisabled(model.busy)
            }
        }
    }
}
