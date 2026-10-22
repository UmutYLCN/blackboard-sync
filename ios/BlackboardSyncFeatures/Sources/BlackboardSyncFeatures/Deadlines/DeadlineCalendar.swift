import Foundation

/// A due date as the calendar shows it, in local time.
public struct DeadlineRow: Identifiable, Hashable, Sendable {
    public let deadline: Deadline
    public let day: LocalDay
    /// "09:00"
    public let time: String

    public var id: String { deadline.id }
    public var title: String { deadline.title }
    public var course: String { deadline.course }
}

public struct DeadlineDay: Identifiable, Hashable, Sendable {
    public let day: LocalDay
    /// "Tomorrow · October 14, 2026"
    public let title: String
    public let past: Bool
    public let rows: [DeadlineRow]

    public var id: String { "\(past ? "past" : "upcoming")-\(day.year)-\(day.month)-\(day.day)" }
}

public struct DeadlinePage: Hashable, Sendable {
    public var days: [DeadlineDay] = []
    /// Shown above the days: not loaded yet, or some courses could not be updated.
    public var message: String = ""
}

/// The desktop's `deadlines.calendar_page` and the Home helpers next to it.
public enum DeadlineCalendar {
    /// Upcoming first, ascending by instant; elapsed dates in a separate section, newest day
    /// first. A day that has both splits in two: what is still ahead and what has passed.
    static func page(_ courses: [String: DeadlineCourse]?, now: Date, timeZone: TimeZone,
                     strings: FeatureStrings) -> DeadlinePage {
        guard let courses else { return DeadlinePage(message: strings.calendarNotLoaded) }
        let today = LocalTime(now, timeZone).day
        var grouped: [Bool: [LocalDay: [DeadlineRow]]] = [:]
        for course in courses.values {
            for item in course.items {
                let local = LocalTime(item.due, timeZone)
                grouped[item.due < now, default: [:]][local.day, default: []]
                    .append(DeadlineRow(deadline: item, day: local.day, time: local.time))
            }
        }
        var days: [DeadlineDay] = []
        for past in [false, true] {
            let section = grouped[past] ?? [:]
            for day in section.keys.sorted(by: past ? (>) : (<)) {
                days.append(DeadlineDay(day: day, title: dayTitle(day, today: today, strings: strings), past: past,
                                        rows: sortRows(section[day]!)))
            }
        }
        let message = courses.values.contains(where: \.unavailable) ? strings.calendarIncomplete : ""
        return DeadlinePage(days: days, message: message)
    }

    static func sortRows(_ rows: [DeadlineRow]) -> [DeadlineRow] {
        rows.sorted { a, b in
            if a.deadline.due != b.deadline.due { return a.deadline.due < b.deadline.due }
            if a.course != b.course { return a.course < b.course }
            return a.title < b.title
        }
    }

    /// "Today · October 13, 2026", "Tomorrow · …", else the weekday.
    public static func dayTitle(_ day: LocalDay, today: LocalDay, strings: FeatureStrings) -> String {
        let prefix = day == today ? strings.tr("Today")
            : day == today.next ? strings.tr("Tomorrow") : strings.weekday(day.weekday)
        return "\(prefix) · " + strings.fullDate(month: day.month, day: day.day, year: day.year)
    }

    /// The next `limit` due dates that have not passed, soonest first (Home's small calendar).
    public static func upcomingRows(_ page: DeadlinePage, limit: Int) -> [DeadlineRow] {
        Array(sortRows(page.days.filter { !$0.past }.flatMap(\.rows)).prefix(limit))
    }

    /// "This week" is the next 7 days counted from now, not the calendar week.
    public static let week: TimeInterval = 7 * 24 * 3600

    /// (due today, due within the next 7 days) among the dates that have not passed yet.
    public static func countDue(_ page: DeadlinePage, now: Date, timeZone: TimeZone) -> (today: Int, week: Int) {
        let today = LocalTime(now, timeZone).day
        var counts = (today: 0, week: 0)
        for row in page.days.flatMap(\.rows) where now <= row.deadline.due && row.deadline.due < now + week {
            counts.week += 1
            if row.day == today { counts.today += 1 }
        }
        return counts
    }

    /// "1 deadline today · 3 this week"; empty while nothing was loaded yet.
    public static func subtitle(_ page: DeadlinePage, now: Date, timeZone: TimeZone, strings: FeatureStrings) -> String {
        if page.message == strings.calendarNotLoaded { return "" }
        let counts = countDue(page, now: now, timeZone: timeZone)
        return strings.deadlineCount(today: counts.today, week: counts.week)
    }

    /// "today 14:30", "tomorrow 09:00" or "October 15 09:00", for a small row.
    public static func whenText(_ row: DeadlineRow, today: LocalDay, strings: FeatureStrings) -> String {
        if row.day == today { return strings.today(row.time) }
        if row.day == today.next { return strings.tomorrow(row.time) }
        return strings.monthDay(month: row.day.month, day: row.day.day, time: row.time)
    }
}
