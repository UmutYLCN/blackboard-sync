import SwiftUI

/// The Calendar page as on the Mac: "Upcoming" then "Past due", a card per local day with
/// each due time, title and course; the selected due date's details beside the list.
public struct DeadlinesView: View {
    @Bindable var model: DeadlinesViewModel
    let showsHeader: Bool

    /// `showsHeader: false` when the shell already titles the page.
    public init(model: DeadlinesViewModel, showsHeader: Bool = true) {
        self.model = model
        self.showsHeader = showsHeader
    }

    public var body: some View {
        MasterDetail(selection: $model.selection, selected: model.selected, master: {
            DeadlineList(model: model, showsHeader: showsHeader)
        }, detail: { row in
            if let row {
                DeadlineDetail(row: row, due: model.dueText(for: row), strings: model.strings)
            } else {
                ContentUnavailableView(model.strings.selectDeadline, systemImage: "calendar")
            }
        }, closeTitle: model.strings.close)
        .task { await model.loadIfNeeded() }
    }
}

struct DeadlineList: View {
    @Bindable var model: DeadlinesViewModel
    let showsHeader: Bool
    @Environment(\.featureTheme) private var theme

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: theme.spacing) {
                if showsHeader {
                    PageHeader(title: model.strings.calendarTab, hint: model.strings.calendarHint)
                        .padding(.bottom, 4)
                }
                if let error = model.error {
                    Notice(text: error, warning: true)
                }
                if model.phase == .loading && model.page.days.isEmpty {
                    ProgressView(model.strings.loading).frame(maxWidth: .infinity).padding(.top, 24)
                } else {
                    if !model.page.message.isEmpty {
                        Notice(text: model.page.message, warning: model.page.message == model.strings.calendarIncomplete)
                    }
                    if model.page.days.isEmpty, model.phase == .loaded, model.error == nil {
                        Text(model.strings.calendarEmpty).foregroundStyle(theme.secondaryText).padding(.horizontal, 8)
                    }
                }
                ForEach(Array(model.page.days.enumerated()), id: \.element.id) { index, day in
                    if index == 0 || model.page.days[index - 1].past != day.past {
                        SectionHeading(past: day.past, strings: model.strings)
                    }
                    DayCard(day: day, selection: $model.selection)
                }
            }
            .padding(20)
        }
        .refreshable { await model.refresh() }
    }
}

struct SectionHeading: View {
    let past: Bool
    let strings: FeatureStrings
    @Environment(\.featureTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(past ? strings.pastDue : strings.upcoming).font(.headline)
            if past {
                Text(strings.pastDueHint).font(.subheadline).foregroundStyle(theme.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 8).padding(.top, 8)
        .accessibilityAddTraits(.isHeader)
    }
}

struct DayCard: View {
    let day: DeadlineDay
    @Binding var selection: DeadlineRow.ID?
    @Environment(\.featureTheme) private var theme

    var body: some View {
        Card(warning: day.past) {
            VStack(alignment: .leading, spacing: 0) {
                Text(day.title).font(.subheadline.bold())
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 6)
                ForEach(day.rows) { row in
                    Button {
                        selection = row.id
                    } label: {
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Text(row.time).font(.body.bold().monospacedDigit()).frame(width: 58, alignment: .leading)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.title).font(.body).lineLimit(2).multilineTextAlignment(.leading)
                                Text(row.course).font(.caption).foregroundStyle(theme.secondaryText).lineLimit(1)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 8)
                        .background(selection == row.id ? theme.accent.opacity(0.12) : .clear)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(row.title), \(row.course), \(row.time)")
                }
            }
            .padding(.bottom, 6)
        }
    }
}

struct DeadlineDetail: View {
    let row: DeadlineRow
    let due: String
    let strings: FeatureStrings

    var body: some View {
        ScrollView {
            DeadlineDetailContent(row: row, due: due, strings: strings)
        }
    }
}

struct DeadlineDetailContent: View {
    let row: DeadlineRow
    let due: String
    let strings: FeatureStrings
    @Environment(\.featureTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text(row.course).font(.subheadline).foregroundStyle(theme.secondaryText)
                Text(row.title).font(.title2.bold())
            }
            VStack(alignment: .leading, spacing: 8) {
                Label(strings.due(due), systemImage: "clock")
                if let points = row.deadline.pointsText {
                    Label(strings.points(points), systemImage: "star")
                }
            }
            .font(.body)
            if row.deadline.due < Date() {
                Text(strings.pastDueHint).font(.subheadline).foregroundStyle(theme.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let url = row.deadline.url {
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
}
