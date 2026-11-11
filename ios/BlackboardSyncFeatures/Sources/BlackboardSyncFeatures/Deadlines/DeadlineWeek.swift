import Foundation

/// The Calendar page as a week (board pick H2 "This week"): a Monday-to-Sunday strip of the
/// current week, then every due date grouped as Today, Later this week, Next week, Later and
/// Past due. Built from `DeadlinePage` with a fresh "now", so a time that passes while the page
/// stays open moves to Past due without a request.
public struct DeadlineWeek: Hashable, Sendable {
    /// Seven days, Monday first.
    public let days: [WeekDay]
    public let sections: [DeadlineSection]
    /// Course id -> index into `AppColor.courses`, by course name so a course keeps its colour.
    public let courseColors: [String: Int]
    /// "November 9 – 15" / "9 – 15 Kasım"
    public let range: String
    /// The first due date after this week, for the empty week's "next due date" line.
    public let nextAfterWeek: WeekRow?
    /// Due dates in this calendar week, passed ones included.
    public var weekCount: Int { days.reduce(0) { $0 + $1.count } }
    /// No due dates at all, past or upcoming.
    public var isEmpty: Bool { sections.isEmpty }

    public func colorIndex(_ courseID: String) -> Int { courseColors[courseID] ?? 0 }
}

public struct WeekDay: Identifiable, Hashable, Sendable {
    public let day: LocalDay
    /// "MON" / "PZT"
    public let label: String
    public let isToday: Bool
    /// Before today.
    public let isPast: Bool
    public let count: Int
    /// Distinct courses due that day in due order, at most three (the strip's dots).
    public let courseIDs: [String]
    /// The day's earliest due date, which a tap on the day scrolls to.
    public let firstRowID: DeadlineRow.ID?
    /// "Friday, November 13, 2 deadlines" for VoiceOver.
    public let accessibilityLabel: String

    public var id: LocalDay { day }
}

public struct DeadlineSection: Identifiable, Hashable, Sendable {
    public enum Kind: String, Sendable, CaseIterable {
        case today, laterThisWeek, nextWeek, later, pastDue
    }
    public let kind: Kind
    public let title: String
    public let rows: [WeekRow]

    public var id: Kind { kind }
}

/// A due date as a week row: the date tile, the due time and how close it is.
public struct WeekRow: Identifiable, Hashable, Sendable {
    public let row: DeadlineRow
    /// "13"
    public let dayNumber: String
    /// "NOV" / "KAS"
    public let month: String
    /// "23:59 · in 5 hours", "Tomorrow 09:00", "Fri 23:59"
    public let when: String
    /// Due today and not passed: drawn in the warning colour.
    public let hot: Bool
    public let past: Bool
    public let isToday: Bool

    public var id: DeadlineRow.ID { row.id }
}

extension DeadlineCalendar {
    public static func week(_ page: DeadlinePage, now: Date, timeZone: TimeZone,
                            strings: FeatureStrings) -> DeadlineWeek {
        let today = LocalTime(now, timeZone).day
        let monday = today.weekStart
        let sunday = monday.adding(6)
        let nextSunday = monday.adding(13)
        let rows = page.days.flatMap(\.rows)

        var names: [String: String] = [:]
        for row in rows { names[row.deadline.courseID] = row.course }
        let ordered = names.keys.sorted { (names[$0]!, $0) < (names[$1]!, $1) }
        let colors = Dictionary(uniqueKeysWithValues: ordered.enumerated().map { ($1, $0) })

        func weekRow(_ row: DeadlineRow) -> WeekRow {
            let past = row.deadline.due < now
            let when: String
            if row.day == today && !past {
                when = "\(row.time) · \(strings.inTime(row.deadline.due.timeIntervalSince(now)))"
            } else if row.day == today {
                when = "\(strings.tr("Today")) \(row.time)"
            } else if row.day == today.next {
                when = "\(strings.tr("Tomorrow")) \(row.time)"
            } else {
                when = "\(DisplayFormat.weekdayShort(row.day, language: strings.language)) \(row.time)"
            }
            return WeekRow(row: row, dayNumber: String(row.day.day),
                           month: strings.upper(DisplayFormat.monthShort(row.day, language: strings.language)),
                           when: when, hot: row.day == today && !past, past: past, isToday: row.day == today)
        }

        var buckets: [DeadlineSection.Kind: [DeadlineRow]] = [:]
        for row in rows {
            let kind: DeadlineSection.Kind
            if row.deadline.due < now { kind = .pastDue }
            else if row.day == today { kind = .today }
            else if row.day <= sunday { kind = .laterThisWeek }
            else if row.day <= nextSunday { kind = .nextWeek }
            else { kind = .later }
            buckets[kind, default: []].append(row)
        }
        let sections = DeadlineSection.Kind.allCases.compactMap { kind -> DeadlineSection? in
            guard var items = buckets[kind], !items.isEmpty else { return nil }
            items = sortRows(items)
            if kind == .pastDue { items.reverse() }
            return DeadlineSection(kind: kind, title: strings.sectionTitle(kind), rows: items.map(weekRow))
        }

        let days = (0..<7).map { offset -> WeekDay in
            let day = monday.adding(offset)
            let due = sortRows(rows.filter { $0.day == day })
            var courses: [String] = []
            for row in due where !courses.contains(row.deadline.courseID) { courses.append(row.deadline.courseID) }
            let name = strings.weekday(day.weekday)
            let date = strings.monthDay(month: day.month, day: day.day)
            let count = due.isEmpty ? strings.tr("No deadlines")
                : DisplayFormat.count(due.count, one: "{n} deadline", other: "{n} deadlines", translate: strings.tr)
            let label = (day == today ? "\(strings.tr("Today")), " : "") + "\(name), \(date), \(count)"
            return WeekDay(day: day, label: strings.upper(DisplayFormat.weekdayShort(day, language: strings.language)),
                           isToday: day == today, isPast: day < today, count: due.count,
                           courseIDs: Array(courses.prefix(3)), firstRowID: due.first?.id,
                           accessibilityLabel: label)
        }

        let later = sortRows(rows.filter { $0.day > sunday })
        return DeadlineWeek(days: days, sections: sections, courseColors: colors,
                            range: strings.dayRange(monday, sunday),
                            nextAfterWeek: later.first.map(weekRow))
    }
}
