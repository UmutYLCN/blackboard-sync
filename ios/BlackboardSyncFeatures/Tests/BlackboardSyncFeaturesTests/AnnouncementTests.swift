import XCTest
@testable import BlackboardSyncFeatures

/// The desktop's `tests/test_announcements.py` and `test_announcement_files.py` behaviour,
/// read live through the shell's `BlackboardHTTP` instead of from the sync state.
final class AnnouncementTests: XCTestCase {
    let publicPath = "/learn/api/public/v1/courses/_13004_1/announcements?limit=100"
    let secondPage = "/learn/api/public/v1/courses/_13004_1/announcements?offset=100&limit=100"
    let privatePath = "/learn/api/v1/courses/_13004_1/announcements?limit=100"

    func pagedFake() throws -> FakeBlackboardHTTP {
        let fake = FakeBlackboardHTTP()
        fake.set(publicPath, .json(try fixture("announcements-public-page1")))
        fake.set(secondPage, .json(try fixture("announcements-public-page2")))
        return fake
    }

    func testPagesAreFollowedDraftsSkippedAndNewestComesFirst() async throws {
        let fake = try pagedFake()
        let items = try await AnnouncementService(http: fake, baseURL: base).announcements(for: cse)
        XCTAssertEqual(fake.calls, [publicPath, secondPage])
        XCTAssertEqual(Announcement.newestFirst(items).map(\.title), ["Later", "Sınav & ders", "Welcome to CSE303", "Undated"])
    }

    func testMetadataMatchesTheDesktop() async throws {
        let items = try await AnnouncementService(http: try pagedFake(), baseURL: base).announcements(for: cse)
        let exam = try XCTUnwrap(items.first { $0.title == "Sınav & ders" })
        XCTAssertEqual(exam.id, "announcement:_13004_1:_n3_1")
        // The availability start wins over created; its offset is honoured.
        XCTAssertEqual(exam.date, utc("2026-10-01T06:00:00Z"))
        XCTAssertEqual(exam.dateText(in: istanbul, strings: english), "01.10.2026 09:00")
        XCTAssertEqual(exam.detail(in: istanbul, strings: english), "CSE303 Algorithm Analysis · 01.10.2026 09:00")
        XCTAssertEqual(exam.preview, "Rooms are attached. exam-rooms.pdf Recording: lecture.mp4")
        XCTAssertEqual(exam.body, "Rooms are attached.\n\nRecording: [lecture.mp4](/bbcswebdav/xid-912_1)")
        XCTAssertEqual(exam.files, [AnnouncementFile(id: "911_1", name: "exam-rooms.pdf",
                                                     url: URL(string: "https://blackboard.example.edu/bbcswebdav/xid-911_1"),
                                                     isMedia: false)])
        XCTAssertEqual(exam.media.map(\.name), ["lecture.mp4"])
        XCTAssertEqual(exam.blackboardURL?.absoluteString,
                       "https://blackboard.example.edu/ultra/courses/_13004_1/announcements")
        // The signed token in the body never reaches a link.
        XCTAssertFalse((exam.files + exam.media).contains { $0.url?.absoluteString.contains("token") ?? false })

        let later = try XCTUnwrap(items.first { $0.title == "Later" })
        XCTAssertEqual(later.preview, "Exam rooms & times. Be early.")
        let undated = try XCTUnwrap(items.first { $0.title == "Undated" })
        XCTAssertNil(undated.date)
        XCTAssertEqual(undated.dateText(in: istanbul, strings: english), "No date given")
        XCTAssertEqual(undated.dateText(in: istanbul, strings: turkish), "Tarih belirtilmemiş")
        XCTAssertEqual(items.first { $0.title == "Welcome to CSE303" }?.body, "Welcome!")
    }

    func testLongPreviewIsShortenedAndTitleDefaults() throws {
        let body = "<p>" + String(repeating: "ş", count: 500) + "</p>"
        let value = try json(#"{"id": "x", "body": "\#(body)"}"#)
        let item = try XCTUnwrap(Announcement(json: value, course: cse, baseURL: base, strings: turkish))
        XCTAssertEqual(item.preview, String(repeating: "ş", count: 239) + "…")
        XCTAssertEqual(item.title, "Duyuru")
        XCTAssertNil(Announcement(json: try json(#"{"title": "No id"}"#), course: cse, baseURL: base, strings: english))
    }

    func testPrivateEndpointIsTriedWhenThePublicOneFails() async throws {
        let fake = FakeBlackboardHTTP()
        fake.set(publicPath, .failure(.status(500)))
        fake.set(privatePath, .json(try fixture("announcements-private")))
        let items = try await AnnouncementService(http: fake, baseURL: base).announcements(for: cse)
        XCTAssertEqual(fake.calls, [publicPath, privatePath])
        XCTAssertEqual(items.map(\.title), ["From the private endpoint"])
        // A naive timestamp is read as UTC, as `announcements._date` does.
        XCTAssertEqual(items[0].date, utc("2026-10-02T10:00:00Z"))
        XCTAssertEqual(items[0].body, "plain & simple")
    }

    func testAFailedSecondPageFallsBackInsteadOfReturningHalf() async throws {
        let fake = FakeBlackboardHTTP()
        fake.set(publicPath, .json(try fixture("announcements-public-page1")))
        fake.set(secondPage, .failure(.status(500)))
        fake.set(privatePath, .json(try fixture("announcements-private")))
        let items = try await AnnouncementService(http: fake, baseURL: base).announcements(for: cse)
        XCTAssertEqual(items.map(\.title), ["From the private endpoint"])
    }

    func testNoCollectionIsEmptyButOtherFailuresAreErrors() async throws {
        for code in [403, 404] {
            let fake = FakeBlackboardHTTP([publicPath: .failure(.status(404)), privatePath: .failure(.status(code))])
            let items = try await AnnouncementService(http: fake, baseURL: base).announcements(for: cse)
            XCTAssertEqual(items, [])
        }
        let fake = FakeBlackboardHTTP([publicPath: .failure(.status(403)), privatePath: .failure(.status(500))])
        do {
            _ = try await AnnouncementService(http: fake, baseURL: base).announcements(for: cse)
            XCTFail("a server error must not look like an empty course")
        } catch {
            XCTAssertEqual(error as? BlackboardHTTPError, .status(500))
        }
        let html = FakeBlackboardHTTP([publicPath: .json(Data("<html>".utf8)), privatePath: .failure(.notJSON)])
        do {
            _ = try await AnnouncementService(http: html, baseURL: base).announcements(for: cse)
            XCTFail("a web page instead of data is an error")
        } catch {
            XCTAssertEqual(error as? BlackboardHTTPError, .notJSON)
        }
    }

    func testExpiredSessionIsNotRetriedOrSwallowed() async throws {
        let fake = FakeBlackboardHTTP([publicPath: .failure(.loginRequired)])
        do {
            _ = try await AnnouncementService(http: fake, baseURL: base).announcements(for: cse)
            XCTFail("expected loginRequired")
        } catch {
            XCTAssertEqual(error as? BlackboardHTTPError, .loginRequired)
        }
        XCTAssertEqual(fake.calls, [publicPath])
    }

    func testPagingRefusesLinksOffTheTenantAndLoops() async throws {
        let away = FakeBlackboardHTTP()
        away.set(publicPath, json: #"{"results": [], "paging": {"nextPage": "https://evil.example/x"}}"#)
        away.set(privatePath, json: #"{"results": [], "paging": {"nextPage": "//evil.example/x"}}"#)
        do {
            _ = try await AnnouncementService(http: away, baseURL: base).announcements(for: cse)
            XCTFail("expected a paging error")
        } catch {
            XCTAssertTrue(error is PagingError)
        }
        XCTAssertEqual(away.calls, [publicPath, privatePath])

        let loop = FakeBlackboardHTTP()
        loop.set(publicPath, json: #"{"results": [{"id": "1"}], "paging": {"nextPage": "\#(publicPath)"}}"#)
        loop.set(privatePath, .failure(.status(500)))
        do {
            _ = try await AnnouncementService(http: loop, baseURL: base).announcements(for: cse)
            XCTFail("expected an error")
        } catch {
            XCTAssertEqual(loop.calls, [publicPath, privatePath])
        }
    }
}

@MainActor
final class AnnouncementsViewModelTests: XCTestCase {
    func testFailedCourseKeepsEarlierRowsAndSaysSo() async throws {
        let fake = FakeBlackboardHTTP()
        let cseAnnouncements = "/learn/api/public/v1/courses/_13004_1/announcements?limit=100"
        let mthAnnouncements = "/learn/api/public/v1/courses/_13010_1/announcements?limit=100"
        fake.set(cseAnnouncements, json: #"{"results": [{"id": "a", "title": "Old news", "created": "2026-10-01T08:00:00Z"}]}"#)
        fake.set(mthAnnouncements, json: #"{"results": [{"id": "b", "title": "Matrices", "created": "2026-10-02T08:00:00Z"}]}"#)
        let model = AnnouncementsViewModel(http: fake, courses: StaticCourseProvider([cse, mth]), baseURL: base,
                                           strings: english, timeZone: istanbul)
        XCTAssertEqual(model.phase, .idle)
        await model.loadIfNeeded()
        XCTAssertEqual(model.phase, .loaded)
        XCTAssertNil(model.message)
        XCTAssertEqual(model.announcements.map(\.title), ["Matrices", "Old news"])
        model.selection = model.announcements[1].id
        XCTAssertEqual(model.selected?.title, "Old news")

        fake.set(cseAnnouncements, .failure(.status(500)))
        fake.set("/learn/api/v1/courses/_13004_1/announcements?limit=100", .failure(.status(502)))
        await model.refresh()
        XCTAssertEqual(model.announcements.map(\.title), ["Matrices", "Old news"])
        XCTAssertEqual(model.message, english.announcementsIncomplete)
        XCTAssertEqual(model.selected?.title, "Old news")

        // A course that is no longer selected leaves the page, and so does its selection.
        let narrowed = AnnouncementsViewModel(http: fake, courses: StaticCourseProvider([mth]), baseURL: base)
        await narrowed.refresh()
        XCTAssertEqual(narrowed.announcements.map(\.title), ["Matrices"])
    }

    func testExpiredSessionTellsTheShell() async throws {
        let fake = FakeBlackboardHTTP(["/learn/api/public/v1/courses/_13004_1/announcements?limit=100": .failure(.loginRequired)])
        var told = 0
        let model = AnnouncementsViewModel(http: fake, courses: StaticCourseProvider([cse]), baseURL: base,
                                           strings: turkish, onSignInRequired: { told += 1 })
        await model.refresh()
        XCTAssertEqual(model.phase, .signInRequired)
        XCTAssertEqual(model.message, "Blackboard oturumunuzun süresi doldu.")
        XCTAssertEqual(told, 1)
    }

    func testEverythingFailingOrNothingSelected() async throws {
        let down = FakeBlackboardHTTP()
        for path in ["/learn/api/public/v1/courses/_13004_1/announcements?limit=100",
                     "/learn/api/v1/courses/_13004_1/announcements?limit=100"] {
            down.set(path, .failure(.status(503)))
        }
        let model = AnnouncementsViewModel(http: down, courses: StaticCourseProvider([cse]), baseURL: base)
        await model.refresh()
        XCTAssertEqual(model.phase, .failed)
        XCTAssertEqual(model.message, english.unreachable)

        let none = AnnouncementsViewModel(http: down, courses: StaticCourseProvider([]), baseURL: base)
        await none.refresh()
        XCTAssertEqual(none.phase, .loaded)
        XCTAssertEqual(none.message, english.noCourses)

        // A course without the announcements tool is simply empty.
        let empty = AnnouncementsViewModel(http: FakeBlackboardHTTP(), courses: StaticCourseProvider([cse]), baseURL: base)
        await empty.refresh()
        XCTAssertEqual(empty.phase, .loaded)
        XCTAssertNil(empty.message)
        XCTAssertEqual(empty.announcements, [])
    }
}
