import Foundation

/// One announcement, with everything the list and the detail pane show.
public struct Announcement: Identifiable, Hashable, Sendable {
    /// "announcement:<course id>:<announcement id>", the desktop's state key.
    public let id: String
    public let courseID: String
    public let course: String
    public let title: String
    /// Availability start, else created, else modified; nil when none can be read.
    public let date: Date?
    /// One line of plain text, at most `previewLimit` characters.
    public let preview: String
    /// The body as light Markdown, as in the desktop's announcement note.
    public let body: String
    /// Files embedded in the body, videos and audio left out.
    public let files: [AnnouncementFile]
    /// Videos and audio, which the desktop only links to.
    public let media: [AnnouncementFile]
    /// The course's announcements page in Blackboard.
    public let blackboardURL: URL?

    public static let previewLimit = 240

    public init(id: String, courseID: String, course: String, title: String, date: Date?, preview: String,
                body: String, files: [AnnouncementFile], media: [AnnouncementFile], blackboardURL: URL?) {
        self.id = id
        self.courseID = courseID
        self.course = course
        self.title = title
        self.date = date
        self.preview = preview
        self.body = body
        self.files = files
        self.media = media
        self.blackboardURL = blackboardURL
    }

    /// Reads one element of Blackboard's `results`; nil for a draft or an entry without id
    /// (`sync_announcements` skips drafts).
    public init?(json: JSONValue, course: FeatureCourse, baseURL: URL, strings: FeatureStrings) {
        guard !(json["draft"]?.isTruthy ?? false), let announcementID = json["id"]?.text else { return nil }
        let html = HTMLText.bodyHTML(json["body"])
        let title = HTMLEntities.decode(json["title"]?.text ?? strings.untitledAnnouncement)
        let embedded = EmbeddedFile.find(in: html).map { file in
            // An unnamed file is called after its announcement, as the desktop names it.
            AnnouncementFile(id: file.xid, name: file.name.isEmpty ? title : file.name,
                             url: file.link(base: baseURL), isMedia: file.isMedia)
        }
        let duration = json["availability"]?["duration"]
        let dateText = duration?["start"]?.text ?? json["created"]?.text ?? json["modified"]?.text ?? ""
        self.init(
            id: "announcement:\(course.id):\(announcementID)",
            courseID: course.id,
            course: course.name,
            title: title,
            date: Self.parseDate(dateText),
            preview: Self.shorten(HTMLText.plainText(html)),
            body: HTMLText.markdown(html),
            files: embedded.filter { !$0.isMedia },
            media: embedded.filter(\.isMedia),
            blackboardURL: Links.resolve("/ultra/courses/\(course.id)/announcements", base: baseURL)
        )
    }

    /// A value without an offset is read as UTC (`announcements._date`).
    static func parseDate(_ value: String) -> Date? {
        ISODate.parse(value)?.date
    }

    static func shorten(_ text: String) -> String {
        guard text.count > previewLimit else { return text }
        return String(text.prefix(previewLimit - 1)).trimmingTrailingWhitespace() + "…"
    }

    /// "13.10.2026 15:00" in `timeZone`, or "No date given".
    public func dateText(in timeZone: TimeZone, strings: FeatureStrings) -> String {
        guard let date else { return strings.noDate }
        let local = LocalTime(date, timeZone)
        return String(format: "%02d.%02d.%04d %@", local.day.day, local.day.month, local.day.year, local.time)
    }

    /// "CSE303 Algorithm Analysis · 13.10.2026 15:00" (`AnnouncementRow.detail`).
    public func detail(in timeZone: TimeZone, strings: FeatureStrings) -> String {
        "\(course) · \(dateText(in: timeZone, strings: strings))"
    }

    /// Newest first, undated last; ties by key, as `announcements.rows`.
    public static func newestFirst(_ items: [Announcement]) -> [Announcement] {
        items.sorted { a, b in
            let (left, right) = (a.date ?? .distantPast, b.date ?? .distantPast)
            return left != right ? left > right : a.id > b.id
        }
    }
}

/// A file linked from an announcement's body.
public struct AnnouncementFile: Identifiable, Hashable, Sendable {
    /// The content-collection id, or "upload-<hex>".
    public let id: String
    public let name: String
    /// The permanent Blackboard link; nil when the body's link is not http(s).
    public let url: URL?
    public let isMedia: Bool

    public init(id: String, name: String, url: URL?, isMedia: Bool) {
        self.id = id
        self.name = name
        self.url = url
        self.isMedia = isMedia
    }
}
