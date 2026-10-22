import Foundation

/// Python's `datetime.fromisoformat(value.replace("Z", "+00:00"))` for the shapes Blackboard
/// sends: `2026-10-13T22:30:00Z`, `...00.000Z`, `...+03:00`, a naive `2026-10-13T19:00:00`
/// and a bare `2026-10-13`.
enum ISODate {
    struct Parsed: Equatable {
        /// The instant, reading a naive value as UTC.
        let date: Date
        /// False for a naive value; its offset was assumed, not given.
        let hasZone: Bool
    }

    private static let pattern = try! NSRegularExpression(pattern:
        #"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2})(?::(\d{2})(?::(\d{2})(?:[.,](\d{1,9}))?)?)?)?"# +
        #"(Z|[+-]\d{2}(?::?\d{2}(?::?\d{2})?)?)?$"#)

    static func parse(_ value: String) -> Parsed? {
        let range = NSRange(value.startIndex..., in: value)
        guard let match = pattern.firstMatch(in: value, range: range) else { return nil }
        func group(_ index: Int) -> String? {
            Range(match.range(at: index), in: value).map { String(value[$0]) }
        }
        func int(_ index: Int) -> Int { group(index).flatMap { Int($0) } ?? 0 }
        let (year, month, day) = (int(1), int(2), int(3))
        let (hour, minute, second) = (int(4), int(5), int(6))
        // A zone needs a time; "2026-10-13Z" is not ISO.
        if group(8) != nil, group(4) == nil { return nil }
        guard (1...12).contains(month), hour < 24, minute < 60, second < 60, year >= 1 else { return nil }
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let components = DateComponents(year: year, month: month, day: day, hour: hour, minute: minute, second: second)
        guard let monthStart = utc.date(from: DateComponents(year: year, month: month)),
              let days = utc.range(of: .day, in: .month, for: monthStart), days.contains(day),
              var date = utc.date(from: components) else { return nil }
        if let fraction = group(7) {
            date += Double("0." + fraction) ?? 0
        }
        guard let zone = group(8) else { return Parsed(date: date, hasZone: false) }
        if zone != "Z" {
            let sign: Double = zone.hasPrefix("-") ? -1 : 1
            let digits = zone.dropFirst().filter(\.isNumber)
            let parts = stride(from: 0, to: digits.count, by: 2).map { offset -> Int in
                let start = digits.index(digits.startIndex, offsetBy: offset)
                return Int(digits[start..<digits.index(start, offsetBy: 2)]) ?? 0
            }
            let hours = parts[0], minutes = parts.count > 1 ? parts[1] : 0, seconds = parts.count > 2 ? parts[2] : 0
            guard hours < 24, minutes < 60, seconds < 60 else { return nil }
            date -= sign * Double(hours * 3600 + minutes * 60 + seconds)
        }
        return Parsed(date: date, hasZone: true)
    }
}
