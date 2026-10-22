# BlackboardSyncFeatures

The iPad app's **Announcements** and **Calendar** (due dates) pages, as a Swift package the app
shell embeds. It does no networking, cookie or Keychain work of its own: the shell hands it a
tiny HTTP protocol and the selected courses, and gets back SwiftUI views.

Behaviour follows the desktop app:

| iPad | Desktop source |
| --- | --- |
| Public announcements endpoint, then the private one; drafts skipped; newest first, undated last | `api.py` `announcements`, `sync.py` `sync_announcements`, `announcements.py` `rows` |
| Title unescaped, date = availability start → created → modified, 240-character preview | `announcements.py` `metadata` |
| Body as readable text (headings, lists, bold, links), files from `data-bbfile` / `bbcswebdav` links, videos and audio listed apart | `htmltext.py`, `notes.py` `render_announcement_note` |
| Due dates from `grading.due` only, with an explicit offset; hidden columns skipped; link to the content or the grades page | `deadlines.py` `parse_due`, `column_deadline` |
| Grouped by local day, upcoming ascending, past due newest first, same-day split at "now"; DST-safe | `deadlines.py` `calendar_page` |
| A failed course keeps what it showed before and the page says so; an expired session is never swallowed | `sync.py` `sync_deadlines`, `test_deadlines.py` |
| Home helpers: next due dates, "1 deadline today · 3 this week", "tomorrow 09:00" | `deadlines.py` `upcoming_rows`, `count_due`, `when_text`; `main_window_model.py` `deadline_subtitle` |
| English and Turkish texts | `i18n.py`, `locale_tr.py` |

Differences, on purpose:

- The pages read Blackboard live when they appear and on pull-to-refresh; there is no sync state.
- Both announcement endpoints answering 403 or 404 means the course has no announcements (no tool
  or no collection), so it shows as empty instead of as a failure. Due dates keep the desktop rule:
  a refused gradebook (403) marks the course "could not be updated".
- `<script>`/`<style>` text is hidden in the detail text as well as in the preview.
- The desktop has no read/unread state for announcements, so neither does this package.
- Google Calendar export is not included.
- Texts that would be untrue on an iPad ("synced", "this computer") are reworded; they are marked
  `// new` in `FeatureStrings.swift` along with the few texts the desktop does not have. Every
  other Turkish text is copied from `locale_tr.py`.

## Tests

```sh
cd ios/BlackboardSyncFeatures
swift test
```

On an iPad simulator (pick any iPad from `xcrun simctl list devices available`):

```sh
cd ios/BlackboardSyncFeatures
xcodebuild test -scheme BlackboardSyncFeatures \
  -destination 'platform=iOS Simulator,name=iPad (A16),OS=26.3.1'
```

Fixtures in `Tests/BlackboardSyncFeaturesTests/Fixtures` are shaped like the desktop tests'
fake Blackboard answers.

## Wiring it into the shell

The app in `ios/BlackboardSync` is wired this way: see its `Features/FeatureBridge.swift` and
`Views/FeatureViews.swift`. The steps below describe the contract.

Add the package to the app project (File ▸ Add Package Dependencies ▸ Add Local…, choose
`ios/BlackboardSyncFeatures`) and link the `BlackboardSyncFeatures` library.

### 1. What the shell provides

```swift
import BlackboardSyncFeatures

/// Wraps the shell's signed-in URLSession client.
struct ShellHTTP: BlackboardHTTP {
    let client: BlackboardClient  // the shell's own type

    func getJSON(_ path: String) async throws -> Data {
        // `path` is tenant-relative with its query, e.g.
        // "/learn/api/public/v1/courses/_1_1/announcements?limit=100", or a `paging.nextPage`
        // value exactly as Blackboard sent it (the package only passes paths that start with
        // a single "/").
        let (data, response) = try await client.get(path, accept: "application/json")
        switch response.statusCode {
        case 200..<300:
            guard response.mimeType?.contains("json") == true else { throw BlackboardHTTPError.notJSON }
            return data
        case 401: throw BlackboardHTTPError.loginRequired
        default: throw BlackboardHTTPError.status(response.statusCode)
        }
        // Also throw .loginRequired when Blackboard redirects to a sign-in page.
    }
}

/// The current-term courses the student left ticked.
struct ShellCourses: CourseProvider {
    let store: CourseStore  // the shell's own type

    func selectedCourses() async throws -> [FeatureCourse] {
        await store.selected.map { FeatureCourse(id: $0.id, name: "\($0.code) \($0.title)") }
    }
}
```

- `FeatureCourse.id` is Blackboard's internal id (`_13004_1`); `name` is what the student reads.
- Never log tokens, cookies or response bodies in `getJSON`; the package logs nothing.
- Any other error thrown from `getJSON` (offline, timeout) marks only that course as failed.

### 2. Make the view models once per signed-in session

```swift
@MainActor
final class FeatureModels {
    let announcements: AnnouncementsViewModel
    let deadlines: DeadlinesViewModel

    init(http: some BlackboardHTTP, courses: some CourseProvider, tenant: URL, language: String,
         signOut: @escaping @MainActor () -> Void) {
        let strings = FeatureStrings(FeatureLanguage(code: language))  // "en" or "tr"
        announcements = AnnouncementsViewModel(http: http, courses: courses, baseURL: tenant,
                                               strings: strings, onSignInRequired: signOut)
        deadlines = DeadlinesViewModel(http: http, courses: courses, baseURL: tenant,
                                       strings: strings, onSignInRequired: signOut)
    }
}
```

`onSignInRequired` runs when Blackboard answers that the session expired; the page then shows
"Your Blackboard session has expired." and keeps what it showed. Call `refresh()` on both models
after the course selection changes.

### 3. Embed the views

```swift
// In the sidebar's detail column, in place of the "coming soon" placeholders:
case .announcements: AnnouncementsView(model: models.announcements)
case .calendar:      DeadlinesView(model: models.deadlines)
```

- Each page loads on first appearance and refreshes on pull-down.
- With room (regular width) the list and the selected item sit side by side; in Slide Over or a
  narrow split the item opens as a sheet.
- `showsHeader: false` hides the page's own title and hint when the shell already shows them.
- `.featureTheme(FeatureTheme(...))` on any ancestor applies the shell's colors; the default uses
  system semantic colors that match the Mac app's cards.
- For Home: `DeadlineCalendar.upcomingRows(models.deadlines.page, limit: 3)`,
  `models.deadlines.subtitle` and `models.deadlines.whenText(for:)` ("tomorrow 09:00").

`PreviewData` gives fake-backed models for SwiftUI previews (`#Preview` blocks are in
`Fakes/PreviewData.swift`), and `FakeBlackboardHTTP` answers from a table for tests.
