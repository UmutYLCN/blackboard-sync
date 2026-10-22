import SwiftUI

/// The Announcements page: a card per announcement (course · date, title, preview) as on
/// the Mac, and the selected one's full text, files and Blackboard link beside it.
public struct AnnouncementsView: View {
    @Bindable var model: AnnouncementsViewModel
    let showsHeader: Bool

    /// `showsHeader: false` when the shell already titles the page.
    public init(model: AnnouncementsViewModel, showsHeader: Bool = true) {
        self.model = model
        self.showsHeader = showsHeader
    }

    public var body: some View {
        MasterDetail(selection: $model.selection, selected: model.selected, master: {
            AnnouncementList(model: model, showsHeader: showsHeader)
        }, detail: { announcement in
            if let announcement {
                AnnouncementDetail(announcement: announcement, detail: model.detail(for: announcement),
                                   strings: model.strings)
            } else {
                ContentUnavailableView(model.strings.selectAnnouncement, systemImage: "megaphone")
            }
        }, closeTitle: model.strings.close)
        .task { await model.loadIfNeeded() }
    }
}

struct AnnouncementList: View {
    @Bindable var model: AnnouncementsViewModel
    let showsHeader: Bool
    @Environment(\.featureTheme) private var theme

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: theme.spacing) {
                if showsHeader {
                    PageHeader(title: model.strings.announcementsTab, hint: model.strings.announcementsHint)
                        .padding(.bottom, 4)
                }
                if let message = model.message {
                    Notice(text: message, warning: model.phase != .loaded || !model.announcements.isEmpty)
                }
                if model.announcements.isEmpty {
                    if model.phase == .loading || model.phase == .idle {
                        ProgressView(model.strings.loading).frame(maxWidth: .infinity).padding(.top, 24)
                    } else if model.phase == .loaded, model.message == nil {
                        Text(model.strings.announcementsEmpty)
                            .foregroundStyle(theme.secondaryText)
                            .padding(.horizontal, 20).padding(.top, 16)
                    }
                }
                ForEach(model.announcements) { announcement in
                    Button {
                        model.selection = announcement.id
                    } label: {
                        AnnouncementCard(announcement: announcement, detail: model.detail(for: announcement),
                                         selected: model.selection == announcement.id)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(announcement.title) · \(model.detail(for: announcement))")
                    .accessibilityHint(model.strings.openAnnouncement)
                }
            }
            .padding(20)
        }
        .refreshable { await model.refresh() }
    }
}

struct AnnouncementCard: View {
    let announcement: Announcement
    let detail: String
    let selected: Bool
    @Environment(\.featureTheme) private var theme

    var body: some View {
        Card(selected: selected) {
            VStack(alignment: .leading, spacing: 6) {
                Text(detail).font(.caption).foregroundStyle(theme.secondaryText).lineLimit(1)
                Text(announcement.title).font(.headline).multilineTextAlignment(.leading)
                if !announcement.preview.isEmpty {
                    Text(announcement.preview).font(.subheadline).foregroundStyle(theme.secondaryText)
                        .lineLimit(3).multilineTextAlignment(.leading)
                }
            }
            .padding(.horizontal, 20).padding(.vertical, 16)
        }
        .contentShape(Rectangle())
    }
}

struct AnnouncementDetail: View {
    let announcement: Announcement
    let detail: String
    let strings: FeatureStrings

    var body: some View {
        ScrollView {
            AnnouncementDetailContent(announcement: announcement, detail: detail, strings: strings)
        }
    }
}

struct AnnouncementDetailContent: View {
    let announcement: Announcement
    let detail: String
    let strings: FeatureStrings
    @Environment(\.featureTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text(detail).font(.subheadline).foregroundStyle(theme.secondaryText)
                Text(announcement.title).font(.title2.bold())
            }
            if !announcement.body.isEmpty {
                Text(Self.rendered(announcement.body))
                    .font(.body)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !announcement.files.isEmpty {
                FileSection(title: strings.filesHeading, files: announcement.files, icon: "doc")
            }
            if !announcement.media.isEmpty {
                FileSection(title: strings.mediaHeading, files: announcement.media, icon: "play.rectangle")
            }
            if let url = announcement.blackboardURL {
                Link(destination: url) {
                    Label(strings.openInBlackboard, systemImage: "arrow.up.forward.square")
                }
                .buttonStyle(.borderedProminent)
                .tint(theme.accent)
            }
        }
        .padding(24)
        .frame(maxWidth: 760, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Bold, italics and links from the Markdown; line breaks, list markers and headings kept
    /// as written, the way the desktop's note reads.
    static func rendered(_ markdown: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace,
                                                              failurePolicy: .returnPartiallyParsedIfPossible)
        return (try? AttributedString(markdown: markdown, options: options)) ?? AttributedString(markdown)
    }
}

struct FileSection: View {
    let title: String
    let files: [AnnouncementFile]
    let icon: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            Card {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(files.enumerated()), id: \.element.id) { index, file in
                        if index > 0 { Divider().padding(.leading, 48) }
                        let label = Label(file.name, systemImage: icon)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                        if let url = file.url {
                            Link(destination: url) { label }
                        } else {
                            label
                        }
                    }
                }
            }
        }
    }
}
