import SwiftUI

@main
struct BlackboardSyncApp: App {
    @StateObject private var model = AppModel()
    @Environment(\.scenePhase) private var phase
    @State private var wasActive = false
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(model)
                .environment(\.locale, Locale(identifier: model.language))
                .task {
                    guard ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil else { return }
                    #if DEBUG
                    let restoreSession = !ProcessInfo.processInfo.arguments.contains("--ui-testing")
                    #else
                    let restoreSession = true
                    #endif
                    await model.start(restoreSession: restoreSession)
                    #if DEBUG
                    if ProcessInfo.processInfo.arguments.contains("--ui-testing-features") { model.showSampleFeatures() }
                    #endif
                }
                .onChange(of: phase) { _, phase in
                    if phase == .active {
                        if wasActive && model.syncOnOpen { model.syncNow() }
                        wasActive = true
                    } else if phase == .background {
                        // Foreground pilot: cancel cooperatively before suspension, preserving checkpoints.
                        model.cancel()
                    }
                }
        }
    }
}
