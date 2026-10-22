import SwiftUI
import WebKit
import BlackboardSyncFeatures

@MainActor
final class AppModel: ObservableObject {
    @Published var language = UserDefaults.standard.string(forKey: "language") ?? "en" {
        didSet {
            UserDefaults.standard.set(language, forKey: "language")
            if language != oldValue, features != nil { connectFeatures() }
        }
    }
    @Published var syncOnOpen = UserDefaults.standard.bool(forKey: "syncOnOpen") {
        didSet { UserDefaults.standard.set(syncOnOpen, forKey: "syncOnOpen") }
    }
    @Published var tenantText = SyncLogic.defaultTenant
    @Published var accountName = ""
    @Published var terms: [Term] = []
    @Published var selected: Set<String> = []
    @Published var busy = false
    @Published var syncing = false
    @Published var hasSession = false
    @Published var hasStoredSession = false
    @Published var needsSignIn = false
    @Published var showingLogin = false
    @Published var webView: WKWebView?
    @Published var browserOrigin = ""
    @Published var status = "Not signed in"
    @Published var errorMessage: String?
    @Published var progress = SyncProgress()
    @Published var library = LibraryState()
    @Published var libraryRevision = 0
    @Published var showingSettings = false
    /// Announcements and due dates for the signed-in account; nil while signed out.
    @Published private(set) var features: FeatureModels?
    var loginAfterSettings = false
    private(set) var store: LibraryStore?
    private(set) var scope = UserDefaults.standard.string(forKey: "libraryScope") ?? ""
    private var api: BlackboardAPI?
    private var operation: Task<Void, Never>?
    private var signingOut = false
    private var started = false
    private var featureHTTP: (any BlackboardHTTP)?
    private var featureTenant: URL?
    private var featureRefreshPending = false
    private(set) var featureRefresh: Task<Void, Never>?
    let websiteStore = WKWebsiteDataStore(forIdentifier: UUID(uuidString: "1A1FAFC3-8243-4C32-81A1-026D23F22B6D")!)
    var courses: [Course] { terms.flatMap(\.courses).sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending } }
    var featureCourses: [FeatureCourse] {
        courses.filter { selected.contains($0.id) }.map { FeatureCourse(id: $0.id, name: $0.name) }
    }
    var canSync: Bool { api != nil && hasSession && !needsSignIn && !busy && !selected.isEmpty && store != nil }
    func text(_ key: String) -> String { L10n.text(key, language: language) }

    func start(restoreSession: Bool = true) async {
        guard !started else { return }
        started = true
        do {
            let fm = FileManager.default
            store = try LibraryStore(documents: fm.urls(for: .documentDirectory, in: .userDomainMask)[0],
                                     support: fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0])
            await reloadLibrary()
            terms = library.cachedScope == scope ? library.terms : []
            selected = library.selected[scope] ?? []
            status = library.interrupted ? "Previous sync was interrupted. Sync now to continue." : "Not signed in"
            if restoreSession, let saved = try SessionVault.load() {
                let tenant = try SyncLogic.tenant(saved.tenant)
                tenantText = tenant.absoluteString
                hasStoredSession = true
                install(tenant: tenant, cookies: saved.cookies.compactMap(\.cookie))
                run { [self] in
                    try await verifyAndDiscover()
                    if syncOnOpen && !selected.isEmpty { try await performSync() }
                }
            }
        } catch { fail(error) }
    }

    private func install(tenant: URL, cookies: [HTTPCookie]) {
        api?.cancel()
        // No response bodies, cookie values, tokens or URLs are logged. Diagnostics are on-screen only.
        api = BlackboardAPI(tenant: tenant, cookies: cookies, log: { _ in })
    }

    func run(_ body: @escaping @MainActor () async throws -> Void) {
        guard !busy, !signingOut else { return }
        busy = true; errorMessage = nil
        operation = Task {
            do { try await body(); try Task.checkCancellation() }
            catch {
                if Task.isCancelled { status = "Cancelled. Sync now to continue." }
                else { fail(error) }
            }
            await reloadLibrary()
            if !signingOut { busy = false; syncing = false }
        }
    }

    private func fail(_ error: Error) {
        if (error as? SyncFailure)?.authRequired == true {
            needsSignIn = true; hasSession = false; status = "Sign-in needed"
        } else { status = "Sync did not finish" }
        errorMessage = SyncLogic.safeError(error)
    }

    func signIn() {
        guard !busy else { return }
        do {
            let tenant = try SyncLogic.tenant(tenantText)
            if let api, !SyncLogic.sameOrigin(api.tenant, tenant) {
                throw SyncFailure(message: "Sign out before changing your school address.")
            }
            let config = WKWebViewConfiguration()
            config.websiteDataStore = websiteStore
            let view = WKWebView(frame: .zero, configuration: config)
            webView = view
            view.load(URLRequest(url: tenant))
            showingLogin = true; errorMessage = nil
        } catch { fail(error) }
    }

    func completeSignIn() {
        run { [self] in
            let tenant = try SyncLogic.tenant(tenantText)
            let cookies = await websiteStore.httpCookieStore.allCookies().filter {
                SyncLogic.matchesHost($0, tenant.host ?? "") && ($0.expiresDate.map { $0 > Date() } ?? true)
            }
            guard !cookies.isEmpty else { throw SyncFailure(message: "Complete school sign-in, then try again.") }
            try SessionVault.save(tenant: tenant, cookies: cookies)
            hasStoredSession = true
            install(tenant: tenant, cookies: cookies)
            try await verifyAndDiscover()
            showingLogin = false; webView?.stopLoading(); webView = nil
            // The student chooses courses before the first sync.
        }
    }

    private func verifyAndDiscover() async throws {
        guard let api, let store else { throw SyncFailure(message: "Library unavailable. Relaunch the app to retry.") }
        status = "Checking your account…"
        let me = try await api.json("/learn/api/public/v1/users/me", label: "Account")
        guard let id = me["id"] as? String else { throw SyncFailure(message: "Account response has no user identifier.") }
        let name = me["name"] as? [String: Any] ?? [:]
        let display = [name["given"] as? String, name["family"] as? String].compactMap { $0 }.joined(separator: " ")
        let newScope = MirrorPaths.digest(api.tenant.absoluteString + ":" + id)
        try Task.checkCancellation()
        let accountChanged = scope != newScope || features == nil
        if scope != newScope { terms = []; selected = [] }
        scope = newScope
        UserDefaults.standard.set(scope, forKey: "libraryScope")
        accountName = display.isEmpty ? (me["userName"] as? String ?? "Blackboard") : display
        hasSession = true; needsSignIn = false
        status = "Finding your courses…"
        let found = try await api.courses(userID: id)
        try Task.checkCancellation()
        let snapshot = await store.snapshot()
        let ids = Set(found.flatMap(\.courses).map(\.id))
        selected = (snapshot.selected[scope] ?? ids).intersection(ids)
        terms = found
        try await store.setTerms(found, scope: scope)
        try await store.select(selected, scope: scope)
        for term in found {
            for course in term.courses { _ = try await store.courseFolder(course, term: term, scope: scope) }
        }
        await reloadLibrary()
        status = found.isEmpty ? "No current-term courses found." : "Ready to sync"
        if accountChanged {
            connectFeatures(http: ShellHTTP { [weak self] in self?.api }, tenant: api.tenant)
        } else {
            refreshFeatures()
        }
    }

    /// (Re)creates the announcements and due-date pages; a new account or language starts them afresh.
    func connectFeatures(http: (any BlackboardHTTP)? = nil, tenant: URL? = nil) {
        if let http { featureHTTP = http }
        if let tenant { featureTenant = tenant }
        guard let featureHTTP, let featureTenant else { features = nil; return }
        let courses = ShellCourses { [weak self] in self?.featureCourses ?? [] }
        features = FeatureModels(http: featureHTTP, courses: courses, tenant: featureTenant, language: language) {
            [weak self] in self?.featureSessionExpired()
        }
    }

    #if DEBUG
    /// UI tests only (`--ui-testing-features`): the pages over the package's sample Blackboard.
    func showSampleFeatures() {
        let courses = PreviewData.courses.map { Course(id: $0.id, name: $0.name, termID: "sample", created: nil) }
        terms = [Term(id: "sample", name: "Sample term", start: nil, end: nil, courses: courses)]
        selected = Set(courses.map(\.id))
        connectFeatures(http: PreviewData.http(), tenant: PreviewData.baseURL)
    }
    #endif

    /// Reloads the pages already shown once, after the selection changes or a reconnect. Requests
    /// made while a refresh runs are folded into one more refresh after it.
    func refreshFeatures() {
        guard features != nil else { return }
        featureRefreshPending = true
        guard featureRefresh == nil else { return }
        featureRefresh = Task { [weak self] in
            while let self, self.featureRefreshPending, let features = self.features {
                self.featureRefreshPending = false
                await features.refreshLoaded()
            }
            self?.featureRefresh = nil
        }
    }

    /// The pages found the session expired: the same Reconnect state as a sync that hit it.
    private func featureSessionExpired() {
        guard hasSession, !signingOut else { return }
        fail(SyncFailure(message: "Session expired. Sign in again.", authRequired: true))
    }

    func refreshCourses() { run { [self] in try await verifyAndDiscover() } }

    func setSelected(_ course: Course, enabled: Bool) {
        guard !busy else { return }
        if enabled { selected.insert(course.id) } else { selected.remove(course.id) }
        let ids = selected, scope = scope
        Task {
            do { try await store?.select(ids, scope: scope); await reloadLibrary() }
            catch { fail(error) }
        }
        refreshFeatures()
    }

    func syncNow() {
        guard canSync else { return }
        run { [self] in try await performSync() }
    }
    private func performSync() async throws {
        guard let api, let store else { return }
        syncing = true; progress = SyncProgress(); status = "Syncing…"
        let engine = SyncEngine(api: api, store: store, scope: scope) { [weak self] progress in self?.progress = progress }
        let result = try await engine.run(terms: terms, selected: selected)
        try Task.checkCancellation()
        status = result.failed > 0 ? "Sync did not finish" : "Up to date"
    }
    func cancel() { operation?.cancel() }
    func reloadLibrary() async {
        if let store { library = await store.snapshot(); libraryRevision += 1 }
    }
    func folder(for course: Course) -> String? { library.folders[scope + ":course:" + course.id] }

    func signOut() {
        guard !signingOut else { return }
        signingOut = true; busy = true
        showingLogin = false; webView?.stopLoading(); webView = nil
        operation?.cancel(); api?.cancel()
        featureRefreshPending = false; featureHTTP = nil; featureTenant = nil; features = nil
        let previous = operation
        Task {
            await previous?.value
            var removalError: Error?
            do { try SessionVault.clear() } catch { removalError = error }
            let cookies = await websiteStore.httpCookieStore.allCookies()
            for cookie in cookies { await websiteStore.httpCookieStore.deleteCookie(cookie) }
            await websiteStore.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast)
            api = nil; hasSession = false; hasStoredSession = removalError != nil; needsSignIn = false; accountName = ""
            errorMessage = removalError.map { SyncLogic.safeError($0) }
            status = removalError == nil ? "Signed out. Downloaded files remain on this iPad." : "Keychain removal failed. Try signing out again."
            signingOut = false; busy = false; syncing = false
            await reloadLibrary()
        }
    }

    var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let salutation = text(hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening")
        guard let first = accountName.split(separator: " ").first else { return text("Home") }
        let name = String(first).capitalized(with: Locale(identifier: language))
        return salutation + ", " + name
    }
}
