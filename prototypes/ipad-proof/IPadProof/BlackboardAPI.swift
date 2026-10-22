import Foundation

// Delegate callbacks are off the main actor. The lock protects the private cookie jar/diagnostics.
final class CookieTransport: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    let tenant: URL
    private let lock = NSLock()
    private var jar: [HTTPCookie]
    private var messages: [String] = []

    init(tenant: URL, cookies: [HTTPCookie]) {
        self.tenant = tenant
        self.jar = cookies.filter { ProofLogic.matchesHost($0, tenant.host ?? "") }
    }

    var cookies: [HTTPCookie] {
        lock.lock(); defer { lock.unlock() }
        return jar.filter { $0.expiresDate.map { $0 > Date() } ?? true }
    }

    func request(_ url: URL, json: Bool) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpShouldHandleCookies = false
        request.setValue(json ? "application/json" : "*/*", forHTTPHeaderField: "Accept")
        if ProofLogic.sameOrigin(url, tenant) {
            request.setValue(ProofLogic.cookieHeader(cookies, for: url), forHTTPHeaderField: "Cookie")
        }
        return request
    }

    func receive(_ response: HTTPURLResponse) {
        guard let url = response.url, ProofLogic.sameOrigin(url, tenant) else { return }
        let headers = response.allHeaderFields.reduce(into: [String: String]()) {
            if let key = $1.key as? String, let value = $1.value as? String { $0[key] = value }
        }
        let incoming = HTTPCookie.cookies(withResponseHeaderFields: headers, for: url)
            .filter { ProofLogic.matchesHost($0, tenant.host ?? "") }
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
        let login = ProofLogic.isLogin(target)
        let allowed = !json && !login && target?.scheme == "https"
        lock.lock()
        messages.append("HTTP \(response.statusCode) redirect: \(login ? "login page" : "destination URL redacted"); \(allowed ? "following with cookies re-scoped" : "stopped").")
        lock.unlock()
        guard allowed, let target else { completionHandler(nil); return }
        // Build afresh: do not forward Cookie/Authorization headers to storage/SSO origins.
        completionHandler(self.request(target, json: false))
    }
}

@MainActor
final class BlackboardAPI {
    let tenant: URL
    private let transport: CookieTransport
    private let session: URLSession
    private let log: (String) -> Void
    private let pageLoader: ((String) async throws -> [String: Any])?

    init(tenant: URL, cookies: [HTTPCookie],
         pageLoader: ((String) async throws -> [String: Any])? = nil,
         log: @escaping (String) -> Void) {
        self.tenant = tenant
        self.transport = CookieTransport(tenant: tenant, cookies: cookies)
        self.log = log
        self.pageLoader = pageLoader
        let config = URLSessionConfiguration.ephemeral
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
              ProofLogic.sameOrigin(url, tenant), url.user == nil, url.password == nil else {
            throw ProofFailure(message: "Rejected an API link outside the HTTPS tenant origin.")
        }
        return url
    }

    private func record(_ response: URLResponse, label: String) throws -> HTTPURLResponse {
        for message in transport.takeMessages() { log(message) }
        guard let http = response as? HTTPURLResponse else {
            throw ProofFailure(message: "\(label): no HTTP response.")
        }
        transport.receive(http)
        try SessionVault.save(tenant: tenant, cookies: transport.cookies)
        log("\(label): HTTP \(http.statusCode).")
        if (300...399).contains(http.statusCode) {
            throw ProofFailure(message: "\(label): HTTP \(http.statusCode) redirect stopped; sign-in or redirect required (URL redacted).")
        }
        if http.statusCode == 401 || ProofLogic.isLogin(http.url) {
            throw ProofFailure(message: "\(label): session expired or login page returned; sign in again.")
        }
        guard (200...299).contains(http.statusCode) else {
            throw ProofFailure(message: "\(label): HTTP \(http.statusCode)\(http.statusCode == 403 ? " (access denied)" : ""); body redacted.")
        }
        return http
    }

    func json(_ path: String, label: String, attachmentListing: Bool = false) async throws -> [String: Any] {
        if let pageLoader { return try await pageLoader(path) }
        let (data, response) = try await session.data(for: transport.request(try url(path), json: true))
        // Inspect only the structured message, never include the body in diagnostics.
        if attachmentListing, let http = response as? HTTPURLResponse,
           ProofLogic.noAttachments(status: http.statusCode, data: data) {
            transport.receive(http)
            try SessionVault.save(tenant: tenant, cookies: transport.cookies)
            for message in transport.takeMessages() { log(message) }
            log("Attachments: no attachment collection for this item.")
            return ["results": [[String: Any]]()]
        }
        let http = try record(response, label: label)
        guard http.mimeType?.lowercased().contains("json") == true,
              !ProofLogic.looksLikeHTML(mime: http.mimeType, prefix: data),
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ProofFailure(message: "\(label): HTTP \(http.statusCode), expected JSON; HTML/non-JSON returned (body redacted).")
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
                throw ProofFailure(message: "\(label): repeated page or 100-page proof limit reached.")
            }
            let page = try await json(path, label: label, attachmentListing: attachmentListing)
            guard let rows = page["results"] as? [[String: Any]] else {
                throw ProofFailure(message: "\(label): JSON has no results array.")
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
                termID: term, created: ProofLogic.date(course["created"] as? String)))
        }
        var terms: [Term] = []
        for id in groups.keys.sorted() where !id.isEmpty {
            var raw: [String: Any] = [:]
            do { raw = try await json("/learn/api/public/v1/terms/\(Self.segment(id))", label: "Term") }
            catch {
                log("Public term lookup failed: " + ProofLogic.safeError(error))
                do { raw = try await json("/learn/api/v1/terms/\(Self.segment(id))", label: "Term fallback") }
                catch { log("Term dates unavailable; newest-course fallback may apply. " + ProofLogic.safeError(error)) }
            }
            let duration = (raw["availability"] as? [String: Any])?["duration"] as? [String: Any] ?? [:]
            terms.append(Term(id: id, name: raw["name"] as? String ?? id,
                start: ProofLogic.date(duration["start"] as? String),
                end: ProofLogic.date(duration["end"] as? String), courses: groups[id] ?? []))
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
            if ProofLogic.noAttachmentHandlers.contains(item.handlerID ?? "") {
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
                item.note = ProofLogic.safeError(error)
                log("Attachment listing: " + ProofLogic.safeError(error))
            }
            contents.append(item)
        }
        return contents
    }

    func download(_ attachment: Attachment, course: Course) async throws -> URL {
        let path = "/learn/api/public/v1/courses/\(Self.segment(course.id))/contents/\(Self.segment(attachment.contentID))/attachments/\(Self.segment(attachment.id))/download"
        let (temporary, response) = try await session.download(for: transport.request(try url(path), json: false))
        defer { try? FileManager.default.removeItem(at: temporary) }
        let http = try record(response, label: "Download")
        let handle = try FileHandle(forReadingFrom: temporary)
        defer { try? handle.close() }
        let prefix = try handle.read(upToCount: 4096) ?? Data()
        guard !ProofLogic.looksLikeHTML(mime: http.mimeType, prefix: prefix) else {
            throw ProofFailure(message: "Download rejected: HTML/login page returned instead of a file; nothing saved.")
        }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let folder = documents.appendingPathComponent("University", isDirectory: true)
            .appendingPathComponent(ProofLogic.safeName(course.name) + " (" + ProofLogic.safeName(course.id) + ")", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let name = ProofLogic.safeName(attachment.name)
        var destination = folder.appendingPathComponent(name)
        if FileManager.default.fileExists(atPath: destination.path) {
            destination = folder.appendingPathComponent(UUID().uuidString.prefix(8) + "-" + name)
        }
        // Move only validated responses into the Files-visible directory; preserve existing documents.
        try FileManager.default.moveItem(at: temporary, to: destination)
        return destination
    }
}
