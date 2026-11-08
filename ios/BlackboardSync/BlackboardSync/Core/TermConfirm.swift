import Foundation

/// Asking before the first download at a school when the current term is not clear: a twin of the
/// desktop `term_confirm.py` (PR #147). Each function names its Python twin so the two stay easy to compare.
///
/// The first sync at a school (no state for it yet) downloads at once when the term choice is clear:
/// dated terms, one running group, names that give a year and a season. When it is not (`ambiguity`:
/// a term without dates or with dates left from an earlier year, terms that started on different days,
/// a name that gives no year and season), Sync now downloads nothing and the app shows a card with the
/// terms and courses found. Its ticks are the course selection of Courses (every course found, unless the
/// student already unticked some there). Confirm saves the ticks as that selection and the school as
/// confirmed (`LibraryState.confirmedSchools`, the desktop's `term-confirm.json`), and syncs. Not now saves
/// nothing, so the next sync asks again.
///
/// A school with state (every library before this existed, such as the first school's with its files)
/// is never asked.
enum TermConfirm {
    /// Why the current term is not clear (`ambiguity`); the raw values are the desktop's.
    enum Reason: String, Equatable {
        case undated // a term without dates
        case staleDates = "stale_dates" // a term whose dates ended before its courses were made
        case severalStarts = "several_starts" // terms that started on different days
        case unknownName = "unknown_name" // a term whose name gives no year and season
    }

    /// One course on the card.
    struct CardCourse: Equatable, Identifiable {
        let id: String
        /// "CSE303 Algorithm Analysis", as its folder is named.
        let name: String
        let term: String
    }

    /// What the card shows: the school, why it asks, the terms and their courses (`proposal`).
    struct Card: Equatable, Identifiable {
        let school: String
        let reasons: [Reason]
        let terms: [String]
        let courses: [CardCourse]
        var id: String { school }
    }

    static let title = "Check your courses before the first download"
    static let messageTemplate = "Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
        + "Untick any course you do not want, then confirm. Nothing is downloaded until you do."
    static let confirmLabel = "Confirm"
    static let notNow = "Not now"
    static let waiting = "Waiting for you to confirm the courses to download."

    /// `school_of`: the school's host, as `LibraryStore.useSchool` records it.
    static func school(_ tenant: URL) -> String { (tenant.host ?? "").lowercased() }

    /// The library holds something of the school (`has_school_state`).
    ///
    /// On the iPad, finding the courses records the school and its folders before anything is
    /// downloaded, so the school's state is what a sync left: a sync run at the school
    /// (`syncedSchools`), or a downloaded file of this account there (file records are keyed by the
    /// account scope, which holds the school's address). A library from before syncs were recorded per
    /// school belongs to the school in use when a sync ever ran in it, like the desktop's state file from
    /// before schools were recorded: the first school's users keep syncing as before.
    static func hasSchoolState(_ library: LibraryState, school: String, scope: String) -> Bool {
        if library.syncedSchools?.contains(school) == true { return true }
        if library.records.keys.contains(where: { $0.hasPrefix(scope + ":") }) { return true }
        return library.syncedSchools == nil && (!library.records.isEmpty || library.lastSync != nil)
    }

    /// Why the term choice of the first sync is not clear; empty when it is (`ambiguity`).
    ///
    /// `terms` are the current terms (`Term.current`); courses without a term always come along and
    /// say nothing about the term.
    static func ambiguity(_ terms: [Term]) -> [Reason] {
        let dated = terms.filter { !$0.id.isEmpty }
        guard terms.contains(where: { !$0.courses.isEmpty }) else { return [] }
        var reasons: [Reason] = []
        if dated.contains(where: { $0.start == nil }) { reasons.append(.undated) }
        if dated.contains(where: Term.hasStaleDates) { reasons.append(.staleDates) }
        if Set(dated.filter { !Term.hasStaleDates($0) }.compactMap(\.start)).count > 1 { reasons.append(.severalStarts) }
        if dated.contains(where: { term in term.names.allSatisfy { Term.academicOrder($0) == nil } }) {
            reasons.append(.unknownName)
        }
        return reasons
    }

    /// What the card shows; nil when nothing needs asking (`proposal`).
    static func proposal(tenant: URL, terms: [Term]) -> Card? {
        let reasons = ambiguity(terms)
        let found = terms.flatMap { term in term.courses.map { (course: $0, term: term.name) } }
        guard !reasons.isEmpty, !found.isEmpty else { return nil }
        return Card(school: school(tenant), reasons: reasons, terms: terms.filter { !$0.courses.isEmpty }.map(\.name),
                    courses: found.map { CardCourse(id: $0.course.id, name: MirrorPaths.course($0.course), term: $0.term) })
    }

    /// The card a sync must show before downloading anything, or nil to sync at once (the desktop's
    /// `run_sync(confirm_first=True)`): only at a school with no state that was never confirmed.
    static func card(library: LibraryState, tenant: URL, scope: String, terms: [Term]) -> Card? {
        let school = Self.school(tenant)
        guard !hasSchoolState(library, school: school, scope: scope),
              !(library.confirmedSchools ?? []).contains(school) else { return nil }
        return proposal(tenant: tenant, terms: terms)
    }

    /// The courses ticked when the card opens: those of the selection (`selected` in Courses).
    static func initialTicks(_ card: Card, selected: Set<String>) -> Set<String> {
        Set(card.courses.map(\.id)).intersection(selected)
    }

    /// The selection after Confirm: the card's courses as ticked, other courses as they were.
    static func confirmedSelection(_ card: Card, ticked: Set<String>, selected: Set<String>) -> Set<String> {
        let shown = Set(card.courses.map(\.id))
        return selected.subtracting(shown).union(ticked.intersection(shown))
    }

    /// Save the choice on the card (`confirm`): the ticks as the selection, the school as asked.
    /// Returns the new selection. Not now calls nothing, so nothing is saved.
    @discardableResult
    static func confirm(_ card: Card, ticked: Set<String>, selected: Set<String>, scope: String,
                        store: LibraryStore) async throws -> Set<String> {
        let chosen = confirmedSelection(card, ticked: ticked, selected: selected)
        try await store.confirmFirstCourses(school: card.school, selected: chosen, scope: scope)
        return chosen
    }

    /// One course on the card, with its term when the card shows more than one (`course_label`).
    static func label(_ course: CardCourse, severalTerms: Bool) -> String {
        severalTerms && !course.term.isEmpty ? course.name + " · " + course.term : course.name
    }

    /// One row of the card: the course id and its label.
    struct Row: Equatable, Identifiable {
        let id: String
        let label: String
    }

    /// The row of every course on the card, in the order found (`card_rows`).
    static func rows(_ card: Card) -> [Row] {
        let several = card.terms.count > 1
        return card.courses.map { Row(id: $0.id, label: label($0, severalTerms: several)) }
    }

    /// The card's text in the app's language (`card_message`).
    static func message(_ card: Card, language: String) -> String {
        L10n.text(messageTemplate, language: language)
            .replacingOccurrences(of: "{terms}", with: card.terms.isEmpty ? "?" : card.terms.joined(separator: ", "))
    }
}
