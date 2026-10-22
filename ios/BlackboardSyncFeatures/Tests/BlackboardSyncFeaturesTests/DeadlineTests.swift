import XCTest
@testable import BlackboardSyncFeatures

/// The desktop's `tests/test_deadlines.py` and `test_home_header.py` behaviour.
final class DeadlineTests: XCTestCase {
    let now = utc("2026-10-13T12:00:00Z")
    let firstPage = "/learn/api/public/v2/courses/_13004_1/gradebook/columns?limit=200"
    let secondPage = "/learn/api/public/v2/courses/_13004_1/gradebook/columns?offset=200&limit=200"

    func column(_ id: String = "_grade_1", _ due: String = "2026-10-13T22:30:00Z", extra: String = "") throws -> JSONValue {
        try json(#"{"id": "\#(id)", "name": "Ödev 1", "grading": {"due": "\#(due)"}, "contentId": "_c4_1"\#(extra)}"#)
    }

    func deadline(_ id: String, _ due: String) throws -> Deadline {
        try XCTUnwrap(Deadline(column: try column(id, due), course: cse, baseURL: base, strings: english))
    }

    func page(_ items: [Deadline], _ zone: TimeZone, unavailable: Bool = false,
              strings: FeatureStrings = english) -> DeadlinePage {
        DeadlineCalendar.page([cse.id: DeadlineCourse(name: cse.name, items: items, unavailable: unavailable)],
                              now: now, timeZone: zone, strings: strings)
    }

    func testInvalidOrAmbiguousTimestampsAreNotGuessed() throws {
        for value in ["", "not a date", "2026-10-13", "2026-10-13T19:00:00", "2026-13-01T00:00:00Z",
                      "2026-02-30T10:00:00Z", "2026-10-13T25:00:00Z"] {
            XCTAssertNil(Deadline.parseDue(.string(value)), value)
            XCTAssertNil(Deadline(column: try column("x", value), course: cse, baseURL: base, strings: english), value)
        }
        XCTAssertNil(Deadline.parseDue(.number(123)))
        XCTAssertNil(Deadline.parseDue(nil))
    }

    func testTimestampShapesBlackboardSends() {
        XCTAssertEqual(Deadline.parseDue(.string("2026-10-14T01:30:00+03:00")), utc("2026-10-13T22:30:00Z"))
        XCTAssertEqual(Deadline.parseDue(.string("2026-10-13T22:30:00.000Z")), utc("2026-10-13T22:30:00Z"))
        XCTAssertEqual(Deadline.parseDue(.string("2026-10-13T17:30:00-0500")), utc("2026-10-13T22:30:00Z"))
        XCTAssertEqual(Deadline.parseDue(.string("2026-10-13T22:30:00.250Z"))?.timeIntervalSince(utc("2026-10-13T22:30:00Z")),
                       0.25)
    }

    func testOnlyExplicitVisibleGradeColumnDueDatesAreUsed() throws {
        let result = try XCTUnwrap(Deadline(column: try column(due: "2026-10-14T01:30:00+03:00", displayName: "Proje"),
                                            course: cse, baseURL: base, strings: english))
        XCTAssertEqual(result.due, utc("2026-10-13T22:30:00Z"))
        XCTAssertEqual(result.title, "Proje")
        XCTAssertEqual(result.id, "_13004_1:_grade_1")
        let query = URLComponents(url: try XCTUnwrap(result.url), resolvingAgainstBaseURL: false)?.queryItems
        XCTAssertEqual(query, [URLQueryItem(name: "redirectType", value: "nautilus"),
                               URLQueryItem(name: "courseId", value: "_13004_1"),
                               URLQueryItem(name: "contentId", value: "_c4_1")])
        XCTAssertNil(Deadline(column: try column(extra: #", "availability": {"available": "No"}"#),
                              course: cse, baseURL: base, strings: english))
        XCTAssertNil(Deadline(column: try json(#"{"id": "x", "dueDate": "2026-10-13T22:30:00Z", "availability": {"end": "2026-10-13T22:30:00Z"}}"#),
                              course: cse, baseURL: base, strings: english))
        let bare = try json(#"{"id": "_grade_1", "grading": {"due": "2026-10-13T22:30:00Z"}}"#)
        let linked = try XCTUnwrap(Deadline(column: bare, course: cse, baseURL: base, strings: turkish,
                                            contentIDs: ["_grade_1": "nested"]))
        XCTAssertEqual(linked.contentID, "nested")
        XCTAssertEqual(linked.title, "Adsız çalışma")
        let standalone = try XCTUnwrap(Deadline(column: bare, course: cse, baseURL: base, strings: english))
        XCTAssertEqual(standalone.url?.absoluteString, "https://blackboard.example.edu/ultra/courses/_13004_1/grades")
    }

    func column(due: String, displayName: String) throws -> JSONValue {
        try column("_grade_1", due, extra: #", "displayName": "\#(displayName)""#)
    }

    func testGroupsByLocalDayAndSeparatesElapsedTimesOnTheSameDay() throws {
        let items = [try deadline("tomorrow", "2026-10-13T22:30:00Z"), try deadline("past", "2026-10-13T11:59:00Z"),
                     try deadline("later", "2026-10-13T18:00:00Z"), try deadline("now", "2026-10-13T12:00:00Z"),
                     try deadline("older", "2026-10-12T10:00:00Z")]
        let result = page(items, istanbul)
        XCTAssertEqual(result.days.map { "\($0.day.year)-\($0.day.month)-\($0.day.day) \($0.past)" },
                       ["2026-10-13 false", "2026-10-14 false", "2026-10-13 true", "2026-10-12 true"])
        XCTAssertEqual(result.days[0].rows.map(\.time), ["15:00", "21:00"])
        XCTAssertEqual(result.days[0].title, "Today · October 13, 2026")
        XCTAssertEqual(result.days[1].title, "Tomorrow · October 14, 2026")
        XCTAssertEqual(result.days[1].rows[0].time, "01:30")
        XCTAssertEqual(result.days[3].title, "Monday · October 12, 2026")
        XCTAssertEqual(result.days[0].rows[0].course, "CSE303 Algorithm Analysis")
        XCTAssertEqual(result.message, "")
        let california = page(items, TimeZone(identifier: "America/Los_Angeles")!)
        XCTAssertEqual(california.days.count, 3)  // Istanbul's tomorrow is still today in California.
        let tr = page(items, istanbul, strings: turkish)
        XCTAssertEqual(tr.days.map(\.title), ["Bugün · 13 Ekim 2026", "Yarın · 14 Ekim 2026",
                                              "Bugün · 13 Ekim 2026", "Pazartesi · 12 Ekim 2026"])
    }

    func testDaylightSavingFoldSortsByInstantNotWallClock() throws {
        let items = [try deadline("second", "2026-11-01T06:15:00Z"), try deadline("first", "2026-11-01T05:45:00Z")]
        let result = page(items, TimeZone(identifier: "America/New_York")!)
        XCTAssertEqual(result.days.count, 1)
        XCTAssertEqual(result.days[0].rows.map(\.time), ["01:45", "01:15"])
        XCTAssertEqual(result.days[0].title, "Sunday · November 1, 2026")
    }

    func testSameInstantSortsByCourseThenTitle() throws {
        let due = utc("2026-10-14T09:00:00Z")
        let rows = [Deadline(columnID: "1", courseID: "b", course: "B", title: "A", due: due, contentID: nil, url: nil, points: nil),
                    Deadline(columnID: "2", courseID: "a", course: "A", title: "Z", due: due, contentID: nil, url: nil, points: nil),
                    Deadline(columnID: "3", courseID: "a", course: "A", title: "B", due: due, contentID: nil, url: nil, points: nil)]
        let result = DeadlineCalendar.page(["x": DeadlineCourse(name: "x", items: rows, unavailable: false)],
                                           now: now, timeZone: istanbul, strings: english)
        XCTAssertEqual(result.days[0].rows.map { "\($0.course)/\($0.title)" }, ["A/B", "A/Z", "B/A"])
    }

    func testMessagesForNotLoadedEmptyAndIncomplete() {
        XCTAssertEqual(DeadlineCalendar.page(nil, now: now, timeZone: istanbul, strings: english).message,
                       "Sync to see due dates.")
        XCTAssertEqual(page([], istanbul).message, "")
        XCTAssertEqual(page([], istanbul, unavailable: true).message, english.calendarIncomplete)
        XCTAssertEqual(page([], istanbul, unavailable: true, strings: turkish).message,
                       "Bazı derslerin tarihleri güncellenemedi. Varsa önceki kayıtlar gösteriliyor.")
    }

    func testHomeHelpersCountTodayAndTheNextSevenDays() throws {
        let items = [try deadline("a", "2026-10-13T15:00:00Z"), try deadline("b", "2026-10-13T20:30:00Z"),
                     try deadline("c", "2026-10-14T09:00:00Z"), try deadline("d", "2026-10-21T09:00:00Z"),
                     try deadline("e", "2026-10-13T08:00:00Z")]
        let result = page(items, istanbul)
        XCTAssertTrue(DeadlineCalendar.countDue(result, now: now, timeZone: istanbul) == (2, 3))
        XCTAssertEqual(DeadlineCalendar.subtitle(result, now: now, timeZone: istanbul, strings: english),
                       "2 deadlines today · 3 this week")
        XCTAssertEqual(DeadlineCalendar.subtitle(result, now: now, timeZone: istanbul, strings: turkish),
                       "Bugün 2 teslim tarihi · bu hafta 3")
        XCTAssertEqual(DeadlineCalendar.subtitle(page([], istanbul), now: now, timeZone: istanbul, strings: english),
                       "No deadlines this week")
        XCTAssertEqual(DeadlineCalendar.subtitle(page([items[2]], istanbul), now: now, timeZone: istanbul, strings: english),
                       "1 deadline this week")
        XCTAssertEqual(DeadlineCalendar.subtitle(DeadlineCalendar.page(nil, now: now, timeZone: istanbul, strings: english),
                                                 now: now, timeZone: istanbul, strings: english), "")
        let upcoming = DeadlineCalendar.upcomingRows(result, limit: 4)
        XCTAssertEqual(upcoming.map(\.deadline.columnID), ["a", "b", "c", "d"])
        let today = LocalTime(now, istanbul).day
        XCTAssertEqual(upcoming.map { DeadlineCalendar.whenText($0, today: today, strings: english) },
                       ["today 18:00", "today 23:30", "tomorrow 12:00", "October 21 12:00"])
        XCTAssertEqual(upcoming.map { DeadlineCalendar.whenText($0, today: today, strings: turkish) },
                       ["bugün 18:00", "bugün 23:30", "yarın 12:00", "21 Ekim 12:00"])
    }

    func testPointsAreShownAsTheDesktopNoteWritesThem() async throws {
        let service = DeadlineService(http: try pagedFake(), baseURL: base)
        let items = try await service.deadlines(for: cse)
        XCTAssertEqual(items.map(\.columnID), ["tomorrow", "past", "later", "older"])
        XCTAssertEqual(items.map(\.pointsText), ["100", "12.5", nil, nil])  // `true` is not a number of points
        XCTAssertEqual(english.points("12.5"), "Points: 12.5")
        XCTAssertEqual(turkish.due("yarın 01:30"), "Teslim: yarın 01:30")
    }

    func pagedFake() throws -> FakeBlackboardHTTP {
        let fake = FakeBlackboardHTTP()
        fake.set(firstPage, .json(try fixture("gradebook-columns-page1")))
        fake.set(secondPage, .json(try fixture("gradebook-columns-page2")))
        return fake
    }

    func testServiceFollowsPagesAndUsesOnlyGradeColumnMetadata() async throws {
        let fake = try pagedFake()
        let items = try await DeadlineService(http: fake, baseURL: base).deadlines(for: cse)
        XCTAssertEqual(fake.calls, [firstPage, secondPage])
        XCTAssertEqual(items.first { $0.columnID == "later" }?.title, "Proje")
        XCTAssertEqual(items.first { $0.columnID == "past" }?.url?.absoluteString,
                       "https://blackboard.example.edu/ultra/courses/_13004_1/grades")
    }
}

@MainActor
final class DeadlinesViewModelTests: XCTestCase {
    let firstPage = "/learn/api/public/v2/courses/_13004_1/gradebook/columns?limit=200"
    let secondPage = "/learn/api/public/v2/courses/_13004_1/gradebook/columns?offset=200&limit=200"

    func model(_ fake: FakeBlackboardHTTP, courses: [FeatureCourse] = [cse], strings: FeatureStrings = english,
               clock: Clock = Clock(utc("2026-10-13T12:00:00Z")),
               onSignInRequired: @escaping @MainActor () -> Void = {}) -> DeadlinesViewModel {
        DeadlinesViewModel(http: fake, courses: StaticCourseProvider(courses), baseURL: base, strings: strings,
                           timeZone: istanbul, now: { clock.now }, onSignInRequired: onSignInRequired)
    }

    func testPartialPagingFailurePreservesEarlierDatesAndMarksThemOutOfDate() async throws {
        let fake = FakeBlackboardHTTP()
        fake.set(firstPage, .json(try fixture("gradebook-columns-page1")))
        fake.set(secondPage, .json(try fixture("gradebook-columns-page2")))
        let model = model(fake)
        XCTAssertEqual(model.page.message, "Sync to see due dates.")
        await model.loadIfNeeded()
        XCTAssertEqual(model.phase, .loaded)
        XCTAssertEqual(model.page.message, "")
        XCTAssertEqual(model.page.days.flatMap(\.rows).count, 4)
        XCTAssertEqual(model.subtitle, "1 deadline today · 2 this week")
        let row = try XCTUnwrap(model.page.days.first?.rows.first)
        model.selection = row.id
        XCTAssertEqual(model.dueText(for: row), "Today · October 13, 2026 21:00")
        XCTAssertEqual(model.whenText(for: row), "today 21:00")

        fake.set(secondPage, .failure(.status(500)))
        await model.refresh()
        XCTAssertEqual(model.page.days.flatMap(\.rows).count, 4)
        XCTAssertEqual(model.page.message, english.calendarIncomplete)
        XCTAssertEqual(model.selected?.id, row.id)

        fake.set(firstPage, json: #"{"results": []}"#)
        await model.refresh()
        XCTAssertEqual(model.page.days, [])
        XCTAssertEqual(model.page.message, "")
        XCTAssertNil(model.selection)
    }

    func testDeniedAccessIsDistinctFromNoDueDates() async throws {
        let model = model(FakeBlackboardHTTP([firstPage: .failure(.status(403))]))
        await model.refresh()
        XCTAssertEqual(model.page.days, [])
        XCTAssertEqual(model.page.message, english.calendarIncomplete)
    }

    func testExpiredSessionIsNotSwallowed() async throws {
        var told = false
        let model = model(FakeBlackboardHTTP([firstPage: .failure(.loginRequired)]), onSignInRequired: { told = true })
        await model.refresh()
        XCTAssertEqual(model.phase, .signInRequired)
        XCTAssertEqual(model.error, english.sessionExpired)
        XCTAssertTrue(told)
    }

    func testRebuildMovesElapsedDatesWithoutARequest() async throws {
        let fake = FakeBlackboardHTTP([firstPage: .json(Data(#"{"results": [{"id": "a", "name": "Lab", "grading": {"due": "2026-10-13T13:00:00Z"}}]}"#.utf8))])
        let clock = Clock(utc("2026-10-13T12:00:00Z"))
        let model = model(fake, strings: turkish, clock: clock)
        await model.refresh()
        XCTAssertEqual(model.page.days.map(\.past), [false])
        clock.now = utc("2026-10-13T14:00:00Z")
        model.rebuild()
        XCTAssertEqual(model.page.days.map(\.past), [true])
        XCTAssertEqual(fake.calls.count, 1)
        XCTAssertEqual(model.subtitle, "Bu hafta teslim tarihi yok")
    }
}
