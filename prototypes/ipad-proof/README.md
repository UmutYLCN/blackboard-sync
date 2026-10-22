# Blackboard iPad proof

A throwaway, foreground-only SwiftUI iPad app for the Stage 0 authentication gate: can the school's real WKWebView sign-in produce cookies that work with Blackboard REST through URLSession? It does not change or run the desktop app. It makes no school requests at launch; each network operation needs a button press.

## Open and install

1. Open `IPadProof.xcodeproj` in Xcode 26. Select the shared **IPadProof** scheme. Requires iPadOS 17 or later; no packages or XcodeGen needed.
2. In **IPadProof → Signing & Capabilities**, choose your Apple Developer **Team**, enable automatic signing, and replace `com.example.BlackboardIPadProof` with a unique bundle identifier owned by your team (for example, `your.reverse.domain.BlackboardIPadProof`). For device tests, also set the **IPadProofTests** team and a matching unique identifier ending in `Tests`.
3. Connect and trust the physical iPad, enable **Settings → Privacy & Security → Developer Mode**, select the iPad as the run destination, and press Run. Approve developer trust if iPadOS asks. No special entitlements are required.
4. Default tenant: `https://blackboard.istun.edu.tr`, taken from `src/blackboard_sync/config.py`. Edit it before signing in; use an HTTPS origin only. Sign out before switching tenants.

## Owner's physical-iPad checklist

Record iPad model, iPadOS/Xcode versions, test time, and each pass/failure. Copy the on-screen plain-text log when useful. Logs omit identities, full URLs, response bodies, cookie values, tokens, and passwords. Do not record credentials, MFA codes, or SSO URL/screen captures.

- [ ] Press **Open school sign-in**. Record the steps that appear: Blackboard page, SSO provider, account/password, MFA, authenticator app switch and return, passkey/security key, embedded-browser restriction, or unexpected popup. The current page origin is visible above the web view. Popups navigate in that same web view; note any flow that needs a separate window or external app.
- [ ] When back in Blackboard, press **Capture cookies**. Record the count and any error; cookie presence alone does not prove authentication.
- [ ] Press **Verify stored session**. Confirm the real user ID/name shown on screen. Record success or the exact HTTP status, redirect, HTML/non-JSON, or network error. A 403 is reported as access denied; a 401/login response requires sign-in again.
- [ ] Press **List current-term courses** and compare with the school's site. Select one course, then **List top-level contents + attachments**. Note missing courses/term mismatches and any attachment endpoint failures. Folders are marked; choose a top-level item with a direct attachment.
- [ ] Download one small PDF/slide deck. Confirm success and that **Open** previews it and **Share** offers another app. An HTML/login response must report failure and must not appear as a saved PDF. Repeat download should retain the existing file and create a separately named copy.
- [ ] Open **Files → On My iPad → Blackboard Proof → University → <course>**. Confirm the file exists, opens in another reader, and remains readable in airplane mode. Return online for subsequent REST tests.
- [ ] Close the login sheet, terminate the app from the app switcher, and relaunch from the home screen. Before reopening sign-in, press **Verify stored session**. Record whether it returns the same account. Repeat later (for example, next day) to observe expiry; survival is not guaranteed by persisting cookies.
- [ ] Press **Sign out** (also try during a request/download). Confirm verification becomes unavailable and downloaded files remain. Relaunch: no stored session should load. Open sign-in and note whether the app-owned school/IdP web state was cleared; institutional SSO outside the app may still authenticate you.

## Scope and credential handling

The app owns a dedicated persistent `WKWebsiteDataStore` with a fixed identifier. It reads Blackboard-host cookies with `WKHTTPCookieStore`, including HttpOnly cookies, on the student's explicit capture action. The replay jar retains domain/path/Secure/expiry scope, persists session cookies for relaunch, and accepts server rotations/deletions. URLSession uses an ephemeral configuration with automatic cookie handling and shared credential/cache storage disabled. Its delegate rebuilds every redirected download request: HTTPS only, no school cookies on other origins. API redirects stop with status diagnostics rather than silently following SSO.

Cookie records and the bound tenant live in a device-only, when-unlocked Keychain item. WebKit's separate persistent SSO data stays app-private. Neither is written to Documents. Sign out cancels the current task, invalidates URLSession, deletes the Keychain item, and clears all cookies/website data in the dedicated store. A Keychain deletion failure is shown explicitly. Downloaded/exported files remain; deleting the app removes its container. Only validated downloads are moved from a private URLSession temporary file into `Documents/University/<course>/`. Both Files sharing plist keys are enabled. Existing files are never overwritten.

The REST endpoints mirror `api.py`: `users/me`; user memberships with `expand=course` and pagination; v3 course detail fallback; public terms with private term fallback; top-level contents and attachment lists; attachment download. Current-term selection mirrors the desktop date rules: date range with a 30-day lead, latest started term, then newest-created course if no usable dates. Courses without terms and unavailable memberships/courses are excluded. This small proof does not merge bilingual term aliases, crawl children/embedded links, sync incrementally, enforce desktop media policies, or provide background/resumable transfers. Public/private term fallback and unsupported attachment endpoints leave explicit diagnostics. Large files, suspension, authentication-provider restrictions, and device-managed SSO remain unproven.

HTML/XHTML MIME types and HTML-looking body prefixes are rejected for downloads, even if labelled PDF. For this proof, legitimate HTML attachments are also rejected. Only the first 4 KB is read for sniffing; file bodies are downloaded with a URLSession download task rather than loaded into memory. Full HTML parsing and arbitrary file-type validation are outside this spike.

## Simulator validation (no school access)

From this folder, choose an installed iPad simulator by name or ID:

```sh
xcodebuild -project IPadProof.xcodeproj -scheme IPadProof \
  -destination 'platform=iOS Simulator,name=iPad (A16),OS=26.3' \
  -derivedDataPath /tmp/bbsync-ipad-proof-derived \
  CODE_SIGNING_ALLOWED=NO test
```

The host app does not load a web page or call REST at launch. Tests use synthetic cookies, dates, HTTP responses, and URLSession tasks that are never resumed. They cover host/domain/path boundaries, Secure/expiry, session-cookie persistence representation, cookie rotation/deletion, redirect credential isolation, HTML detection, filename traversal, term selection, and error redaction. Simulator tests cannot establish whether the school's actual SSO/MFA or Files integration works on the owner's iPad.

Apple references: [dedicated persistent website stores](https://developer.apple.com/documentation/webkit/wkwebsitedatastore/init(foridentifier:)), [URLSession redirect delegate](https://developer.apple.com/documentation/foundation/urlsessiontaskdelegate/urlsession(_:task:willperformhttpredirection:newrequest:completionhandler:)).
