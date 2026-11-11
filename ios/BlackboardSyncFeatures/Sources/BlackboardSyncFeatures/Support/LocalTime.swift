import Foundation

/// A calendar day in some time zone, comparable like Python's `date`.
public struct LocalDay: Hashable, Comparable, Sendable {
    public let year: Int
    public let month: Int
    public let day: Int
    /// Monday = 0 … Sunday = 6, as `date.weekday()`.
    public let weekday: Int

    public static func < (a: LocalDay, b: LocalDay) -> Bool {
        (a.year, a.month, a.day) < (b.year, b.month, b.day)
    }

    /// The day after this one.
    var next: LocalDay { adding(1) }

    /// The day `days` after (or, when negative, before) this one.
    func adding(_ days: Int) -> LocalDay {
        LocalTime(Self.utcCalendar.date(from: DateComponents(year: year, month: month, day: day + days, hour: 12))!,
                  Self.utcCalendar.timeZone).day
    }

    /// Monday of this day's week (weeks start on Monday, as the desktop's `date.weekday()`).
    var weekStart: LocalDay { adding(-weekday) }

    /// Noon of this day in UTC, for formatting the day's names without a time-zone shift.
    var noonUTC: Date {
        Self.utcCalendar.date(from: DateComponents(year: year, month: month, day: day, hour: 12))!
    }

    static let utcCalendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }()
}

/// An instant as a wall clock in one zone: each instant converted on its own, so daylight
/// saving changes fall where they really are.
struct LocalTime: Hashable, Sendable {
    let day: LocalDay
    /// "09:00"
    let time: String

    init(_ date: Date, _ timeZone: TimeZone) {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let parts = calendar.dateComponents([.year, .month, .day, .hour, .minute, .weekday], from: date)
        day = LocalDay(year: parts.year!, month: parts.month!, day: parts.day!,
                       weekday: (parts.weekday! + 5) % 7)
        time = String(format: "%02d:%02d", parts.hour!, parts.minute!)
    }
}
