import Foundation

/// Dates and counts in the app's chosen language rather than the device's.
public enum DisplayFormat {
    /// "Nov 11, 2026 at 10:43 AM" / "11 Kas 2026 10:43": an abbreviated date and a short time, in
    /// `language` with the device's region (so its 12/24-hour clock). `region` is for tests.
    public static func dateTime(_ date: Date, language: FeatureLanguage, timeZone: TimeZone = .current,
                                region: Locale.Region? = Locale.current.region) -> String {
        let locale = locale(language, region: region)
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = locale
        calendar.timeZone = timeZone
        let style = Date.FormatStyle(date: .abbreviated, time: .shortened, locale: locale,
                                     calendar: calendar, timeZone: timeZone)
        return date.formatted(style)
    }

    /// "NOV" / "KAS": a month's short name in capitals, for a date tile. `month` is 1 to 12.
    public static func shortMonth(_ month: Int, language: FeatureLanguage) -> String {
        let locale = Locale(identifier: language.rawValue)
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = locale
        let symbols = calendar.shortStandaloneMonthSymbols
        guard symbols.indices.contains(month - 1) else { return "" }
        return symbols[month - 1].replacingOccurrences(of: ".", with: "").uppercased(with: locale)
    }

    /// True when `day` is today in `timeZone`, as a due date's row marks it.
    public static func isToday(_ day: LocalDay, now: Date = Date(), timeZone: TimeZone) -> Bool {
        LocalTime(now, timeZone).day == day
    }

    /// `language` with `region`'s conventions; a region without data falls back to the language's own.
    static func locale(_ language: FeatureLanguage, region: Locale.Region?) -> Locale {
        var components = Locale.Components(languageCode: Locale.LanguageCode(language.rawValue))
        components.region = region
        return Locale(components: components)
    }

    /// Picks the template for `count` by the language's plural rule, then fills in `{n}`.
    /// English: one for exactly 1, other otherwise. Turkish nouns stay singular after a number, so its
    /// translations of both templates are the same. `translate` maps the English template to the
    /// chosen language.
    public static func count(_ count: Int, one: String, other: String,
                             translate: (String) -> String = { $0 }) -> String {
        translate(count == 1 ? one : other).replacingOccurrences(of: "{n}", with: String(count))
    }
}
