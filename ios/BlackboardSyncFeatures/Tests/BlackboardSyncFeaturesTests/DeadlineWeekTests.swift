import XCTest
@testable import BlackboardSyncFeatures

/// The Calendar page's week view (board pick H2): the strip, the groups and the row texts.
final class DeadlineWeekTests: XCTestCase {
    /// Tuesday, October 13, 2026, 15:00 in Istanbul; the week runs Monday 12 to Sunday 18.
    let now = utc("2026-10-13T12:00:00Z")

    func item(_ id: String, _ due: String, course: FeatureCourse = cse) -> Deadline {
        Deadline(columnID: id, courseID: course.id, course: course.name, title: id, due: utc(due),
                 contentID: nil, url: nil, points: nil)
    }

    func week(_ items: [Deadline], strings: FeatureStrings = english, at now: Date? = nil,
              zone: TimeZone = istanbul) -> DeadlineWeek {
        let now = now ?? self.now
        var courses: [String: DeadlineCourse] = [:]
        for item in items {
            courses[item.courseID, default: DeadlineCourse(name: item.course, items: [], unavailable: false)].items.append(item)
        }
        let page = DeadlineCalendar.page(courses, now: now, timeZone: zone, strings: strings)
        return DeadlineCalendar.week(page, now: now, timeZone: zone, strings: strings)
    }

    var sample: [Deadline] {
        [item("soon", "2026-10-13T17:00:00Z"),            // today 20:00, in 5 hours
         item("passed", "2026-10-13T06:00:00Z"),          // today 09:00, already passed
         item("tomorrow", "2026-10-14T06:00:00Z", course: mth),
         item("friday", "2026-10-16T20:59:00Z"),          // Friday 23:59
         item("monday", "2026-10-19T06:00:00Z", course: mth),
         item("later", "2026-10-30T14:00:00Z"),
         item("last week", "2026-10-08T09:00:00Z")]
    }

    func testStripIsMondayToSundayWithTodayMarked() {
        let result = week(sample)
        XCTAssertEqual(result.days.map(\.day.day), [12, 13, 14, 15, 16, 17, 18])
        XCTAssertEqual(result.days.map(\.label), ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
        XCTAssertEqual(result.days.filter(\.isToday).map(\.day.day), [13])
        XCTAssertEqual(result.days.filter(\.isPast).map(\.day.day), [12])
        XCTAssertEqual(result.days.map(\.count), [0, 2, 1, 0, 1, 0, 0])
        XCTAssertEqual(result.weekCount, 4)
        XCTAssertEqual(result.range, "October 12 – 18")
        XCTAssertNil(result.days[0].firstRowID)
        XCTAssertEqual(result.days[1].firstRowID, "_13004_1:passed")
        XCTAssertEqual(result.days[1].accessibilityLabel, "Today, Tuesday, October 13, 2 deadlines")
        XCTAssertEqual(result.days[4].accessibilityLabel, "Friday, October 16, 1 deadline")
        XCTAssertEqual(result.days[0].accessibilityLabel, "Monday, October 12, No deadlines")
    }

    func testGroupsUpcomingByWeekAndPastDueNewestFirst() {
        let result = week(sample)
        XCTAssertEqual(result.sections.map(\.kind), [.today, .laterThisWeek, .nextWeek, .later, .pastDue])
        XCTAssertEqual(result.sections.map(\.title), ["Today", "Later this week", "Next week", "Later", "Past due"])
        XCTAssertEqual(result.sections.map { $0.rows.map(\.row.title) },
                       [["soon"], ["tomorrow", "friday"], ["monday"], ["later"], ["passed", "last week"]])
    }

    func testRowTexts() {
        let rows = week(sample).sections.flatMap(\.rows)
        XCTAssertEqual(rows.map(\.when), ["20:00 · in 5 hours", "Tomorrow 09:00", "Fri 23:59", "Mon 09:00",
                                          "Fri 17:00", "Today 09:00", "Thu 12:00"])
        XCTAssertEqual(rows.map(\.hot), [true, false, false, false, false, false, false])
        XCTAssertEqual(rows.map(\.past), [false, false, false, false, false, true, true])
        XCTAssertEqual(rows.map(\.dayNumber), ["13", "14", "16", "19", "30", "13", "8"])
        XCTAssertEqual(Set(rows.map(\.month)), ["OCT"])
        XCTAssertEqual(rows.filter(\.isToday).map(\.row.title), ["soon", "passed"])
    }

    func testTurkish() {
        let result = week(sample, strings: turkish)
        XCTAssertEqual(result.days.map(\.label), ["PZT", "SAL", "ÇAR", "PER", "CUM", "CMT", "PAZ"])
        XCTAssertEqual(result.range, "12 – 18 Ekim")
        XCTAssertEqual(result.sections.map(\.title),
                       ["Bugün", "Haftanın geri kalanı", "Gelecek hafta", "Daha sonra", "Tarihi geçenler"])
        let rows = result.sections.flatMap(\.rows)
        XCTAssertEqual(rows.map(\.when), ["20:00 · 5 saat sonra", "Yarın 09:00", "Cum 23:59", "Pzt 09:00",
                                          "Cum 17:00", "Bugün 09:00", "Per 12:00"])
        XCTAssertEqual(Set(rows.map(\.month)), ["EKİ"])
        XCTAssertEqual(result.days[1].accessibilityLabel, "Bugün, Salı, 13 Ekim, 2 teslim tarihi")
        XCTAssertEqual(result.days[0].accessibilityLabel, "Pazartesi, 12 Ekim, Teslim tarihi yok")
        XCTAssertEqual(turkish.upper("Tarihi geçenler"), "TARİHİ GEÇENLER")
    }

    func testRelativeTimePlurals() {
        XCTAssertEqual(english.inTime(30), "in 1 minute")
        XCTAssertEqual(english.inTime(59 * 60), "in 59 minutes")
        XCTAssertEqual(english.inTime(60 * 60), "in 1 hour")
        XCTAssertEqual(english.inTime(5 * 3600 + 59 * 60), "in 5 hours")
        XCTAssertEqual(turkish.inTime(60), "1 dakika sonra")
        XCTAssertEqual(turkish.inTime(2 * 3600), "2 saat sonra")
    }

    func testRangeAcrossMonths() {
        let start = LocalTime(utc("2026-10-26T12:00:00Z"), istanbul).day
        XCTAssertEqual(english.dayRange(start, start.adding(6)), "October 26 – November 1")
        XCTAssertEqual(turkish.dayRange(start, start.adding(6)), "26 Ekim – 1 Kasım")
    }

    func testEmptyWeekPointsAtTheNextDueDate() {
        let result = week([item("later", "2026-10-30T14:00:00Z"), item("old", "2026-10-01T09:00:00Z")])
        XCTAssertEqual(result.weekCount, 0)
        XCTAssertTrue(result.days.allSatisfy { $0.courseIDs.isEmpty })
        XCTAssertEqual(result.nextAfterWeek?.row.title, "later")
        XCTAssertEqual(english.nextDueDate("later, Fri 17:00"), "Next due date: later, Fri 17:00")
        XCTAssertEqual(turkish.nextDueDate("x"), "Sonraki teslim: x")
        let nothing = week([])
        XCTAssertTrue(nothing.isEmpty)
        XCTAssertNil(nothing.nextAfterWeek)
        XCTAssertEqual(nothing.days.count, 7)
    }

    func testCourseColoursFollowCourseNamesAndDotsAreDistinct() {
        let result = week(sample)
        XCTAssertEqual(result.courseColors, [cse.id: 0, mth.id: 1])
        XCTAssertEqual(result.days[1].courseIDs, [cse.id])
        let busy = week([item("a", "2026-10-14T06:00:00Z"), item("b", "2026-10-14T07:00:00Z", course: mth),
                         item("c", "2026-10-14T08:00:00Z")]
                        + (0..<3).map { item("x\($0)", "2026-10-14T09:00:00Z",
                                             course: FeatureCourse(id: "_z\($0)", name: "Z\($0)")) })
        XCTAssertEqual(busy.days[2].courseIDs, [cse.id, mth.id, "_z0"])
        XCTAssertEqual(busy.days[2].count, 6)
        XCTAssertEqual(AppColor.courses.count, 7)
        XCTAssertEqual(AppColor.course(7), AppColor.course(0))
    }

    func testTimePassingMovesARowToPastDueWithoutARefresh() {
        var courses: [String: DeadlineCourse] = [:]
        courses[cse.id] = DeadlineCourse(name: cse.name, items: [item("soon", "2026-10-13T12:30:00Z")], unavailable: false)
        let page = DeadlineCalendar.page(courses, now: now, timeZone: istanbul, strings: english)
        XCTAssertEqual(DeadlineCalendar.week(page, now: now, timeZone: istanbul, strings: english).sections.map(\.kind), [.today])
        XCTAssertEqual(DeadlineCalendar.week(page, now: now, timeZone: istanbul, strings: english).sections[0].rows[0].when,
                       "15:30 · in 30 minutes")
        let later = DeadlineCalendar.week(page, now: now + 3600, timeZone: istanbul, strings: english)
        XCTAssertEqual(later.sections.map(\.kind), [.pastDue])
        XCTAssertEqual(later.sections[0].rows[0].when, "Today 15:30")
    }

    func testWeekStartsOnMondayInEveryZoneAndOnSunday() {
        // Sunday 18th: still the week of Monday 12th.
        let sunday = week([], at: utc("2026-10-18T20:00:00Z"))
        XCTAssertEqual(sunday.days.first?.day.day, 12)
        XCTAssertEqual(sunday.days.last?.isToday, true)
        // Midnight Monday in Istanbul is still Sunday in UTC.
        let monday = week([], at: utc("2026-10-18T21:30:00Z"))
        XCTAssertEqual(monday.days.first?.day.day, 19)
        XCTAssertEqual(monday.days.first?.isToday, true)
    }

    func testShortNamesFollowTheChosenLanguage() {
        let day = LocalTime(utc("2026-11-11T12:00:00Z"), istanbul).day
        XCTAssertEqual(DisplayFormat.weekdayShort(day, language: .english), "Wed")
        XCTAssertEqual(DisplayFormat.weekdayShort(day, language: .turkish), "Çar")
        XCTAssertEqual(DisplayFormat.monthShort(day, language: .english), "Nov")
        XCTAssertEqual(DisplayFormat.monthShort(day, language: .turkish), "Kas")
        XCTAssertEqual(day.weekStart.day, 9)
        XCTAssertEqual(day.adding(-11).month, 10)
    }
}
