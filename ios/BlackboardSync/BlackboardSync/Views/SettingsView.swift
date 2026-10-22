import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                Section(model.text("Account")) {
                    Text(model.accountName.isEmpty ? model.text("Not signed in") : model.accountName)
                    TextField(model.text("Your school's Blackboard address"), text: $model.tenantText)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .disabled(model.hasSession || model.needsSignIn || model.hasStoredSession || model.busy)
                    if model.hasSession || model.needsSignIn || model.hasStoredSession {
                        Button(model.text("Sign out"), role: .destructive) { model.signOut() }.disabled(model.busy && !model.syncing)
                    } else {
                        Button(model.text("Sign in to Blackboard")) { model.loginAfterSettings = true; dismiss() }.disabled(model.busy)
                    }
                    Text(model.text("Signing out removes the app's session. Downloaded files stay on this iPad.")).font(.caption).foregroundStyle(.secondary)
                    if let error = model.errorMessage { Text(model.text(error)).font(.caption).foregroundStyle(.orange) }
                }
                Section(model.text("Sync")) {
                    Picker(model.text("Language"), selection: $model.language) {
                        Text("English").tag("en")
                        Text("Türkçe").tag("tr")
                    }
                    Toggle(model.text("Sync on app open"), isOn: $model.syncOnOpen)
                    NavigationLink(model.text("Selected courses")) { CoursesView() }
                    ComingSoon(title: "Automatic background sync", symbol: "clock.arrow.circlepath")
                }
                Section(model.text("Google Calendar")) {
                    ComingSoon(title: "Connect Google Calendar", symbol: "calendar.badge.plus")
                }
                Section(model.text("Folder")) {
                    NavigationLink(model.text("Open folder")) { FileBrowser(folder: "", title: model.text("University")) }
                    Text("Documents/University/<term>/<course>/…").font(.caption).foregroundStyle(.secondary)
                    ComingSoon(title: "Choose another folder", symbol: "folder.badge.gearshape")
                }
                Section(model.text("More")) {
                    ComingSoon(title: "Past terms", symbol: "archivebox")
                    ComingSoon(title: "Notes PDFs", symbol: "doc.text")
                }
                Section(model.text("About & privacy")) {
                    Text("Blackboard Sync · iPad 0.1").font(.headline)
                    Text(model.text("Your sign-in stays on this device in the app's private web store and Keychain. Course files are downloaded directly from your school. No analytics or relay server."))
                    Text(model.text("Files appear in the Files app and can be opened or edited by other apps. Deleting Blackboard Sync removes its local files. Export anything you want to keep first."))
                    Text(model.text("Foreground sync only. Audio, video and files over 500 MB are skipped. HTML responses are rejected. No files are deleted from your mirror."))
                }.font(.callout)
            }.navigationTitle(model.text("Settings"))
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(model.text("Done")) { dismiss() } } }
        }.presentationDetents([.large])
    }
}

struct SignInView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Text(model.text("Complete your school's sign-in and MFA. When Blackboard opens, tap Continue."))
                    .font(.callout).padding()
                if !model.browserOrigin.isEmpty { Text(model.browserOrigin).font(.caption).foregroundStyle(.secondary).padding(.bottom, 8) }
                if let error = model.errorMessage { Text(model.text(error)).font(.callout).foregroundStyle(.orange).padding() }
                if let webView = model.webView {
                    LoginBrowser(webView: webView, origin: { model.browserOrigin = $0 }, event: { model.errorMessage = $0 })
                }
                if model.busy { ProgressView(model.text("Checking your account…")).padding() }
            }.navigationTitle(model.text("Sign in to Blackboard"))
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(model.text("Cancel")) { model.cancel(); model.webView?.stopLoading(); dismiss() }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(model.text("Continue")) { model.completeSignIn() }.disabled(model.busy)
                    }
                }
        }.interactiveDismissDisabled(model.busy)
    }
}
