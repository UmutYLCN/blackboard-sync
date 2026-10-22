import XCTest
@testable import BlackboardSync

private final class FixtureProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, [String: String], Data))!
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let (code, headers, data) = Self.handler(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1", headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class TransferTests: XCTestCase {
    @MainActor
    private func client() -> BlackboardAPI {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FixtureProtocol.self]
        return BlackboardAPI(tenant: URL(string: "https://school.example.edu")!, cookies: [], configuration: config, persistSession: false, log: { _ in })
    }

    @MainActor
    func testConditionalRequestReturnsNoBodyFor304() async throws {
        FixtureProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "If-None-Match"), "test-etag")
            XCTAssertEqual(request.value(forHTTPHeaderField: "If-Modified-Since"), "test-date")
            return (304, [:], Data())
        }
        let api = client(); defer { api.cancel() }
        let record = FileRecord(relativePath: "Term/Course/notes.pdf", hash: "hash", fingerprint: nil, etag: "test-etag", lastModified: "test-date", updated: Date(), size: 3)
        let result = try await api.fetch(path: "/file", name: "notes.pdf", previous: record)
        guard case .unchanged = result else { return XCTFail("Expected 304 unchanged") }
    }

    @MainActor
    func testStreamedBytesAndValidatorsAreReturnedForValidatedFile() async throws {
        let body = Data("%PDF-1.7 fixture".utf8)
        FixtureProtocol.handler = { _ in (200, ["Content-Type": "application/pdf", "ETag": "v2", "Content-Length": "\(body.count)"], body) }
        let api = client(); defer { api.cancel() }
        let result = try await api.fetch(path: "/file", name: "notes.pdf", previous: nil)
        guard case .file(let url, let etag, _) = result else { return XCTFail("Expected file") }
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertEqual(try Data(contentsOf: url), body)
        XCTAssertEqual(etag, "v2")
    }

    @MainActor
    func testMislabelledHTMLIsRejectedAndRequiresReconnect() async throws {
        FixtureProtocol.handler = { _ in (200, ["Content-Type": "application/pdf"], Data("  <!DOCTYPE html><html>FAKE_SECRET</html>".utf8)) }
        let api = client(); defer { api.cancel() }
        do { _ = try await api.fetch(path: "/file", name: "notes.pdf", previous: nil); XCTFail("Accepted HTML") }
        catch {
            XCTAssertTrue((error as? SyncFailure)?.authRequired == true)
            XCTAssertFalse(SyncLogic.safeError(error).contains("FAKE_SECRET"))
        }
    }

    @MainActor
    func testSizeAndMIMEPolicySkipBeforeSaving() async throws {
        let api = client(); defer { api.cancel() }
        for headers in [["Content-Type": "application/pdf", "Content-Length": "500000001"], ["Content-Type": "video/mp4"]] {
            FixtureProtocol.handler = { _ in (200, headers, Data()) }
            let result = try await api.fetch(path: "/file", name: "unknown.pdf", previous: nil)
            guard case .skipped = result else { return XCTFail("Expected policy skip") }
        }
    }

    @MainActor
    func testAccessDeniedIsDistinctFromSessionExpiry() async throws {
        let api = client(); defer { api.cancel() }
        for code in [401,403] {
            FixtureProtocol.handler = { _ in (code, ["Content-Type": "application/json"], Data("{\"secret\":\"FAKE_SECRET\"}".utf8)) }
            do { _ = try await api.fetch(path: "/file", name: "notes.pdf", previous: nil); XCTFail("Expected failure") }
            catch {
                XCTAssertEqual((error as? SyncFailure)?.authRequired, code == 401)
                XCTAssertFalse(SyncLogic.safeError(error).contains("FAKE_SECRET"))
            }
        }
    }
}
