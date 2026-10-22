import Foundation

/// The app's two languages, as in the desktop's `i18n.py`: English is the text written in the
/// code, Turkish comes from the catalog below.
public enum FeatureLanguage: String, CaseIterable, Sendable {
    case english = "en"
    case turkish = "tr"

    /// A known language code, else English (`normalize_language`).
    public init(code: String?) {
        self = FeatureLanguage(rawValue: code ?? "") ?? .english
    }
}

/// Every text these pages show. Strings shared with the desktop keep its English and its
/// `locale_tr.py` Turkish word for word; the few that would be untrue on an iPad ("synced",
/// "this computer") are reworded and marked below.
public struct FeatureStrings: Sendable {
    public let language: FeatureLanguage

    public init(_ language: FeatureLanguage = .english) {
        self.language = language
    }

    /// `text` in the chosen language; English is the text itself (`tr`).
    public func tr(_ text: String) -> String {
        language == .english ? text : Self.turkish[text] ?? text
    }

    func format(_ text: String, _ values: [String: String]) -> String {
        values.reduce(tr(text)) { $0.replacingOccurrences(of: "{\($1.key)}", with: $1.value) }
    }

    // MARK: Announcements (announcements.py)
    public var announcementsTab: String { tr("Announcements") }
    public var announcementsHint: String { tr("Every announcement from your selected courses.") }  // iPad wording
    public var announcementsEmpty: String { tr("No announcements in your selected courses yet.") }  // iPad wording
    public var noDate: String { tr("No date given") }
    public var openAnnouncement: String { tr("Open announcement") }
    public var untitledAnnouncement: String { tr("Announcement") }
    public var announcementsIncomplete: String {
        tr("Some courses' announcements could not be updated. Earlier ones are shown where there are any.")
    }
    public var filesHeading: String { tr("Files in this announcement") }
    public var mediaHeading: String { tr("Video and audio files (open in Blackboard)") }
    public var selectAnnouncement: String { tr("Select an announcement") }

    // MARK: Calendar (deadlines.py)
    public var calendarTab: String { tr("Calendar") }
    public var calendarHint: String {  // iPad wording: there is no background sync and no "computer"
        tr("Due dates are updated when this page refreshes. Times are in this iPad's local time.")
    }
    public var upcoming: String { tr("Upcoming") }
    public var pastDue: String { tr("Past due") }
    public var pastDueHint: String { tr("Submissions are not checked; work you already handed in may show here too.") }
    public var calendarEmpty: String { tr("No due dates saved.") }
    public var calendarNotLoaded: String { tr("Sync to see due dates.") }
    public var calendarIncomplete: String {
        tr("Some courses' due dates could not be updated. Earlier ones are shown where there are any.")
    }
    public var untitledWork: String { tr("Untitled work") }
    public var openInBlackboard: String { tr("Open in Blackboard") }
    public var selectDeadline: String { tr("Select a due date") }
    public var upcomingDeadlines: String { tr("Upcoming deadlines") }
    public var noUpcomingDeadlines: String { tr("No upcoming deadlines.") }

    public func due(_ time: String) -> String { format("Due: {time}", ["time": time]) }
    public func points(_ points: String) -> String { format("Points: {points}", ["points": points]) }

    // MARK: Shared
    public var close: String { tr("Close") }
    public var refresh: String { tr("Refresh") }
    public var loading: String { tr("Loading…") }
    public var noCourses: String { tr("No courses selected.") }
    public var sessionExpired: String { tr("Your Blackboard session has expired.") }
    public var unreachable: String { tr("Blackboard could not be reached. Pull down to try again.") }

    // MARK: Dates
    static let months = ["January", "February", "March", "April", "May", "June", "July",
                         "August", "September", "October", "November", "December"]
    static let weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    func month(_ number: Int) -> String { tr(Self.months[number - 1]) }

    /// `weekday` counted from Monday = 0, as Python's `date.weekday()`.
    func weekday(_ mondayBased: Int) -> String { tr(Self.weekdays[mondayBased]) }

    /// "October 15" / "October 15 09:00" (Turkish: "15 Ekim 09:00"); `month_day`.
    func monthDay(month: Int, day: Int, time: String = "") -> String {
        let text = format("{month} {day}", ["month": self.month(month), "day": String(day)])
        return time.isEmpty ? text : "\(text) \(time)"
    }

    func fullDate(month: Int, day: Int, year: Int) -> String {
        format("{month} {day}, {year}", ["month": self.month(month), "day": String(day), "year": String(year)])
    }

    func today(_ time: String) -> String { format("today {time}", ["time": time]) }
    func tomorrow(_ time: String) -> String { format("tomorrow {time}", ["time": time]) }

    /// "1 deadline today · 3 this week" (`main_window_model.deadline_subtitle`).
    func deadlineCount(today: Int, week: Int) -> String {
        if week == 0 { return tr("No deadlines this week") }
        if today == 0 {
            return format(week == 1 ? "{n} deadline this week" : "{n} deadlines this week", ["n": String(week)])
        }
        var text = format(today == 1 ? "{n} deadline today" : "{n} deadlines today", ["n": String(today)])
        if week > today { text += " · " + format("{n} this week", ["n": String(week)]) }
        return text
    }

    /// English -> Turkish. Entries without a comment are copied from `locale_tr.py`.
    static let turkish: [String: String] = [
        "Announcements": "Duyurular",
        "Every announcement from your selected courses.": "Seçili derslerinizdeki tüm duyurular.",  // new
        "No announcements in your selected courses yet.": "Seçili derslerinizde henüz duyuru yok.",  // new
        "No date given": "Tarih belirtilmemiş",
        "Open announcement": "Duyuruyu aç",
        "Announcement": "Duyuru",
        "Some courses' announcements could not be updated. Earlier ones are shown where there are any.":
            "Bazı derslerin duyuruları güncellenemedi. Varsa önceki kayıtlar gösteriliyor.",  // new
        "Files in this announcement": "Bu duyurudaki dosyalar",  // new
        "Video and audio files (open in Blackboard)": "Video ve ses dosyaları (Blackboard'da açın)",  // new
        "Select an announcement": "Bir duyuru seçin",  // new
        "Calendar": "Takvim",
        "Due dates are updated when this page refreshes. Times are in this iPad's local time.":
            "Son teslim tarihleri bu sayfa yenilendiğinde güncellenir. Saatler bu iPad'in yerel saatine göredir.",  // new
        "Upcoming": "Yaklaşan teslimler",
        "Past due": "Tarihi geçenler",
        "Submissions are not checked; work you already handed in may show here too.":
            "Teslim durumu kontrol edilmez; tamamladığınız çalışmalar da burada görünebilir.",
        "No due dates saved.": "Kayıtlı son teslim tarihi yok.",
        "Sync to see due dates.": "Tarihleri görmek için senkronize edin.",
        "Some courses' due dates could not be updated. Earlier ones are shown where there are any.":
            "Bazı derslerin tarihleri güncellenemedi. Varsa önceki kayıtlar gösteriliyor.",
        "Untitled work": "Adsız çalışma",
        "Open in Blackboard": "Blackboard'da aç",
        "Select a due date": "Bir teslim tarihi seçin",  // new
        "Upcoming deadlines": "Yaklaşan teslim tarihleri",
        "No upcoming deadlines.": "Yaklaşan teslim yok.",
        "Due: {time}": "Teslim: {time}",
        "Points: {points}": "Puan: {points}",  // new
        "Close": "Kapat",
        "Refresh": "Yenile",  // new
        "Loading…": "Yükleniyor…",  // new
        "No courses selected.": "Seçili ders yok.",  // new
        "Your Blackboard session has expired.": "Blackboard oturumunuzun süresi doldu.",
        "Blackboard could not be reached. Pull down to try again.":
            "Blackboard'a ulaşılamadı. Yeniden denemek için aşağı çekin.",  // new
        "January": "Ocak", "February": "Şubat", "March": "Mart", "April": "Nisan", "May": "Mayıs",
        "June": "Haziran", "July": "Temmuz", "August": "Ağustos", "September": "Eylül",
        "October": "Ekim", "November": "Kasım", "December": "Aralık",
        "Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba", "Thursday": "Perşembe",
        "Friday": "Cuma", "Saturday": "Cumartesi", "Sunday": "Pazar",
        "{month} {day}": "{day} {month}",
        "{month} {day}, {year}": "{day} {month} {year}",
        "Today": "Bugün",
        "Tomorrow": "Yarın",
        "today {time}": "bugün {time}",
        "tomorrow {time}": "yarın {time}",
        "No deadlines this week": "Bu hafta teslim tarihi yok",
        "{n} deadline this week": "Bu hafta {n} teslim tarihi",
        "{n} deadlines this week": "Bu hafta {n} teslim tarihi",
        "{n} deadline today": "Bugün {n} teslim tarihi",
        "{n} deadlines today": "Bugün {n} teslim tarihi",
        "{n} this week": "bu hafta {n}",
    ]
}
