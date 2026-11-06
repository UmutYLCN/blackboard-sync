import OSLog
import SwiftUI
import WebKit
import BlackboardSyncFeatures

// Only the outcome's fixed name is logged: no cookie, address or sign-on detail.
private let sessionLog = Logger(subsystem: "BlackboardSync", category: "session")

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
    /// Pause / Resume at the top right, as on the Mac: nothing syncs, by hand or on app open, until resumed.
    @Published private(set) var paused = UserDefaults.standard.bool(forKey: "paused") {
        didSet { UserDefaults.standard.set(paused, forKey: "paused") }
    }
    /// The "Automatic re-sign-in" setting and what it remembers; see `tendSession`.
    @Published private(set) var care = SessionCare.saved() {
        didSet { if care != oldValue { care.save() } }
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
    /// The ticked courses on the Send to NotebookLM page and Home's NotebookLM card.
    @Published private(set) var notebookCourses: [NotebookCourse] = []
    @Published var notebookError: String?
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
    private var notebookLedger: NotebookLedger?
    private(set) var featureRefresh: Task<Void, Never>?
    private var sessionRefresh: Task<Bool, Never>?
    private var careLoop: Task<Void, Never>?
    private lazy var defaultSilentSignIn = BrowserSilentSignIn(store: websiteStore)
    var silentSignIn: (any SilentSignIn)?
    var backgroundTasks: any BackgroundScheduling = SystemBackgroundTasks()
    var saveSession: (URL, [HTTPCookie]) throws -> Void = SessionVault.save(tenant:cookies:)
    var loadSession: () throws -> SavedSession? = SessionVault.load
    let websiteStore = WKWebsiteDataStore(forIdentifier: UUID(uuidString: "1A1FAFC3-8243-4C32-81A1-026D23F22B6D")!)
    var courses: [Course] { terms.flatMap(\.courses).sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending } }
    var featureCourses: [FeatureCourse] {
        courses.filter { selected.contains($0.id) }.map { FeatureCourse(id: $0.id, name: $0.name) }
    }
    var canSync: Bool { api != nil && hasSession && !needsSignIn && !busy && !selected.isEmpty && store != nil && !paused }
    /// Like the Mac, Pause waits for the first sign-in; a pause already set can always be lifted.
    var canTogglePause: Bool { !signingOut && (paused || hasSession || hasStoredSession || needsSignIn) }
    /// Home's status headline: a pause shows unless a sync is still winding down.
    var displayStatus: String { paused && !syncing ? "Paused" : status }
    /// Home's note, only while nothing more important is said there, as on the Mac.
    var sessionNoteVisible: Bool {
        hasSession && !needsSignIn && !syncing && !paused && errorMessage == nil && care.noteVisible(Date())
    }
    /// Turning it on again may try right away; turning it off stops everything in the background.
    var automaticSignIn: Bool {
        get { care.enabled }
        set {
            guard newValue != care.enabled else { return }
            care.enabled = newValue
            if newValue { care.failedAt = nil } else { sessionRefresh?.cancel() }
            scheduleBackgroundRefresh()
        }
    }
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
            await openNotebookLedger()
            status = library.interrupted ? "Previous sync was interrupted. Sync now to continue." : "Not signed in"
            if restoreSession, let saved = try SessionVault.load() {
                let tenant = try SyncLogic.tenant(saved.tenant)
                tenantText = tenant.absoluteString
                hasStoredSession = true
                install(tenant: tenant, cookies: saved.cookies.compactMap(\.cookie))
                run { [self] in
                    try await recovering { try await self.verifyAndDiscover() }
                    if syncOnOpen && !selected.isEmpty && !paused { try await recovering { try await self.performSync() } }
                }
            }
        } catch { fail(error) }
    }

    func install(tenant: URL, cookies: [HTTPCookie], pageLoader: ((String) async throws -> [String: Any])? = nil) {
        api?.cancel()
        // No response bodies, cookie values, tokens or URLs are logged. Diagnostics are on-screen only.
        api = BlackboardAPI(tenant: tenant, cookies: cookies, pageLoader: pageLoader, log: { _ in })
    }

    func run(_ body: @escaping @MainActor () async throws -> Void) {
        guard !busy, !signingOut else { return }
        busy = true; errorMessage = nil
        let refresh = sessionRefresh
        operation = Task {
            _ = await refresh?.value // its new session is the one to work with
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
        sessionRefresh?.cancel() // both would work on the same web data
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
            let cookies = SessionCare.sessionCookies(await websiteStore.httpCookieStore.allCookies(), tenant: tenant)
            guard !cookies.isEmpty else { throw SyncFailure(message: "Complete school sign-in, then try again.") }
            try saveSession(tenant, cookies)
            hasStoredSession = true
            care.failedAt = nil // a new sign-on: background sign-in may work again
            install(tenant: tenant, cookies: cookies)
            try await verifyAndDiscover()
            showingLogin = false; webView?.stopLoading(); webView = nil
            // The student chooses courses before the first sync.
        }
    }

    private func verifyAndDiscover() async throws {
        guard let api, let store else { throw SyncFailure(message: "Library unavailable. Relaunch the app to retry.") }
        status = "Checking your account…"
        let me = try await api.json(BlackboardAPI.accountPath, label: "Account")
        care.checkedAt = Date()
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
    /// UI tests only (`--ui-testing-notebook`, after the sample pages): new files in the first
    /// sample course, and a second course that is fully sent.
    func showSampleNotebookFiles() async {
        guard let store, let term = terms.first, term.courses.count > 1 else { return }
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: temporary) }
        do {
            for (course, name) in [(term.courses[0], "Week 1/slides.pdf"), (term.courses[0], "Week 2/notes.txt"), (term.courses[1], "syllabus.pdf")] {
                let folder = try await store.courseFolder(course, term: term, scope: scope)
                try Data(name.utf8).write(to: temporary)
                _ = try await store.install(key: "sample:" + name, desired: folder + "/" + name, temporary: temporary,
                                            fingerprint: nil, etag: nil, lastModified: nil)
            }
            await reloadLibrary()
            if let sent = notebookCourses.first(where: { $0.id == folder(for: term.courses[1]) }) {
                await notebookShareFinished(sent, activity: nil, completed: true, error: nil)
            }
        } catch { notebookError = SyncLogic.safeError(error) }
    }

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
        guard canRefreshSession else { fail(Self.sessionExpired); return }
        Task {
            if await refreshSession() { refreshFeatures() }
            else if hasSession, !signingOut { fail(Self.sessionExpired) }
        }
    }

    func refreshCourses() { run { [self] in try await recovering { try await self.verifyAndDiscover() } } }

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
        run { [self] in try await recovering { try await self.performSync() } }
    }
    private func performSync() async throws {
        guard let api, let store else { return }
        syncing = true; progress = SyncProgress(); status = "Syncing…"
        let engine = SyncEngine(api: api, store: store, scope: scope) { [weak self] progress in self?.progress = progress }
        let result = try await engine.run(terms: terms, selected: selected)
        try Task.checkCancellation()
        status = result.failed > 0 ? "Sync did not finish" : "Up to date"
        care.checkedAt = Date() // a sync keeps the session alive as well
    }
    func cancel() { operation?.cancel() }

    /// Pause also ends a sync that is running right now; Resume syncs right away when Sync on app open is on.
    func togglePause() {
        guard canTogglePause else { return }
        if paused {
            paused = false
            if syncOnOpen { syncNow() }
        } else {
            paused = true
            if syncing { cancel() }
        }
    }
    func reloadLibrary() async {
        if let store { library = await store.snapshot(); libraryRevision += 1; await refreshNotebook() }
    }

    /// A record that cannot be read stops the page rather than listing everything as new again.
    private func openNotebookLedger() async {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        do { notebookLedger = try NotebookLedger(support: support) }
        catch { notebookError = "Library unavailable. Relaunch the app to retry." }
        await refreshNotebook()
    }

    func refreshNotebook() async {
        guard let store else { return }
        let folders = courses.filter { selected.contains($0.id) }.compactMap { folder(for: $0) }
        let local = await store.localFiles(library.records.values.map(\.relativePath))
        guard let notebookLedger else { return } // After the await: a share may have finished meanwhile.
        notebookCourses = NotebookSend.courses(folders: folders, records: Array(library.records.values),
                                               local: local, sent: notebookLedger.sent)
    }

    /// The course as it is right now, for the share sheet; nil when nothing is left to send.
    func notebookCourseToSend(_ id: String) async -> NotebookCourse? {
        notebookError = nil
        await refreshNotebook()
        return notebookCourses.first { $0.id == id && !$0.newFiles.isEmpty }
    }

    /// Takes `course` as it was shared, so a file replaced during the share is listed again.
    func notebookShareFinished(_ course: NotebookCourse, activity: String?, completed: Bool, error: Error?) async {
        do { _ = try notebookLedger?.shareFinished(course, activity: activity, completed: completed, error: error) }
        catch { notebookError = "Sent, but this iPad could not save that. These files may show as new again." }
        await refreshNotebook()
    }
    func folder(for course: Course) -> String? { library.folders[scope + ":course:" + course.id] }

    func signOut() {
        guard !signingOut else { return }
        signingOut = true; busy = true
        showingLogin = false; webView?.stopLoading(); webView = nil
        operation?.cancel(); api?.cancel()
        let refresh = sessionRefresh
        refresh?.cancel()
        featureRefreshPending = false; featureHTTP = nil; featureTenant = nil; features = nil
        let previous = operation
        Task {
            await previous?.value
            _ = await refresh?.value
            var removalError: Error?
            do { try SessionVault.clear() } catch { removalError = error }
            let cookies = await websiteStore.httpCookieStore.allCookies()
            for cookie in cookies { await websiteStore.httpCookieStore.deleteCookie(cookie) }
            await websiteStore.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast)
            api = nil; hasSession = false; hasStoredSession = removalError != nil; needsSignIn = false; accountName = ""
            errorMessage = removalError.map { SyncLogic.safeError($0) }
            status = removalError == nil ? "Signed out. Downloaded files remain on this iPad." : "Keychain removal failed. Try signing out again."
            care = SessionCare(enabled: care.enabled)
            backgroundTasks.cancel()
            signingOut = false; busy = false; syncing = false
            await reloadLibrary()
        }
    }

    // MARK: Staying signed in

    private static let sessionExpired = SyncFailure(message: "Session expired. Sign in again.", authRequired: true)

    private var canRefreshSession: Bool {
        sessionRefresh != nil || (care.mayRefresh(Date()) && hasStoredSession && api != nil && !showingLogin && !signingOut)
    }

    /// The one background sign-in: a caller while it runs shares its result. True once the app has its
    /// new session. On failure nothing changes, and the old session is kept for as long as it works.
    private func refreshSession(timeout: TimeInterval = SessionCare.silentTimeout) async -> Bool {
        if sessionRefresh == nil {
            guard canRefreshSession, let tenant = api?.tenant else { return false }
            let silentSignIn = silentSignIn ?? defaultSilentSignIn
            sessionRefresh = Task { [self] in
                defer { sessionRefresh = nil }
                let result = await silentSignIn.attempt(tenant: tenant, timeout: timeout)
                var outcome = Task.isCancelled ? .cancelled : result.outcome
                if outcome == .refreshed {
                    do {
                        try saveSession(tenant, result.cookies)
                        api?.replaceSession(result.cookies)
                    } catch { outcome = .failed }
                }
                care.record(outcome, now: Date())
                sessionLog.info("Background sign-in: \(outcome.rawValue, privacy: .public)")
                return outcome == .refreshed
            }
        }
        guard let task = sessionRefresh else { return false }
        return await withTaskCancellationHandler { await task.value } onCancel: { task.cancel() }
    }

    /// Runs work that needs the session; when it finds the session over, signs in again and repeats it
    /// once. A failed sign-in lets the work's own failure through, which shows Sign in as always.
    private func recovering(_ work: @MainActor () async throws -> Void) async throws {
        do { try await work() }
        catch let failure as SyncFailure where failure.authRequired {
            guard await refreshSession() else { throw failure }
            try Task.checkCancellation()
            try await work()
        }
    }

    /// One look at the session: nothing, the light keep-alive request, or a background sign-in when the
    /// session is over or nearly so. Running work is left alone: it finds out for itself (`recovering`).
    /// In the background it only keeps the saved session; what the screen shows waits for the next open.
    func tendSession(foreground: Bool = true, timeout: TimeInterval = SessionCare.silentTimeout) async {
        guard care.enabled, !paused, !busy, !showingLogin, !signingOut, hasStoredSession, let api else { return }
        let now = Date()
        let expiresAt = SessionCare.sessionExpiry(api.sessionCookies)
        var action = care.action(now: now, expiresAt: expiresAt)
        var over = expiresAt.map { $0 <= now } ?? false
        if action == .keepAlive {
            care.checkedAt = now
            do {
                _ = try await api.json(BlackboardAPI.accountPath, label: "Account")
                if foreground, needsSignIn || !hasSession { refreshCourses(); return }
                let expiry = SessionCare.sessionExpiry(api.sessionCookies)
                guard care.action(now: Date(), expiresAt: expiry) == .refresh else { return }
            } catch let failure as SyncFailure where failure.authRequired {
                over = true
            } catch {
                sessionLog.info("Keep-alive: no answer")
                return
            }
            action = .refresh
        }
        guard action == .refresh else { return }
        let refreshed = await refreshSession(timeout: timeout)
        guard foreground, !Task.isCancelled else { return }
        if refreshed {
            if needsSignIn || !hasSession { refreshCourses() }
        } else if over, hasSession, !needsSignIn {
            fail(Self.sessionExpired)
        }
    }

    /// While the app is on screen: a look now, then once a minute (`care` says when anything is due).
    func enterForeground(resumeSync: Bool) {
        careLoop?.cancel()
        careLoop = Task { [weak self] in
            await self?.tendSession()
            if resumeSync, self?.syncOnOpen == true { self?.syncNow() }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                if !Task.isCancelled { await self?.tendSession() }
            }
        }
    }

    func enterBackground() {
        careLoop?.cancel(); careLoop = nil
        sessionRefresh?.cancel()
        scheduleBackgroundRefresh()
    }

    /// iPadOS decides when (and whether) this runs, often hours later. It may also start the app for it,
    /// so it needs nothing that `start` set up, and the Keychain is closed while the iPad is locked.
    func backgroundRefresh() async {
        defer { scheduleBackgroundRefresh() }
        if api == nil {
            guard care.enabled, !paused, let saved = try? loadSession(), let tenant = try? SyncLogic.tenant(saved.tenant) else { return }
            hasStoredSession = true
            install(tenant: tenant, cookies: saved.cookies.compactMap(\.cookie))
        }
        await tendSession(foreground: false, timeout: SessionCare.backgroundTimeout)
        care.checkedAt = nil // the next open looks again, and shows what it finds
    }

    private func scheduleBackgroundRefresh() {
        guard care.enabled, !paused, hasStoredSession else { backgroundTasks.cancel(); return }
        let expiresAt = api.flatMap { SessionCare.sessionExpiry($0.sessionCookies) }
        do { try backgroundTasks.submit(earliest: care.nextBackgroundCheck(now: Date(), expiresAt: expiresAt)) }
        catch { sessionLog.info("Background refresh not scheduled") }
    }

    /// The account control's initials, as on the Mac: the first letters of the first two words.
    nonisolated static func initials(_ name: String, language: String) -> String {
        let letters = name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined()
        return letters.isEmpty ? "?" : letters.uppercased(with: Locale(identifier: language))
    }

    var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let salutation = text(hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening")
        guard let first = accountName.split(separator: " ").first else { return text("Home") }
        let name = String(first).capitalized(with: Locale(identifier: language))
        return salutation + ", " + name
    }
}
