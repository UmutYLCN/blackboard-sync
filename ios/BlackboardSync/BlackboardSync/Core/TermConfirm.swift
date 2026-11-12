import Foundation
import BlackboardSyncFeatures

/// Asking before the first download at a school: the card with the term and courses found.
///
/// The desktop apps ask only when the current term is not clear (`term_confirm.py`, PR #147); the iPad
/// asks at every school it has never downloaded from, right after the first Blackboard sign-in there, as
/// the last step of the first run. The card shows the term the app picked (`Term.current`, the same rule
/// as the desktop) with its courses, ticked as the selection of Courses (every course found, unless the
/// student already unticked some there). The student can untick courses or switch the card to another
/// term Blackboard lists. Nothing is downloaded until **Confirm and start**, which saves the ticks as the
/// selection, a switched term as the account's term choice and the school as confirmed
/// (`LibraryState.confirmedSchools`, the desktop's `term-confirm.json`), then syncs.
///
/// `needsConfirmation` is the one gate: a school with state (every library before this existed, such as
/// the first school's with its files) or one already confirmed is never asked. When the term is not
/// clear (`ambiguity`) the card says so, in the desktop's words.
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

    /// What the card offers: the school, why the term is not clear (often nothing), the terms the app
    /// picked and the other terms with courses the student can switch to (`proposal`).
    struct Card: Equatable, Identifiable {
        let school: String
        let reasons: [Reason]
        /// The current terms (`Term.current`), the "No term" group included.
        let detected: [Term]
        /// Every other term Blackboard lists with courses, newest first.
        let others: [Term]
        var id: String { school }
        /// The names of the picked terms that hold courses.
        var terms: [String] { detected.filter { !$0.courses.isEmpty }.map(\.name) }
    }

    /// The term the student switched to, saved for the account. It holds while the app still picks the
    /// same terms (`detected`); once Blackboard's current term changes, the app's pick is used again.
    struct TermChoice: Codable, Equatable {
        /// The ids of the terms the app picked when the student chose (sorted, the "No term" group left out).
        let detected: [String]
        /// The id of the term chosen instead.
        let chosen: String
    }

    /// The card as the student fills it in: the terms shown and the ticked courses.
    struct Draft: Equatable, Identifiable {
        let card: Card
        /// The id of the term switched to; nil while the card shows the app's pick.
        private(set) var choice: String?
        private(set) var ticked: Set<String>
        var id: String { card.id }

        /// Opens the card on the app's pick, ticked as Courses (`selected`).
        init(card: Card, selected: Set<String>) {
            self.card = card
            ticked = Set(TermConfirm.courses(card.detected).map(\.id)).intersection(selected)
        }

        /// The terms the card shows: the app's pick, or the chosen term with the "No term" group.
        var terms: [Term] {
            guard let choice, let term = card.others.first(where: { $0.id == choice }) else { return card.detected }
            return [term] + card.detected.filter { $0.id.isEmpty }
        }

        var courses: [CardCourse] { TermConfirm.courses(terms) }
        var rows: [Row] { TermConfirm.rows(terms) }
        /// "Fall 2026", or the picked terms' names joined when the app picked several.
        var termName: String {
            let named = terms.filter { !$0.id.isEmpty }.map(\.name)
            return (named.isEmpty ? terms.map(\.name) : named).joined(separator: ", ")
        }

        /// The ticked courses among those shown: the selection Confirm saves.
        var selection: Set<String> { ticked.intersection(courses.map(\.id)) }
        /// Confirm needs at least one course: with none, nothing would ever download.
        var canConfirm: Bool { !selection.isEmpty }

        /// Shows another term (nil: the app's pick again); every course it holds starts ticked.
        mutating func choose(_ id: String?) {
            let id = id.flatMap { id in card.others.contains { $0.id == id } ? id : nil }
            guard id != choice else { return }
            choice = id
            ticked = Set(courses.map(\.id))
        }

        mutating func toggle(_ course: String) {
            if ticked.contains(course) { ticked.remove(course) } else { ticked.insert(course) }
        }

        /// What Confirm saves as the account's term choice; nil keeps the app's pick.
        var savedChoice: TermChoice? {
            choice.map { TermChoice(detected: TermConfirm.key(card.detected), chosen: $0) }
        }
    }

    static let title = "Check your courses before the first download"
    /// When the term is clear.
    static let foundMessage = "Blackboard Sync found your current term and its courses. Untick any course you do not want, "
        + "or change the term, then tap Confirm and start. Nothing is downloaded until you do."
    /// When it is not (`ambiguity`).
    static let messageTemplate = "Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
        + "Untick any course you do not want, or change the term, then tap Confirm and start. Nothing is downloaded until you do."
    static let confirmLabel = "Confirm and start"
    static let changeTerm = "Change term"
    static let termLabel = "Term"
    static let detectedLabel = "Found by Blackboard Sync"
    static let otherTerms = "Other terms on Blackboard"
    static let selectedOne = "{selected} of {n} course selected"
    static let selectedOther = "{selected} of {n} courses selected"
    static let courseOne = "{n} course"
    static let courseOther = "{n} courses"
    static let tickOne = "Tick at least one course to start."
    static let waiting = "Waiting for you to confirm the courses to download."
    /// Every string the card shows; each has a Turkish translation.
    static let strings = [title, foundMessage, messageTemplate, confirmLabel, changeTerm, termLabel, detectedLabel,
                          otherTerms, selectedOne, selectedOther, courseOne, courseOther, tickOne, waiting]

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

    /// The one gate: the first download at this school waits for the card. True at a school the library
    /// holds nothing of (`hasSchoolState`) whose courses were never confirmed; so it asks once per school,
    /// and again only at a new school.
    static func needsConfirmation(_ library: LibraryState, tenant: URL, scope: String) -> Bool {
        let school = Self.school(tenant)
        return !hasSchoolState(library, school: school, scope: scope) && !(library.confirmedSchools ?? []).contains(school)
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

    /// What the card shows; nil when the app found no course to download (`proposal`).
    ///
    /// `detected` are the current terms, `listed` every term Blackboard lists (`BlackboardAPI.discover`).
    static func proposal(tenant: URL, detected: [Term], listed: [Term]) -> Card? {
        guard detected.contains(where: { !$0.courses.isEmpty }) else { return nil }
        let picked = Set(detected.map(\.id))
        let others = listed.filter { !$0.id.isEmpty && !$0.courses.isEmpty && !picked.contains($0.id) }
            .sorted { Term.age($0) > Term.age($1) }
        return Card(school: school(tenant), reasons: ambiguity(detected), detected: detected, others: others)
    }

    /// The card to show before the first download, or nil to download at once (`needsConfirmation`).
    static func card(library: LibraryState, tenant: URL, scope: String, detected: [Term], listed: [Term]) -> Card? {
        guard needsConfirmation(library, tenant: tenant, scope: scope) else { return nil }
        return proposal(tenant: tenant, detected: detected, listed: listed)
    }

    /// The terms to sync: the app's pick, or the term the student chose on the card while the app
    /// still picks what it picked then.
    static func apply(_ choice: TermChoice?, detected: [Term], listed: [Term]) -> [Term] {
        guard let choice, choice.detected == key(detected),
              let term = listed.first(where: { $0.id == choice.chosen && !$0.courses.isEmpty }) else { return detected }
        return [term] + detected.filter { $0.id.isEmpty }
    }

    /// The ids of the picked terms, as a `TermChoice` records them.
    static func key(_ terms: [Term]) -> [String] { terms.map(\.id).filter { !$0.isEmpty }.sorted() }

    /// Save the card (`confirm`): the ticks as the selection, the terms shown and a switched term, the
    /// school as asked. Returns the terms and the selection to sync.
    @discardableResult
    static func confirm(_ draft: Draft, scope: String, store: LibraryStore) async throws -> (terms: [Term], selected: Set<String>) {
        let terms = draft.terms, selected = draft.selection
        try await store.confirmFirstCourses(school: draft.card.school, selected: selected, terms: terms,
                                            choice: draft.savedChoice, scope: scope)
        return (terms, selected)
    }

    /// The courses of `terms`, named as their folders, in the order found.
    static func courses(_ terms: [Term]) -> [CardCourse] {
        terms.flatMap { term in term.courses.map { CardCourse(id: $0.id, name: MirrorPaths.course($0), term: term.name) } }
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

    /// The row of every course of `terms`, in the order found (`card_rows`).
    static func rows(_ terms: [Term]) -> [Row] {
        let several = terms.filter { !$0.courses.isEmpty }.count > 1
        return courses(terms).map { Row(id: $0.id, label: label($0, severalTerms: several)) }
    }

    /// The card's text in the app's language (`card_message`).
    static func message(_ card: Card, language: String) -> String {
        guard !card.reasons.isEmpty else { return L10n.text(foundMessage, language: language) }
        return L10n.text(messageTemplate, language: language)
            .replacingOccurrences(of: "{terms}", with: card.terms.isEmpty ? "?" : card.terms.joined(separator: ", "))
    }

    /// "2 of 3 courses selected" / "3 dersin 2 tanesi seçili"; the plural follows the course count.
    static func selectedLine(_ draft: Draft, language: String) -> String {
        DisplayFormat.count(draft.courses.count, one: selectedOne, other: selectedOther) { L10n.text($0, language: language) }
            .replacingOccurrences(of: "{selected}", with: String(draft.selection.count))
    }

    /// "Spring 2026 · 4 courses": a term in the Change term menu.
    static func optionLabel(_ term: Term, language: String) -> String {
        term.name + " · " + DisplayFormat.count(term.courses.count, one: courseOne, other: courseOther) {
            L10n.text($0, language: language)
        }
    }
}
