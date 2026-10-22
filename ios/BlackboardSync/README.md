# Blackboard Sync for iPad — foreground pilot

A native SwiftUI iPadOS 17+ app, developed separately from the desktop app and the untouched `prototypes/ipad-proof/`. Open **BlackboardSync.xcodeproj** in Xcode 26 and select the shared **BlackboardSync** scheme. No packages, project generator, server, or desktop companion are needed.

The app uses the desktop icon, blue accent, system typography, sidebar order, greeting, status/recent-download cards, and English/Turkish wording. Home, Sync activity, Courses, Settings, and the offline file browser work. Announcements, deadlines/calendar, Google Calendar, automatic background sync, notes PDFs, past terms, and choosing another destination are visibly labelled **Coming soon / Çok yakında** and have no tap actions.

## Install on a physical iPad

1. Open the project. In **BlackboardSync → Signing & Capabilities**, choose your Apple Developer **Team**, enable automatic signing, and replace placeholder **com.example.BlackboardSync** with a unique bundle ID you own. Give **BlackboardSyncTests** the same team and a unique ID ending in `Tests` if running device tests. No special entitlements are required.
2. Connect and trust the iPad, enable **Settings → Privacy & Security → Developer Mode**, select the iPad in Xcode, then Run. Approve developer trust on the iPad if requested. The target is iPad-only and supports portrait, landscape, split navigation, and system light/dark appearance.
3. The default school is `https://blackboard.istun.edu.tr`, matching desktop configuration. Before signing in, change it to another HTTPS origin if needed. Sign out before changing schools.
4. Tap **Sign in to Blackboard**, finish the school's sign-in/MFA in the embedded browser, then **Continue** when Blackboard opens. This captures app-owned school cookies and verifies `users/me`; the account appears on Home. No school password is handled by the native app.
5. Open **Courses**, choose the courses to mirror, then **Sync now**. All discovered current-term courses are selected initially; an explicit empty selection remains empty on relaunch. **Sync on app open** is off by default and can be enabled in Settings.
6. Open a course's folder, preview with **Open**, or export with **Share**. Ordinary files are also in **Files → On My iPad → Blackboard Sync → University → term → course**. Files remain available offline and after sign-out. Deleting the app removes its container; export files you want to keep first.

This target has a different bundle ID and dedicated WebKit store from the proof. Sign in once in this app; it does not import the proof's cookies or downloads.

## Sync and storage behavior

- Current-term discovery uses memberships, expanded courses with detail fallback, public/private term metadata, a 30-day lead, latest-started term, then newest-course fallback. Unavailable memberships/courses and courses without a term are excluded. Recognized English/Turkish academic semester aliases merge as on desktop, using the Turkish semester name for folder stability.
- Files go to `Documents/University/<term>/<course>/…`. Names follow macOS conventions where practical: readable Unicode/NFC, course code without section suffix, safe path components, extension preservation, and bounded UTF-8 component size. Allocated term/course folders are stable across renames/relaunch and disambiguated across collisions and accounts. Nested folders, attachment collections, and content-body/description/instructor-instruction collection links are crawled. No announcements, submissions, grades, or student attempts are queried.
- Three concurrent file transfers at most; folder discovery is serial. Discovery guards recursion at 40 levels or 10,000 already-visited items per course and limits each collection to 100 pages, with explicit errors. Repeated or foreign pagination is rejected. Progress shows discovery, completed/total files, downloads, unchanged files, skips and errors. Sync activity retains up to 1,000 entries. A failing collection/file leaves an error while other files continue; **Retry sync** makes a fresh scan of selected courses and reuses successful checkpoints.
- A private atomic manifest in Application Support records selected IDs, stable paths, SHA-256, remote metadata fingerprints, ETags and Last-Modified values. Secrets and signed embedded URLs are excluded. Completed files checkpoint individually. Interrupted runs are rediscovered on relaunch/retry; completed records avoid duplicate downloads. Temporary response files live outside Documents and are removed on failure/cancellation.
- Unchanged remote content fingerprints skip body requests. Without usable content modification metadata, conditional requests use ETag/Last-Modified and a 304 downloads no body. Servers lacking both metadata and validators require a body request; hashing then avoids replacing an identical copy. A locally missing file is downloaded again. The app does not claim zero network bytes when the server offers no way to verify freshness.
- Files stream to private staging with bounded memory. Audio/video are skipped by name or MIME type; the desktop's decimal **500,000,000-byte** cap is checked against headers and streamed byte count. HTML/XHTML MIME types and HTML-looking prefixes are rejected even when labelled PDF; these responses request reconnection. API 401/redirect/non-JSON responses request sign-in; access-denied 403 errors remain distinct. Validated bytes are committed only after the full response arrives.
- A changed remote file replaces only an unchanged local copy. Local edits/annotations are hashed and preserved; the new remote version is saved beside them as `name (2).ext`, then tracked there. Hash-identical remote bytes leave local annotations alone. File coordination and a second hash check guard save-time edits; an edit race produces a retryable error. Existing untracked files are preserved too. Paths reject traversal and symlinks.
- This pilot preserves local files when remote content disappears, a course is deselected, a school/account changes, or the student signs out. It does not implement deletion propagation or archive migration. Different accounts allocate separate collision-safe folders, while the root file browser can show all files retained on the device.

## Session and privacy

The proof's working authentication pieces are reorganized into Session and Core. A dedicated persistent `WKWebsiteDataStore` owns browser/SSO data; the cookie replay transport scopes domain, host-only status, path, Secure and expiry, accepts cookie rotations/deletions, and sends school cookies only to the exact tenant origin. Redirects rebuild requests without forwarding Cookie or Authorization to storage/SSO origins; downloads require HTTPS. URLSession is ephemeral with shared cookies, credentials and caches disabled.

Tenant-bound cookie records are stored in a when-unlocked, device-only Keychain item. Sign-out cancels and awaits current work, invalidates URLSession, deletes the Keychain item, and clears the app's dedicated WebKit data. A Keychain deletion failure stays visible and allows another sign-out attempt. Native code never logs cookies, tokens, response bodies, school URL queries, or identities. Errors retain safe HTTP/network codes and redact underlying diagnostic details. No analytics or relay server is used. Files explicitly shared to another app become that app's responsibility.

## Simulator build and tests

From this folder, the following exact command was used on the installed iPad Air 11-inch (M3) simulator (iPadOS 18.4):

```sh
xcodebuild -project BlackboardSync.xcodeproj -scheme BlackboardSync \
  -destination 'platform=iOS Simulator,id=6A750041-BCF4-4A81-93D2-6208BB031259' -destination-timeout 60 \
  -derivedDataPath /tmp/bbsync-ipad-app-derived \
  CODE_SIGNING_ALLOWED=NO test
```

For another Mac, use `xcrun simctl list devices available` and replace the destination ID, or use `-destination 'platform=iOS Simulator,name=iPad (A16),OS=latest'`. Use `build` instead of `test` for a simulator-only build. Derived data/test results stay outside the repository. The checked-in project and shared scheme build directly; there is no XcodeGen step.

Unit tests use synthetic cookies, a fake paged API, a fake mirror service and a URLProtocol transport; no school requests run. They cover naming/byte limits/Turkish course codes, traversal/symlinks, stable folder allocation, current-term selection and aliases, state restoration, explicit empty selections, SHA-256/change detection, modified-local conflicts, missing/untracked files, conditional requests, MIME/size policies, HTML-instead-of-file detection, redaction, cookie boundaries/rotation/redirect isolation, nested content/attachment pagination, embedded files, selected-course filtering, bounded concurrency, per-file retry, cancellation/checkpoint recovery, and session expiry. The hosted test app skips startup/session restoration under XCTest. A separate UI test target checks English/Turkish onboarding, navigation, inert placeholders, and portrait/landscape layouts; screenshots are attached to the `.xcresult` outside the repository.

## Owner's physical-iPad checklist

Record iPad model, OS and app version plus pass/fail notes. Do not capture passwords, MFA codes, cookie values, tokens, SSO screens or signed URLs.

- [ ] Install with your signing team and bundle ID. Confirm the app icon and sidebar resemble the Mac app. Rotate portrait/landscape, try a narrow split view, light/dark mode, larger text and VoiceOver labels.
- [ ] Sign in with the real school account/MFA, including an authenticator app switch if needed. Tap Continue and compare Home's account and current-term course list with Blackboard.
- [ ] Deselect several courses, sync a small selected course, and confirm only its files arrive. Include nested folders, a regular attachment, and an Ultra embedded/instruction file. Inspect per-file errors if one collection is unavailable.
- [ ] Run a second sync with no remote changes. Confirm zero new downloads where Blackboard provides modification metadata or validators, and no duplicate copies. Review unchanged/skipped/error counts.
- [ ] Open a PDF with another editor through Files, annotate it, then have a permitted remote update available. Sync and confirm the annotated original remains and the new remote file is saved beside it. Also confirm an unmodified local file updates in place, and a manually deleted local file downloads again.
- [ ] Confirm audio/video and a file over 500 MB are skipped and not exported. Check a login/HTML response never becomes a PDF in the mirror.
- [ ] Disconnect Wi-Fi during a multi-file sync. Review errors and Retry sync after reconnecting. Cancel mid-sync, then sync again; successful files should be reused. Lock/switch apps, force-quit during sync, relaunch and Sync now; partial transfers must not appear as completed files.
- [ ] Preview and Share from a course folder. Find the same nested files in Files, open in another reader, then repeat in airplane mode.
- [ ] Change English ↔ Türkçe in Settings; labels update immediately. Verify every Coming soon / Çok yakında row is inert, including announcements, calendar, background sync, Google Calendar, notes PDFs and past terms.
- [ ] Turn Sync on app open on/off, relaunch and verify the chosen behavior. Course selection (including selecting none) survives relaunch. Test a late session expiry: the app must offer Reconnect, with existing offline files retained.
- [ ] Sign out while idle and during a sync. Confirm the native session and app WebKit state clear, no transfer continues saving files, and offline documents remain. Relaunch without a session; no school API request should start until sign-in. A school/IdP may independently retain device-wide SSO.

## Pilot limits and parity follow-ups

The proof's real-school authentication worked on the owner's iPad; this new app still requires the physical-device checklist. Simulator fixtures cannot establish institutional SSO behavior, actual attachment metadata/validators, device Files editing, or network behavior under suspension.

Sync runs while the app is active. Entering the background cancels cooperatively; return and Sync now to continue, or enable Sync on app open. Transfers restart per incomplete file; there is no HTTP Range resume or scheduled/background transfer service. Byte-level progress for a single large file, a Files provider extension/external destination, advanced rich-text-to-PDF generation, full arbitrary HTML parsing and distribution/App Store readiness are future work. Embedded discovery supports Blackboard collection/upload attributes and common tags, rather than a general web crawler. No background timing promise is made.

The practical iPad adaptations are immediate settings persistence (no Save/restart step), an in-app folder browser instead of a Finder button, native Open/Share, and system SwiftUI layout. Term/course folder naming follows desktop semantics; shorter component budgets and numbered collision suffixes are used on iPad. Existing allocations remain stable rather than migrating a renamed course's local folder. These details should be compared against representative owner courses before broader distribution.
