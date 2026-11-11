import SwiftUI

/// The Calendar page as a week (board pick H2 "This week"): a strip of the current week with
/// today marked and a course-coloured dot per course due, then every due date grouped as Today,
/// Later this week, Next week, Later and Past due; the selected due date's details beside the list.
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
                DeadlineDetail(row: row, due: model.dueText(for: row), strings: model.strings,
                               color: AppColor.course(model.week().colorIndex(row.deadline.courseID)))
            } else {
                ContentUnavailableView(model.strings.selectDeadline, systemImage: AppIcon.calendar)
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
        ScrollViewReader { proxy in
            ScrollView {
                // Redrawn every minute so "in 5 hours" and Past due stay true while the page is open.
                TimelineView(.everyMinute) { _ in
                    content(week: model.week(), proxy: proxy)
                }
                .padding(Spacing.l)
            }
            .refreshable { await model.refresh() }
        }
    }

    @ViewBuilder
    private func content(week: DeadlineWeek, proxy: ScrollViewProxy) -> some View {
        let strings = model.strings
        LazyVStack(alignment: .leading, spacing: Spacing.m) {
            if showsHeader && theme.showsPageTitle {
                Text(strings.calendarTab).font(.title2.bold())
            }
            if let error = model.error {
                Notice(text: error, warning: true)
            }
            if !model.page.message.isEmpty {
                Notice(text: model.page.message, warning: model.page.message == strings.calendarIncomplete)
            }
            WeekCard(model: model, week: week) { id in
                withAnimation { proxy.scrollTo(id, anchor: .center) }
            }
            ForEach(week.sections.filter { ![.today, .laterThisWeek].contains($0.kind) }) { section in
                Card(warning: section.kind == .pastDue) {
                    VStack(alignment: .leading, spacing: 0) {
                        SectionRows(section: section, week: week, model: model)
                        if section.kind == .pastDue {
                            Text(strings.pastDueHint).font(.footnote).foregroundStyle(theme.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.top, Spacing.xs)
                        }
                    }
                    .padding(.horizontal, Spacing.l).padding(.vertical, Spacing.m)
                }
            }
            Text(strings.calendarHint).font(.footnote).foregroundStyle(theme.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, Spacing.xxs)
        }
    }
}

/// "This week": the range, the seven days, and what is due today and later this week.
struct WeekCard: View {
    @Bindable var model: DeadlinesViewModel
    let week: DeadlineWeek
    let scrollTo: (DeadlineRow.ID) -> Void
    @Environment(\.featureTheme) private var theme

    var body: some View {
        let strings = model.strings
        let thisWeek = week.sections.filter { [.today, .laterThisWeek].contains($0.kind) }
        Card {
            VStack(alignment: .leading, spacing: 0) {
                // The range moves under the title when the column is narrow (portrait beside the sidebar).
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Spacing.xs) {
                        title(strings)
                        Spacer(minLength: Spacing.xs)
                        range
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        title(strings)
                        range
                    }
                }
                HStack(spacing: Spacing.xs - 2) {
                    ForEach(week.days) { day in
                        DayCell(day: day, week: week) { if let id = day.firstRowID { scrollTo(id) } }
                    }
                }
                .padding(.top, Spacing.s)
                ForEach(thisWeek) { section in
                    SectionRows(section: section, week: week, model: model)
                }
                if thisWeek.isEmpty {
                    emptyState(strings)
                }
            }
            .padding(.horizontal, Spacing.l).padding(.vertical, Spacing.m)
        }
    }

    private func title(_ strings: FeatureStrings) -> some View {
        HStack(spacing: Spacing.xs) {
            Image(systemName: AppIcon.calendar).foregroundStyle(AppColor.accentText)
            Text(strings.thisWeek).font(.headline).accessibilityAddTraits(.isHeader)
        }
    }

    private var range: some View {
        Text(week.range).font(.subheadline).foregroundStyle(theme.secondaryText).lineLimit(1)
    }

    @ViewBuilder
    private func emptyState(_ strings: FeatureStrings) -> some View {
        if model.phase == .idle || (model.phase == .loading && week.isEmpty) {
            ProgressView(strings.loading).frame(maxWidth: .infinity).padding(.top, Spacing.m)
        } else if model.page.message != strings.calendarNotLoaded {
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                if week.weekCount == 0 {
                    Text(strings.noDeadlinesThisWeek).font(.subheadline.weight(.semibold))
                        .accessibilityIdentifier("calendar.emptyWeek")
                }
                if let next = week.nextAfterWeek {
                    Button {
                        model.selection = next.id
                        scrollTo(next.id)
                    } label: {
                        Text(strings.nextDueDate("\(next.row.title), \(next.when)"))
                            .font(.subheadline).foregroundStyle(AppColor.accentText)
                            .multilineTextAlignment(.leading)
                    }
                    .buttonStyle(.plain)
                } else if week.isEmpty, model.error == nil {
                    Text(strings.calendarEmpty).font(.subheadline).foregroundStyle(theme.secondaryText)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, Spacing.m)
        }
    }
}

/// One day of the strip: weekday, date and a dot per course due; today is the solid accent.
struct DayCell: View {
    let day: WeekDay
    let week: DeadlineWeek
    let action: () -> Void
    @Environment(\.featureTheme) private var theme

    var body: some View {
        Button(action: action) {
            VStack(spacing: 3) {
                Text(day.label).font(.caption2.weight(.bold))
                    .foregroundStyle(day.isToday ? Color.white.opacity(0.85) : theme.secondaryText)
                    .lineLimit(1).minimumScaleFactor(0.7)
                Text(String(day.day.day)).font(.title3.weight(.semibold).monospacedDigit())
                    .foregroundStyle(day.isToday ? Color.white : day.isPast ? theme.secondaryText : Color.primary)
                HStack(spacing: 3) {
                    ForEach(day.courseIDs, id: \.self) { id in
                        Circle()
                            .fill(day.isToday ? Color.white : AppColor.course(week.colorIndex(id)))
                            .frame(width: 6, height: 6)
                            .opacity(day.isPast ? 0.5 : 1)
                    }
                }
                .frame(height: 6)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, Spacing.xs)
            .background(day.isToday ? AppColor.accent : AppColor.neutralFill,
                        in: RoundedRectangle(cornerRadius: Radius.control, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: Radius.control, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(day.firstRowID == nil)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(day.accessibilityLabel)
        .accessibilityAddTraits(.isButton)
        .accessibilityAddTraits(day.isToday ? .isSelected : [])
        .accessibilityIdentifier(day.isToday ? "calendar.today" : "calendar.day")
    }
}

/// A group's small upper-case title and its rows.
struct SectionRows: View {
    let section: DeadlineSection
    let week: DeadlineWeek
    @Bindable var model: DeadlinesViewModel
    @Environment(\.featureTheme) private var theme

    var body: some View {
        Text(model.strings.upper(section.title))
            .font(.caption.weight(.bold)).tracking(0.5)
            .foregroundStyle(theme.secondaryText)
            .padding(.top, Spacing.m).padding(.bottom, Spacing.xxs)
            .accessibilityLabel(section.title)
            .accessibilityAddTraits(.isHeader)
        ForEach(Array(section.rows.enumerated()), id: \.element.id) { index, row in
            if index > 0 { Divider() }
            WeekRowView(row: row, color: AppColor.course(week.colorIndex(row.row.deadline.courseID)),
                        selected: model.selection == row.id,
                        accessibility: "\(row.row.title), \(row.row.course), \(model.dueText(for: row.row))") {
                model.selection = row.id
            }
            .id(row.id)
        }
    }
}

struct WeekRowView: View {
    let row: WeekRow
    let color: Color
    let selected: Bool
    let accessibility: String
    let action: () -> Void
    @Environment(\.featureTheme) private var theme

    var body: some View {
        Button(action: action) {
            // The due time sits at the right when it fits beside the title, else under the course.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Spacing.s) {
                    tile
                    names
                    Spacer(minLength: Spacing.xs)
                    when
                }
                HStack(spacing: Spacing.s) {
                    tile
                    VStack(alignment: .leading, spacing: 2) {
                        names
                        when
                    }
                    Spacer(minLength: 0)
                }
            }
            .padding(.vertical, Spacing.xs + 2).padding(.horizontal, Spacing.xs)
            .background(selected ? AppColor.accentSoft : .clear,
                        in: RoundedRectangle(cornerRadius: Radius.small, style: .continuous))
            .padding(.horizontal, -Spacing.xs)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibility)
        .accessibilityAddTraits(.isButton)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    /// The date tile: day and month; tinted orange today.
    private var tile: some View {
        VStack(spacing: 2) {
            Text(row.dayNumber).font(.headline.monospacedDigit())
            Text(row.month).font(.system(size: 10, weight: .bold)).tracking(0.5)
                .foregroundStyle(row.isToday ? AppColor.warning : theme.secondaryText)
        }
        .frame(width: 44, height: 44)
        .background(row.isToday ? AppColor.warning.opacity(0.17) : AppColor.neutralFill,
                    in: RoundedRectangle(cornerRadius: Radius.small, style: .continuous))
    }

    private var names: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(row.row.title).font(.subheadline.weight(.medium)).lineLimit(2)
                .multilineTextAlignment(.leading)
            HStack(spacing: 6) {
                Circle().fill(color).frame(width: 7, height: 7)
                Text(row.row.course).font(.footnote).foregroundStyle(theme.secondaryText).lineLimit(1)
            }
        }
    }

    private var when: some View {
        Text(row.when).font(.footnote.weight(.semibold))
            .foregroundStyle(row.hot ? AppColor.warning : row.past ? theme.secondaryText : AppColor.accentText)
            .lineLimit(1)
    }
}

struct DeadlineDetail: View {
    let row: DeadlineRow
    let due: String
    let strings: FeatureStrings
    var color: Color = AppColor.accentText

    var body: some View {
        ScrollView {
            DeadlineDetailContent(row: row, due: due, strings: strings, color: color)
        }
    }
}

struct DeadlineDetailContent: View {
    let row: DeadlineRow
    let due: String
    let strings: FeatureStrings
    var color: Color = AppColor.accentText
    @Environment(\.featureTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Circle().fill(color).frame(width: 8, height: 8)
                    Text(row.course).font(.subheadline).foregroundStyle(theme.secondaryText)
                }
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
                // A narrow detail column (portrait beside the sidebar) drops the icon, then the large size.
                ViewThatFits(in: .horizontal) {
                    Link(destination: url) {
                        Label(strings.openInBlackboard, systemImage: "arrow.up.forward.square")
                    }
                    .buttonStyle(.appPrimaryLarge)
                    Link(strings.openInBlackboard, destination: url).buttonStyle(.appPrimaryLarge)
                    Link(strings.openInBlackboard, destination: url).buttonStyle(.appPrimary)
                }
            }
        }
        .padding(24)
        .frame(maxWidth: 760, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
