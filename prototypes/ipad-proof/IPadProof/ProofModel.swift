import SwiftUI
import WebKit

@MainActor
final class ProofModel: ObservableObject {
    @Published var tenantText = ProofLogic.defaultTenant
    @Published var showingLogin = false
    @Published var webView: WKWebView?
    @Published var browserOrigin = "No page loaded"
    @Published var busy = false
    @Published var status = "Ready. Sign in, then capture the Blackboard cookies."
    @Published var identity = "Not verified"
    @Published var courses: [Course] = []
    @Published var selectedCourseID = ""
    @Published var contents: [ContentItem] = []
    @Published var files: [URL] = []
    @Published var lines: [String] = ["iPad proof: diagnostics redact cookies, credentials, response bodies and URLs."]
    @Published var hasSession = false

    let websiteStore = WKWebsiteDataStore(forIdentifier: UUID(uuidString: "E5FF2747-FA6E-4F89-A765-1C1154DE3B59")!)
    private var api: BlackboardAPI?
    private var userID: String?
    private var activeTask: Task<Void, Never>?
    private var signingOut = false
    var selectedCourse: Course? { courses.first { $0.id == selectedCourseID } }
    var logText: String { lines.joined(separator: "\n") }

    init() {
        do {
            if let saved = try SessionVault.load() {
                let tenant = try ProofLogic.tenant(saved.tenant)
                tenantText = tenant.absoluteString
                installAPI(tenant: tenant, cookies: saved.cookies.compactMap(\.cookie))
                status = "Stored session loaded from Keychain. Press Verify stored session; no network call has run."
                log("Stored session restored; credentials redacted. Verification is manual.")
            }
        } catch { status = ProofLogic.safeError(error); log(status) }
        refreshFiles()
    }

    func log(_ message: String) {
        lines.append("\(Date().formatted(date: .omitted, time: .standard))  \(message)")
    }

    private func installAPI(tenant: URL, cookies: [HTTPCookie]) {
        api?.cancel()
        api = BlackboardAPI(tenant: tenant, cookies: cookies) { [weak self] in self?.log($0) }
        hasSession = true
        userID = nil
        identity = "Not verified"
        courses = []; selectedCourseID = ""; contents = []
    }

    func run(_ label: String, operation: @escaping @MainActor () async throws -> Void) {
        guard !busy else { return }
        busy = true
        status = label + "…"
        log(label + " started.")
        activeTask = Task {
            do {
                try await operation()
                try Task.checkCancellation()
            } catch {
                status = Task.isCancelled ? "Operation cancelled." : ProofLogic.safeError(error)
                log(status)
            }
            if !signingOut { busy = false }
        }
    }

    func signIn() {
        do {
            let tenant = try ProofLogic.tenant(tenantText)
            if let api, !ProofLogic.sameOrigin(api.tenant, tenant) {
                throw ProofFailure(message: "Sign out before switching tenants, so school and identity-provider state are cleared.")
            }
            let config = WKWebViewConfiguration()
            config.websiteDataStore = websiteStore
            webView = WKWebView(frame: .zero, configuration: config)
            webView?.load(URLRequest(url: tenant))
            showingLogin = true
            status = "Complete school sign-in and MFA in the web view, then press Capture cookies."
            log("Sign-in web view opened. Navigation URLs and form data are redacted.")
        } catch { status = ProofLogic.safeError(error); log(status) }
    }

    func capture() {
        run("Capture cookies") { [self] in
            let tenant = try ProofLogic.tenant(tenantText)
            let all = await websiteStore.httpCookieStore.allCookies()
            let cookies = all.filter { ProofLogic.matchesHost($0, tenant.host ?? "")
                && ($0.expiresDate.map { $0 > Date() } ?? true) }
            guard !cookies.isEmpty else {
                throw ProofFailure(message: "No unexpired Blackboard-host cookies found. Complete sign-in and try again.")
            }
            try SessionVault.save(tenant: tenant, cookies: cookies)
            installAPI(tenant: tenant, cookies: cookies)
            showingLogin = false
            webView?.stopLoading()
            status = "Captured \(cookies.count) Blackboard cookies in Keychain (values redacted). Press Verify."
            log(status)
        }
    }

    func verify() {
        run("Verify stored session") { [self] in
            guard let api else { throw ProofFailure(message: "Sign in and capture cookies first.") }
            userID = nil; identity = "Verification in progress"; courses = []; contents = []
            let me = try await api.json("/learn/api/public/v1/users/me", label: "Verify users/me")
            guard let id = me["id"] as? String else { throw ProofFailure(message: "Verify: JSON has no user id.") }
            let name = me["name"] as? [String: Any] ?? [:]
            let displayName = [name["given"] as? String, name["family"] as? String].compactMap { $0 }.joined(separator: " ")
            userID = id
            identity = "ID: \(id)\nName: \(displayName.isEmpty ? (me["userName"] as? String ?? "unavailable") : displayName)"
            status = "Verify succeeded. Identity shown below."
            log("Verify succeeded; identity is shown on screen and omitted from the log.")
        }
    }

    func listCourses() {
        run("List current-term courses") { [self] in
            guard let api, let userID else { throw ProofFailure(message: "Verify the session first.") }
            courses = []; contents = []; selectedCourseID = ""
            let terms = try await api.courses(userID: userID)
            courses = terms.flatMap(\.courses).sorted { $0.name < $1.name }
            selectedCourseID = courses.first?.id ?? ""
            status = "Found \(courses.count) courses in \(terms.count) selected term(s): " + terms.map(\.name).joined(separator: ", ")
            log("Current-term selection: \(terms.count) terms, \(courses.count) courses. Dates use a 30-day lead, then latest-start/newest-course fallback.")
        }
    }

    func listContents() {
        run("List top-level contents and attachments") { [self] in
            guard let api, let course = selectedCourse else { throw ProofFailure(message: "Select a course first.") }
            contents = []
            contents = try await api.contents(courseID: course.id)
            status = "Found \(contents.count) top-level items. Nested folders are marked; this proof lists top-level attachments only."
            log("Contents: \(contents.count) top-level items, \(contents.reduce(0) { $0 + $1.attachments.count }) attachments.")
        }
    }

    func download(_ attachment: Attachment) {
        run("Download selected attachment") { [self] in
            guard let api, let course = selectedCourse else { throw ProofFailure(message: "Select a course first.") }
            _ = try await api.download(attachment, course: course)
            refreshFiles()
            status = "Download saved under Documents/University. Use Open or Share below, or open Files → On My iPad → Blackboard Proof."
            log("Download validated and saved in Documents/University; file name omitted from log.")
        }
    }

    func refreshFiles() {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("University", isDirectory: true)
        let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey], options: [.skipsHiddenFiles])
        files = (enumerator?.allObjects as? [URL] ?? []).filter {
            (try? $0.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true
        }.sorted { $0.path < $1.path }
    }

    func signOut() {
        guard !signingOut else { return }
        signingOut = true; busy = true
        showingLogin = false
        webView?.stopLoading(); webView = nil
        activeTask?.cancel(); api?.cancel()
        let previous = activeTask
        Task {
            await previous?.value
            // Always clear WebKit/HTTP state even if deleting the Keychain item fails.
            var keychainError: Error?
            do { try SessionVault.clear() } catch { keychainError = error }
            let cookies = await websiteStore.httpCookieStore.allCookies()
            for cookie in cookies { await websiteStore.httpCookieStore.deleteCookie(cookie) }
            await websiteStore.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast)
            api = nil; hasSession = false; userID = nil
            identity = "Not verified"; courses = []; contents = []; selectedCourseID = ""
            status = keychainError.map { "Web data cleared; Keychain removal failed: " + ProofLogic.safeError($0) }
                ?? "Signed out: Keychain, HTTP session, and all app web data cleared. Downloaded files remain."
            log(status)
            signingOut = false; busy = false
        }
    }
}
