import XCTest
import BlackboardSyncFeatures
@testable import BlackboardSync

private final class FeatureFixtureProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, [String: String], Data))!
    static var requested: [URL] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requested.append(request.url!)
        let (code, headers, data) = Self.handler(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1", headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private let tenant = URL(string: "https://school.example.edu")!
private let announcementsPath = "/learn/api/public/v1/courses/_1_1/announcements?limit=100"

final class FeatureWiringTests: XCTestCase {
    @MainActor
    private func client() -> BlackboardAPI {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FeatureFixtureProtocol.self]
        FeatureFixtureProtocol.requested = []
        return BlackboardAPI(tenant: tenant, cookies: [], configuration: config, persistSession: false, log: { _ in })
    }

    private func expect(_ http: ShellHTTP, _ path: String = announcementsPath, throws expected: BlackboardHTTPError,
                        file: StaticString = #filePath, line: UInt = #line) async {
        do { _ = try await http.getJSON(path); XCTFail("Expected \(expected)", file: file, line: line) }
        catch { XCTAssertEqual(error as? BlackboardHTTPError, expected, file: file, line: line) }
    }

    @MainActor
    func testShellHTTPReturnsJSONFromTheTenantAndKeepsPagingLinks() async throws {
        let api = client(); defer { api.cancel() }
        let body = Data(#"{"results":[]}"#.utf8)
        FeatureFixtureProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
            return (200, ["Content-Type": "application/json; charset=utf-8"], body)
        }
        let http = ShellHTTP { api }
        let data = try await http.getJSON(announcementsPath)
        XCTAssertEqual(data, body)
        _ = try await http.getJSON("/learn/api/public/v1/courses/_1_1/announcements?limit=100&offset=100")
        XCTAssertEqual(FeatureFixtureProtocol.requested.map(\.absoluteString), [
            "https://school.example.edu/learn/api/public/v1/courses/_1_1/announcements?limit=100",
            "https://school.example.edu/learn/api/public/v1/courses/_1_1/announcements?limit=100&offset=100",
        ])
    }

    @MainActor
    func testShellHTTPMapsExpiryDeniedMissingAndNonJSONAnswers() async {
        let api = client(); defer { api.cancel() }
        let http = ShellHTTP { api }
        let cases: [(Int, [String: String], String, BlackboardHTTPError)] = [
            (401, ["Content-Type": "application/json"], "{}", .loginRequired),
            (302, ["Location": "https://school.example.edu/webapps/login/"], "", .loginRequired),
            (200, ["Content-Type": "text/html"], "<html>FAKE_SECRET</html>", .loginRequired),
            (200, ["Content-Type": "application/json"], "<!DOCTYPE html><html></html>", .loginRequired),
            (403, ["Content-Type": "application/json"], "{}", .status(403)),
            (404, ["Content-Type": "application/json"], "{}", .status(404)),
            (500, ["Content-Type": "text/plain"], "oops", .status(500)),
            (200, ["Content-Type": "text/plain"], "maintenance", .notJSON),
        ]
        for (code, headers, body, expected) in cases {
            FeatureFixtureProtocol.handler = { _ in (code, headers, Data(body.utf8)) }
            await expect(http, throws: expected)
        }
    }

    @MainActor
    func testShellHTTPRejectsForeignLinksAndNeedsASession() async {
        let api = client(); defer { api.cancel() }
        FeatureFixtureProtocol.handler = { _ in (200, ["Content-Type": "application/json"], Data("{}".utf8)) }
        do {
            _ = try await ShellHTTP { api }.getJSON("https://elsewhere.example.com/learn/api/public/v1/users/me")
            XCTFail("Followed a link outside the tenant")
        } catch {
            XCTAssertNil(error as? BlackboardHTTPError)
            XCTAssertTrue(FeatureFixtureProtocol.requested.isEmpty)
        }
        await expect(ShellHTTP { nil }, throws: .loginRequired)
    }

    @MainActor
    private func signedInModel(language: String = "en") -> (AppModel, FakeBlackboardHTTP) {
        let model = AppModel()
        model.language = language
        let algorithms = Course(id: "_1_1", name: "CSE303 Algorithm Analysis", termID: "t", created: nil)
        let algebra = Course(id: "_2_1", name: "MTH201 Linear Algebra", termID: "t", created: nil)
        model.terms = [Term(id: "t", name: "2026 Fall", start: nil, end: nil, courses: [algorithms, algebra])]
        model.selected = ["_1_1"]
        model.hasSession = true
        let fake = FakeBlackboardHTTP()
        fake.set(announcementsPath, json: """
        {"results": [{"id": "_a1_1", "title": "Midterm room", "body": "<p>Room B-204</p>", "created": "2026-10-12T09:00:00.000Z"}]}
        """)
        fake.set("/learn/api/public/v1/courses/_2_1/announcements?limit=100", json: """
        {"results": [{"id": "_a2_1", "title": "Not selected", "created": "2026-10-12T10:00:00.000Z"}]}
        """)
        fake.set("/learn/api/public/v2/courses/_1_1/gradebook/columns?limit=200", json: #"{"results": []}"#)
        model.connectFeatures(http: fake, tenant: tenant)
        return (model, fake)
    }

    @MainActor
    func testPagesReadOnlySelectedCoursesWithTheAppLanguage() async throws {
        let (model, fake) = signedInModel(language: "tr")
        XCTAssertEqual(model.featureCourses, [FeatureCourse(id: "_1_1", name: "CSE303 Algorithm Analysis")])
        let features = try XCTUnwrap(model.features)
        XCTAssertEqual(features.strings.language, .turkish)
        await features.announcements.loadIfNeeded()
        XCTAssertEqual(features.announcements.phase, .loaded)
        XCTAssertEqual(features.announcements.announcements.map(\.title), ["Midterm room"])
        XCTAssertTrue(features.announcements.announcements[0].detail(in: .gmt, strings: features.strings).hasPrefix("CSE303 Algorithm Analysis"))
        XCTAssertFalse(fake.calls.contains { $0.contains("_2_1") })
        await features.deadlines.loadIfNeeded()
        XCTAssertEqual(features.deadlines.phase, .loaded)
        XCTAssertEqual(features.deadlines.page.days, [])
        XCTAssertEqual(features.deadlines.subtitle, "Bu hafta teslim tarihi yok")
    }

    @MainActor
    func testLanguageChangeRebuildsThePagesAndSignOutClearsThem() async throws {
        let (model, _) = signedInModel()
        let english = try XCTUnwrap(model.features)
        XCTAssertEqual(english.strings.announcementsTab, "Announcements")
        model.language = "tr"
        let turkish = try XCTUnwrap(model.features)
        XCTAssertFalse(english === turkish)
        XCTAssertEqual(turkish.strings.announcementsTab, "Duyurular")
        model.signOut()
        XCTAssertNil(model.features)
        model.language = "en"
        XCTAssertNil(model.features)
    }

    @MainActor
    func testSelectionChangeRefreshesLoadedPagesOnly() async throws {
        let (model, fake) = signedInModel()
        let features = try XCTUnwrap(model.features)
        await features.announcements.loadIfNeeded()
        XCTAssertEqual(features.announcements.announcements.count, 1)
        let algebra = try XCTUnwrap(model.courses.first { $0.id == "_2_1" })
        model.setSelected(algebra, enabled: true)
        await model.featureRefresh?.value
        XCTAssertEqual(features.announcements.announcements.map(\.title), ["Not selected", "Midterm room"])
        XCTAssertEqual(features.deadlines.phase, .idle)
        XCTAssertFalse(fake.calls.contains { $0.contains("gradebook") })
    }

    @MainActor
    func testExpiredSessionLeadsToReconnect() async throws {
        let (model, fake) = signedInModel()
        fake.set(announcementsPath, .failure(.loginRequired))
        let features = try XCTUnwrap(model.features)
        await features.announcements.refresh()
        XCTAssertEqual(features.announcements.phase, .signInRequired)
        XCTAssertEqual(features.announcements.message, "Your Blackboard session has expired.")
        XCTAssertTrue(model.needsSignIn)
        XCTAssertFalse(model.hasSession)
        XCTAssertEqual(model.status, "Sign-in needed")
        XCTAssertFalse(model.canSync)
    }

    @MainActor
    func testOfflineCourseShowsUnreachableWithoutReconnect() async throws {
        let (model, fake) = signedInModel()
        fake.set(announcementsPath, .failure(.status(503)))
        fake.set("/learn/api/v1/courses/_1_1/announcements?limit=100", .failure(.status(503)))
        let features = try XCTUnwrap(model.features)
        await features.announcements.refresh()
        XCTAssertEqual(features.announcements.phase, .failed)
        XCTAssertEqual(features.announcements.message, "Blackboard could not be reached. Pull down to try again.")
        XCTAssertFalse(model.needsSignIn)
        XCTAssertTrue(model.hasSession)
    }
}
