import XCTest
@testable import IPadProof

final class ProofLogicTests: XCTestCase {
    private let tenant = URL(string: "https://blackboard.example.edu")!
    private func cookie(_ name: String = "session", domain: String = "blackboard.example.edu",
                        path: String = "/", secure: Bool = true, expires: Date? = nil) -> HTTPCookie {
        var props: [HTTPCookiePropertyKey: Any] = [.name: name, .value: "FAKE_SECRET", .domain: domain, .path: path]
        if secure { props[.secure] = "TRUE" }
        if let expires { props[.expires] = expires }
        return HTTPCookie(properties: props)!
    }

    func testHostOnlyCookieAndDomainBoundaries() {
        let hostOnly = cookie()
        XCTAssertTrue(ProofLogic.matchesHost(hostOnly, "blackboard.example.edu"))
        XCTAssertFalse(ProofLogic.matchesHost(hostOnly, "sub.blackboard.example.edu"))
        XCTAssertFalse(ProofLogic.matchesHost(hostOnly, "blackboard.example.edu.attacker.test"))
        let domain = cookie(domain: ".example.edu")
        XCTAssertTrue(ProofLogic.matchesHost(domain, "blackboard.example.edu"))
        XCTAssertTrue(ProofLogic.matchesHost(domain, "example.edu"))
        XCTAssertFalse(ProofLogic.matchesHost(domain, "badexample.edu"))
    }

    func testPathBoundaryAndLongestPathFirst() {
        let cookies = [cookie("root"), cookie("learn", path: "/learn"), cookie("api", path: "/learn/api/")]
        let url = tenant.appendingPathComponent("learn/api/public/v1/users/me")
        XCTAssertEqual(ProofLogic.cookies(cookies, for: url).map(\.name), ["api", "learn", "root"])
        XCTAssertEqual(ProofLogic.cookies(cookies, for: tenant.appendingPathComponent("learning")).map(\.name), ["root"])
        XCTAssertEqual(ProofLogic.cookies(cookies, for: tenant.appendingPathComponent("learn")).map(\.name), ["learn", "root"])
    }

    func testSecureAndExpiredCookiesAreExcluded() {
        let cookies = [cookie("secure"), cookie("plain", secure: false), cookie("expired", expires: .distantPast)]
        XCTAssertEqual(ProofLogic.cookies(cookies, for: URL(string: "http://blackboard.example.edu/")!).map(\.name), ["plain"])
        XCTAssertEqual(ProofLogic.cookies(cookies, for: tenant).map(\.name), ["secure", "plain"])
    }

    func testCookieRoundTripPreservesScopeAndSessionCookie() {
        let original = cookie(domain: ".example.edu", path: "/learn")
        let restored = StoredCookie(original).cookie!
        XCTAssertEqual(restored.domain, original.domain)
        XCTAssertEqual(restored.path, original.path)
        XCTAssertTrue(restored.isSecure)
        XCTAssertNil(restored.expiresDate)
        XCTAssertEqual(restored.value, "FAKE_SECRET")
    }

    func testHTMLInsteadOfPDFIncludingMislabelledResponse() {
        XCTAssertTrue(ProofLogic.looksLikeHTML(mime: "text/html; charset=UTF-8", prefix: Data()))
        XCTAssertTrue(ProofLogic.looksLikeHTML(mime: "application/pdf", prefix: Data(" \n<!DOCTYPE html><html>Sign in</html>".utf8)))
        XCTAssertTrue(ProofLogic.looksLikeHTML(mime: nil, prefix: Data("\u{feff}<html><form>Password</form>".utf8)))
        XCTAssertTrue(ProofLogic.looksLikeHTML(mime: "application/xhtml+xml", prefix: Data()))
        XCTAssertFalse(ProofLogic.looksLikeHTML(mime: "application/pdf", prefix: Data("%PDF-1.7".utf8)))
        XCTAssertFalse(ProofLogic.looksLikeHTML(mime: "application/octet-stream", prefix: Data([0x50, 0x4b, 0x03, 0x04])))
    }

    func testLoginRedirectMarkers() {
        XCTAssertTrue(ProofLogic.isLogin(URL(string: "https://sso.example.edu/auth-saml/login?token=FAKE_SECRET")))
        XCTAssertTrue(ProofLogic.isLogin(tenant.appendingPathComponent("webapps/login")))
        XCTAssertFalse(ProofLogic.isLogin(tenant.appendingPathComponent("learn/api/public/v1/users/me")))
    }

    func testTenantValidation() throws {
        XCTAssertEqual(try ProofLogic.tenant("https://blackboard.example.edu/").host, tenant.host)
        for bad in ["http://example.edu", "https://user:password@example.edu", "https://example.edu/login", "https://example.edu?token=secret", "https://example.edu#secret"] {
            XCTAssertThrowsError(try ProofLogic.tenant(bad))
        }
    }

    func testErrorsDoNotExposeURLsOrSecrets() {
        let error = NSError(domain: NSURLErrorDomain, code: -1001,
                            userInfo: [NSLocalizedDescriptionKey: "https://example.edu?token=FAKE_SECRET password=secret"])
        let message = ProofLogic.safeError(error)
        XCTAssertTrue(message.contains("-1001"))
        XCTAssertFalse(message.contains("FAKE_SECRET"))
        XCTAssertFalse(message.contains("https"))
    }

    func testSafeNamesCannotEscapeDocuments() {
        XCTAssertEqual(ProofLogic.safeName("../course/file.pdf"), "_course_file.pdf")
        XCTAssertEqual(ProofLogic.safeName(".."), "unnamed")
        XCTAssertFalse(ProofLogic.safeName("bad\nname").contains("\n"))
    }

    func testTransportNeverSendsSchoolCookiesToStorageEvenForParentDomainCookie() {
        let transport = CookieTransport(tenant: tenant, cookies: [cookie(domain: ".example.edu")])
        let own = transport.request(tenant.appendingPathComponent("learn/api"), json: true)
        XCTAssertNotNil(own.value(forHTTPHeaderField: "Cookie"))
        let external = transport.request(URL(string: "https://storage.example.edu/file.pdf?signature=fake")!, json: false)
        XCTAssertNil(external.value(forHTTPHeaderField: "Cookie"))
        XCTAssertNil(external.value(forHTTPHeaderField: "Authorization"))
    }

    func testCookieRotationAndDeletionFromFakeResponses() {
        let transport = CookieTransport(tenant: tenant, cookies: [cookie()])
        let rotated = HTTPURLResponse(url: tenant, statusCode: 200, httpVersion: nil,
            headerFields: ["Set-Cookie": "session=FAKE_NEW; Path=/; Secure; HttpOnly"])!
        transport.receive(rotated)
        XCTAssertEqual(transport.cookies.count, 1)
        XCTAssertEqual(transport.cookies.first?.value, "FAKE_NEW")
        let deleted = HTTPURLResponse(url: tenant, statusCode: 200, httpVersion: nil,
            headerFields: ["Set-Cookie": "session=; Path=/; Max-Age=0"])!
        transport.receive(deleted)
        XCTAssertTrue(transport.cookies.isEmpty)
    }

    func testRedirectDelegateRejectsAPIRedirectAndRescopesDownload() {
        let transport = CookieTransport(tenant: tenant, cookies: [cookie()])
        let session = URLSession(configuration: .ephemeral)
        defer { session.invalidateAndCancel() }
        // Tasks are never resumed: all responses and callbacks are fake, with no network traffic.
        let apiTask = session.dataTask(with: transport.request(tenant, json: true))
        let response = HTTPURLResponse(url: tenant, statusCode: 302, httpVersion: nil, headerFields: nil)!
        let target = URLRequest(url: URL(string: "https://storage.example.edu/file?token=FAKE_SECRET")!)
        transport.urlSession(session, task: apiTask, willPerformHTTPRedirection: response, newRequest: target) {
            XCTAssertNil($0)
        }
        let downloadTask = session.downloadTask(with: transport.request(tenant, json: false))
        transport.urlSession(session, task: downloadTask, willPerformHTTPRedirection: response, newRequest: target) {
            XCTAssertNotNil($0)
            XCTAssertNil($0?.value(forHTTPHeaderField: "Cookie"))
        }
        let login = URLRequest(url: tenant.appendingPathComponent("webapps/login"))
        transport.urlSession(session, task: downloadTask, willPerformHTTPRedirection: response, newRequest: login) {
            XCTAssertNil($0)
        }
        let http = URLRequest(url: URL(string: "http://storage.example.edu/file")!)
        transport.urlSession(session, task: downloadTask, willPerformHTTPRedirection: response, newRequest: http) {
            XCTAssertNil($0)
        }
        XCTAssertFalse(transport.takeMessages().joined().contains("FAKE_SECRET"))
    }

    func testCurrentTermsUseThirtyDayLeadAndExcludeUntaggedCourses() {
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        let course = Course(id: "1", name: "Course", termID: "active", created: now)
        let active = Term(id: "active", name: "Active", start: now.addingTimeInterval(10 * 86400),
                          end: now.addingTimeInterval(100 * 86400), courses: [course])
        let past = Term(id: "past", name: "Past", start: now.addingTimeInterval(-200 * 86400),
                        end: now.addingTimeInterval(-100 * 86400), courses: [course])
        let untagged = Term(id: "", name: "No term", start: nil, end: nil, courses: [course])
        XCTAssertEqual(Term.current([past, active, untagged], now: now).map(\.id), ["active"])
        XCTAssertEqual(Term.current([past, untagged], now: now).map(\.id), ["past"])
        XCTAssertTrue(Term.current([untagged], now: now).isEmpty)
    }

    func testCurrentTermFallsBackToNewestCourseWithoutDates() {
        let old = Course(id: "1", name: "Old", termID: "a", created: .distantPast)
        let recent = Course(id: "2", name: "Recent", termID: "b", created: Date())
        let terms = [Term(id: "a", name: "A", start: nil, end: nil, courses: [old]),
                     Term(id: "b", name: "B", start: nil, end: nil, courses: [recent])]
        XCTAssertEqual(Term.current(terms).map(\.id), ["b"])
    }
}
