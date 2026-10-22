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
    var next: LocalDay {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let date = calendar.date(from: DateComponents(year: year, month: month, day: day + 1))!
        return LocalTime(date, calendar.timeZone).day
    }
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
