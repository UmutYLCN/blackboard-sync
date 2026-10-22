import Foundation

// Delegate callbacks are off the main actor. The lock protects the private cookie jar/diagnostics.
final class CookieTransport: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    let tenant: URL
    private let lock = NSLock()
    private var jar: [HTTPCookie]
    private var messages: [String] = []

    init(tenant: URL, cookies: [HTTPCookie]) {
        self.tenant = tenant
        self.jar = cookies.filter { SyncLogic.matchesHost($0, tenant.host ?? "") }
    }

    var cookies: [HTTPCookie] {
        lock.lock(); defer { lock.unlock() }
        return jar.filter { $0.expiresDate.map { $0 > Date() } ?? true }
    }

    func request(_ url: URL, json: Bool) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpShouldHandleCookies = false
        request.setValue(json ? "application/json" : "*/*", forHTTPHeaderField: "Accept")
        if SyncLogic.sameOrigin(url, tenant) {
            request.setValue(SyncLogic.cookieHeader(cookies, for: url), forHTTPHeaderField: "Cookie")
        }
        return request
    }

    func receive(_ response: HTTPURLResponse) {
        guard let url = response.url, SyncLogic.sameOrigin(url, tenant) else { return }
        let headers = response.allHeaderFields.reduce(into: [String: String]()) {
            if let key = $1.key as? String, let value = $1.value as? String { $0[key] = value }
        }
        let incoming = HTTPCookie.cookies(withResponseHeaderFields: headers, for: url)
            .filter { SyncLogic.matchesHost($0, tenant.host ?? "") }
        lock.lock(); defer { lock.unlock() }
        for cookie in incoming {
            jar.removeAll { $0.name == cookie.name && $0.domain == cookie.domain && $0.path == cookie.path }
            if cookie.expiresDate.map({ $0 > Date() }) ?? true { jar.append(cookie) }
        }
    }

    func takeMessages() -> [String] {
        lock.lock(); defer { lock.unlock() }
        defer { messages.removeAll() }
        return messages
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        receive(response)
        let json = task.originalRequest?.value(forHTTPHeaderField: "Accept") == "application/json"
        let target = request.url
        let login = SyncLogic.isLogin(target)
        let allowed = !json && !login && target?.scheme == "https"
        lock.lock()
        messages.append("HTTP \(response.statusCode) redirect: \(login ? "login page" : "destination URL redacted"); \(allowed ? "following with cookies re-scoped" : "stopped").")
        lock.unlock()
        guard allowed, let target else { completionHandler(nil); return }
        // Build afresh: do not forward Cookie/Authorization headers to storage/SSO origins.
        var redirected = self.request(target, json: false)
        for header in ["If-None-Match", "If-Modified-Since"] {
            redirected.setValue(task.originalRequest?.value(forHTTPHeaderField: header), forHTTPHeaderField: header)
        }
        completionHandler(redirected)
    }
}

@MainActor
final class BlackboardAPI: MirrorAPI {
    let tenant: URL
    private let transport: CookieTransport
    private let session: URLSession
    private let log: (String) -> Void
    private let persistSession: Bool
    private let pageLoader: ((String) async throws -> [String: Any])?

    init(tenant: URL, cookies: [HTTPCookie],
         pageLoader: ((String) async throws -> [String: Any])? = nil,
         configuration: URLSessionConfiguration? = nil, persistSession: Bool = true,
         log: @escaping (String) -> Void) {
        self.tenant = tenant
        self.transport = CookieTransport(tenant: tenant, cookies: cookies)
        self.log = log
        self.pageLoader = pageLoader
        self.persistSession = persistSession
        let config = configuration ?? URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.urlCredentialStorage = nil
        config.urlCache = nil
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config, delegate: transport, delegateQueue: nil)
    }

    func cancel() { session.invalidateAndCancel() }

    private func url(_ path: String) throws -> URL {
        guard let url = URL(string: path, relativeTo: tenant)?.absoluteURL,
              SyncLogic.sameOrigin(url, tenant), url.user == nil, url.password == nil else {
            throw SyncFailure(message: "Rejected an API link outside the HTTPS tenant origin.")
        }
        return url
    }

    private func record(_ response: URLResponse, label: String) throws -> HTTPURLResponse {
        for message in transport.takeMessages() { log(message) }
        guard let http = response as? HTTPURLResponse else {
            throw SyncFailure(message: "\(label): no HTTP response.")
        }
        transport.receive(http)
        if persistSession { try SessionVault.save(tenant: tenant, cookies: transport.cookies) }
        log("\(label): HTTP \(http.statusCode).")
        if (300...399).contains(http.statusCode) {
            throw SyncFailure(message: "Session expired. Sign in again.", authRequired: true)
        }
        if http.statusCode == 401 || SyncLogic.isLogin(http.url) {
            throw SyncFailure(message: "Session expired. Sign in again.", authRequired: true)
        }
        guard (200...299).contains(http.statusCode) else {
            throw SyncFailure(message: "\(label): HTTP \(http.statusCode)\(http.statusCode == 403 ? " (access denied)" : ""); body redacted.")
        }
        return http
    }

    func json(_ path: String, label: String, attachmentListing: Bool = false) async throws -> [String: Any] {
        if let pageLoader { return try await pageLoader(path) }
        let (data, response) = try await session.data(for: transport.request(try url(path), json: true))
        // Inspect only the structured message, never include the body in diagnostics.
        if attachmentListing, let http = response as? HTTPURLResponse,
           SyncLogic.noAttachments(status: http.statusCode, data: data) {
            transport.receive(http)
            if persistSession { try SessionVault.save(tenant: tenant, cookies: transport.cookies) }
            for message in transport.takeMessages() { log(message) }
            log("Attachments: no attachment collection for this item.")
            return ["results": [[String: Any]]()]
        }
        let http = try record(response, label: label)
        guard http.mimeType?.lowercased().contains("json") == true,
              !SyncLogic.looksLikeHTML(mime: http.mimeType, prefix: data),
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw SyncFailure(message: "Session expired or non-JSON response. Sign in again.", authRequired: true)
        }
        return object
    }

    func paged(_ path: String, label: String, attachmentListing: Bool = false) async throws -> [[String: Any]] {
        var next: String? = path
        var visited: Set<URL> = []
        var results: [[String: Any]] = []
        while let path = next {
            let pageURL = try url(path)
            guard visited.insert(pageURL).inserted, visited.count <= 100 else {
                throw SyncFailure(message: "\(label): repeated page or 100-page safety limit reached.")
            }
            let page = try await json(path, label: label, attachmentListing: attachmentListing)
            guard let rows = page["results"] as? [[String: Any]] else {
                throw SyncFailure(message: "\(label): JSON has no results array.")
            }
            results += rows
            next = (page["paging"] as? [String: Any])?["nextPage"] as? String
        }
        return results
    }

    static func segment(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }

    func courses(userID: String) async throws -> [Term] {
        let memberships = try await paged("/learn/api/public/v1/users/\(Self.segment(userID))/courses?expand=course&limit=100", label: "Memberships")
        var groups: [String: [Course]] = [:]
        var seen: Set<String> = []
        for membership in memberships {
            if (membership["availability"] as? [String: Any])?["available"] as? String == "No" { continue }
            var course = membership["course"] as? [String: Any]
            if course == nil, let id = membership["courseId"] as? String {
                course = try await json("/learn/api/public/v3/courses/\(Self.segment(id))", label: "Course detail")
            }
            guard let course, let id = course["id"] as? String, seen.insert(id).inserted,
                  (course["availability"] as? [String: Any])?["available"] as? String != "No" else { continue }
            let term = course["termId"] as? String ?? ""
            groups[term, default: []].append(Course(id: id, name: course["name"] as? String ?? id,
                termID: term, created: SyncLogic.date(course["created"] as? String), code: course["courseId"] as? String ?? id))
        }
        var terms: [Term] = []
        for id in groups.keys.sorted() where !id.isEmpty {
            var raw: [String: Any] = [:]
            do { raw = try await json("/learn/api/public/v1/terms/\(Self.segment(id))", label: "Term") }
            catch {
                if Task.isCancelled || (error as? SyncFailure)?.authRequired == true { throw error }
                log("Public term lookup failed: " + SyncLogic.safeError(error))
                do { raw = try await json("/learn/api/v1/terms/\(Self.segment(id))", label: "Term fallback") }
                catch {
                    if Task.isCancelled || (error as? SyncFailure)?.authRequired == true { throw error }
                    log("Term dates unavailable; newest-course fallback may apply. " + SyncLogic.safeError(error)) }
            }
            let duration = (raw["availability"] as? [String: Any])?["duration"] as? [String: Any] ?? [:]
            terms.append(Term(id: id, name: raw["name"] as? String ?? id,
                start: SyncLogic.date(duration["start"] as? String),
                end: SyncLogic.date(duration["end"] as? String), courses: groups[id] ?? []))
        }
        if groups[""] != nil { log("Courses without a term excluded, matching desktop current-term selection.") }
        return Term.current(terms)
    }

    func contents(courseID: String, parentID: String? = nil) async throws -> [ContentItem] {
        let root = "/learn/api/public/v1/courses/\(Self.segment(courseID))/contents"
        let path = parentID.map { root + "/\(Self.segment($0))/children" } ?? root
        let rows = try await paged(path + "?limit=200", label: parentID == nil ? "Top-level contents" : "Folder children")
        var contents: [ContentItem] = []
        for row in rows {
            guard let id = row["id"] as? String else { continue }
            var item = ContentItem(id: id, title: row["title"] as? String ?? id,
                                   hasChildren: row["hasChildren"] as? Bool ?? false,
                                   handlerID: (row["contentHandler"] as? [String: Any])?["id"] as? String,
                                   attachments: [])
            item.modified = row["modified"] as? String
            let handler = row["contentHandler"] as? [String: Any] ?? [:]
            item.embedded = EmbeddedFiles.find([EmbeddedFiles.body(row["body"]), EmbeddedFiles.body(row["description"]), EmbeddedFiles.body(handler["instructions"])].joined(separator: "\n"))
            if SyncLogic.noAttachmentHandlers.contains(item.handlerID ?? "") {
                item.note = "No attachments for this content type."
                contents.append(item)
                continue
            }
            do {
                let attachments = try await paged(root + "/\(Self.segment(id))/attachments", label: "Attachments", attachmentListing: true)
                item.attachments = attachments.compactMap {
                    guard let attachmentID = $0["id"] as? String else { return nil }
                    return Attachment(id: attachmentID, contentID: id, name: $0["fileName"] as? String ?? "attachment")
                }
            } catch {
                if Task.isCancelled || (error as? SyncFailure)?.authRequired == true { throw error }
                item.note = SyncLogic.safeError(error)
                log("Attachment listing: " + SyncLogic.safeError(error))
            }
            contents.append(item)
        }
        return contents
    }

    func fetch(path: String, name: String, previous: FileRecord?) async throws -> TransferResult {
        var request = transport.request(try url(path), json: false)
        request.setValue(previous?.etag, forHTTPHeaderField: "If-None-Match")
        request.setValue(previous?.lastModified, forHTTPHeaderField: "If-Modified-Since")
        let (bytes, response) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        if let http = response as? HTTPURLResponse, http.statusCode == 304 {
            transport.receive(http)
            if persistSession { try SessionVault.save(tenant: tenant, cookies: transport.cookies) }
            guard previous != nil else { throw SyncFailure(message: "Unexpected unchanged response. Retry sync.") }
            return .unchanged
        }
        let http = try record(response, label: "Download")
        if MirrorPaths.isMedia(name, mime: http.mimeType) || MirrorPaths.isMedia(http.suggestedFilename ?? "") {
            return .skipped("Audio and video are skipped.")
        }
        if http.expectedContentLength > TransferResult.sizeCap {
            return .skipped("Files over 500 MB are skipped.")
        }
        if SyncLogic.looksLikeHTML(mime: http.mimeType, prefix: Data()) {
            throw SyncFailure(message: "HTML/login page returned instead of a file.", authRequired: true)
        }
        return try await Self.stream(bytes, response: http)
    }

    // File streaming runs off the main actor; memory is bounded to one 64 KB chunk.
    nonisolated private static func stream(_ bytes: URLSession.AsyncBytes, response: HTTPURLResponse) async throws -> TransferResult {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("bbsync-" + UUID().uuidString)
        FileManager.default.createFile(atPath: temporary.path, contents: nil,
                                      attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var keep = false
        defer { if !keep { try? FileManager.default.removeItem(at: temporary) } }
        let handle = try FileHandle(forWritingTo: temporary)
        defer { try? handle.close() }
        var chunk = Data()
        chunk.reserveCapacity(65536)
        var prefix = Data()
        var count: Int64 = 0
        for try await byte in bytes {
            try Task.checkCancellation()
            count += 1
            if count > TransferResult.sizeCap { return .skipped("Files over 500 MB are skipped.") }
            if prefix.count < 4096 { prefix.append(byte) }
            chunk.append(byte)
            if chunk.count == 65536 {
                if SyncLogic.looksLikeHTML(mime: response.mimeType, prefix: prefix) {
                    throw SyncFailure(message: "HTML/login page returned instead of a file.", authRequired: true)
                }
                try handle.write(contentsOf: chunk); chunk.removeAll(keepingCapacity: true)
            }
        }
        guard !SyncLogic.looksLikeHTML(mime: response.mimeType, prefix: prefix) else {
            throw SyncFailure(message: "HTML/login page returned instead of a file.", authRequired: true)
        }
        try handle.write(contentsOf: chunk)
        try handle.synchronize()
        if response.expectedContentLength >= 0, response.value(forHTTPHeaderField: "Content-Encoding") == nil,
           count != response.expectedContentLength {
            throw SyncFailure(message: "Incomplete download. Retry sync.")
        }
        keep = true
        return .file(temporary, etag: response.value(forHTTPHeaderField: "ETag"), lastModified: response.value(forHTTPHeaderField: "Last-Modified"))
    }
}
