import SwiftUI
import BlackboardSyncFeatures

// The two first-run screens (board picks F1 and F2). `AppModel.firstRunScreen` decides which one shows.

/// F1: the full-screen first-run page, shown instead of the app until Blackboard is signed in for the
/// first time. The logo with what the app brings around it, the school, one button; language is the
/// only other control, since Settings is not reachable from here.
struct FirstRunPage: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                FirstRunColumn(footnote: "You sign in on your school's own page. Your password is never stored.",
                               titleFont: .largeTitle.bold()) {
                    ZStack {
                        Image("FirstRunOrbit").resizable().scaledToFit()
                        Image("Logo").resizable().scaledToFit().frame(width: 168, height: 168)
                    }
                    .frame(width: 396, height: 288)
                    .accessibilityHidden(true)
                }
                .frame(maxWidth: 460)
                .padding(.horizontal, Spacing.page)
                .padding(.vertical, Spacing.xxl)
                .frame(maxWidth: .infinity, minHeight: proxy.size.height)
            }
            .scrollBounceBehavior(.basedOnSize)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("firstRun.page")
        }
        .overlay(alignment: .topTrailing) { LanguageMenu().padding(.trailing, Spacing.page).padding(.top, Spacing.s) }
        .background(alignment: .top) {
            GeometryReader { proxy in
                RadialGradient(colors: [AppColor.accentSoft, .clear], center: UnitPoint(x: 0.5, y: 0.3),
                               startRadius: 0, endRadius: max(proxy.size.width, proxy.size.height) * 0.42)
            }
        }
        .background(Color(uiColor: .systemGroupedBackground))
    }
}

/// F2: Home and Courses while Blackboard is signed out and no file is downloaded: a centred welcome
/// with the same school and button as F1, inside the app.
struct WelcomeCard: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        FirstRunColumn(footnote: "Your password is never stored.", titleFont: .title.bold()) {
            Image("FirstRunWelcome").resizable().scaledToFit().frame(width: 340).accessibilityHidden(true)
        }
        .frame(maxWidth: 420)
        .padding(.vertical, Spacing.xl)
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("firstRun.card")
    }
}

/// The column both screens share: the picture, the title, the line under it, the school, the button.
private struct FirstRunColumn<Art: View>: View {
    @EnvironmentObject var model: AppModel
    let footnote: String
    let titleFont: Font
    @ViewBuilder var art: Art

    var body: some View {
        VStack(spacing: 0) {
            art.padding(.bottom, Spacing.xs)
            Text(model.text("Your course files, on your iPad.")).font(titleFont)
                .multilineTextAlignment(.center).padding(.bottom, Spacing.s)
                .accessibilityAddTraits(.isHeader)
            Text(model.text("Sign in once with your school account. Your files, due dates and announcements show up here."))
                .font(.body).foregroundStyle(.secondary).multilineTextAlignment(.center)
                .padding(.bottom, Spacing.xl)
            SchoolField().padding(.bottom, Spacing.s)
            Button { model.signIn() } label: {
                Text(model.text("Sign in to Blackboard")).frame(maxWidth: .infinity)
            }
            .buttonStyle(.appPrimaryLarge).disabled(model.busy)
            .accessibilityIdentifier("firstRun.signIn")
            if let error = model.errorMessage {
                Text(model.text(error)).font(.callout).foregroundStyle(AppColor.warning)
                    .multilineTextAlignment(.center).padding(.top, Spacing.s)
            }
            Label(model.text(footnote), systemImage: "lock.fill")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
                .padding(.top, Spacing.m)
        }
    }
}

/// The school as one row: a menu of the known schools and "Other school…", which shows the address field.
private struct SchoolField: View {
    @EnvironmentObject var model: AppModel
    @State private var other = false

    var body: some View {
        VStack(spacing: Spacing.s) {
            Menu {
                // First, so it is in reach above the long list of schools.
                Button(model.text("Other school…")) { other = true; model.tenantText = "" }
                Divider()
                ForEach(Schools.all, id: \.url) { school in
                    Button(school.name) { model.tenantText = school.url; other = false }
                }
            } label: {
                HStack(spacing: Spacing.s) {
                    Image(systemName: "building.columns").font(.title3).foregroundStyle(AppColor.accentText)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(model.text("School")).font(.caption).foregroundStyle(.secondary)
                        Text(schoolName).font(.callout.weight(.semibold)).foregroundStyle(.primary).lineLimit(1)
                    }
                    Spacer(minLength: Spacing.xs)
                    Image(systemName: "chevron.up.chevron.down").font(.footnote).foregroundStyle(.tertiary)
                }
                .padding(.horizontal, Spacing.m)
                .frame(minHeight: 60)
                .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: Radius.control))
                .overlay(RoundedRectangle(cornerRadius: Radius.control).stroke(.primary.opacity(0.055), lineWidth: 1))
                .contentShape(RoundedRectangle(cornerRadius: Radius.control))
            }
            // A menu label takes the accent tint; the row keeps its own ink, like the board's.
            .tint(.primary)
            .disabled(model.busy)
            .accessibilityIdentifier("firstRun.school")
            if showsAddress {
                TextField(model.text("Your school's Blackboard address"), text: $model.tenantText)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    .padding(.horizontal, Spacing.m).frame(minHeight: 48)
                    .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: Radius.control))
                    .disabled(model.busy)
                    .accessibilityIdentifier("firstRun.address")
            }
        }
    }

    private var known: KnownSchool? { Schools.find(URL(string: model.tenantText)?.host ?? model.tenantText) }
    private var showsAddress: Bool { other || known == nil }
    private var schoolName: String {
        if let known, !other { return known.name }
        return model.text("Other school…")
    }
}

/// F1's language control: the language's own name, as in Settings.
private struct LanguageMenu: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        Menu {
            Picker(model.text("Language"), selection: $model.language) {
                Text(verbatim: "English").tag("en")
                Text(verbatim: "Türkçe").tag("tr")
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "globe")
                Text(verbatim: model.language == "tr" ? "Türkçe" : "English")
                Image(systemName: "chevron.down").font(.caption2.weight(.semibold))
            }
            .font(.subheadline.weight(.medium)).foregroundStyle(AppColor.accentText)
            .frame(minHeight: TopBarMetrics.target)
        }
        .accessibilityLabel(Text(model.text("Language")))
        .accessibilityIdentifier("firstRun.language")
    }
}
