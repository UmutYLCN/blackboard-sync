# Mac App Store package (`mas`)

`Blackboard Sync.app` can be built as a sandboxed Mac App Store (`mas`) flavor
alongside the notarized Developer ID `.dmg` (`direct`, see [SIGNING.md](SIGNING.md))
and the Microsoft Store MSIX (`msstore`, see [MSIX.md](MSIX.md)).

The Mac App Store build is **free** (no in-app purchase, no trial). At runtime
`blackboard_sync.licensing.current_distribution()` returns `"mas"` whenever the
app carries its bundled `assets/mas-distribution` marker, runs inside an
`APP_SANDBOX_CONTAINER_ID` container, or has `BBSYNC_DISTRIBUTION=mas` set in
the environment.

## How the `mas` flavor differs from the direct `.dmg`

| Area | Direct `.dmg` (`direct`) | Mac App Store (`mas`) |
| --- | --- | --- |
| Bundle ID | `io.github.umutylcn.blackboard-sync` | `io.github.umutylcn.blackboard-sync.mas` (override via `BBSYNC_MAS_BUNDLE_ID`) |
| Minimum macOS | 11.0 | 13.0 (`SMAppService.mainApp`) |
| App data folder | `~/Library/Application Support/blackboard-sync` | `~/Library/Containers/<bundle-id>/Data/Library/Application Support/blackboard-sync` |
| First-launch onboarding | School + default `~/Documents/University` prefilled | School and download folder start empty; student picks school, then chooses download folder via `NSOpenPanel` (`files.user-selected.read-write`); **no sync ever runs before a folder is chosen** |
| Folder persistence | Plain path in `settings.json` | App-scoped security-scoped bookmark in `dest-bookmark.json` (`files.bookmarks.app-scope`), resolved and activated on every launch and CLI `sync` run; changing folder in Settings re-creates the bookmark |
| Sign-in & silent SSO refresh | External Chromium via CDP + Playwright fallback to `WKWebView` | In-app `WKWebView` (`inapp_macos.py`) with persistent `WKWebsiteDataStore` only; Playwright and Node.js are excluded from the bundle |
| Start at login | `~/Library/LaunchAgents/*.plist` | `SMAppService.mainApp` (opt-in, off by default per Guideline 2.4.5(iii)) |
| App updates & removal | GitHub Releases self-updater + Trash uninstaller | Self-updater and GitHub checks disabled; App Store delivers updates (`updater.store_update_url()` opens the App Store page for minimum-version prompts) |
| AI study session card | Launches Terminal / iTerm2 (`osascript`) | Opens the term folder in Terminal and copies the command for the selected tool. Paste it and press Enter to start or resume the session. |
| Gemini Notebook | External Chromium Google sign-in | Hidden in the UI and disabled with an explanatory message in `notebooklm/signin.py` (Google blocks embedded web views and App Sandbox blocks external browser CDP) |
| App Review Demo Mode | Not shown by default | **Try the demo** button on the Get started screen runs the real sync engine offline against built-in sample courses, PDFs, announcements, and deadlines (`demo.py`) |

## Entitlements

| File | Used on | Keys |
| --- | --- | --- |
| `packaging/entitlements/mas.plist` | `Blackboard Sync.app` | `com.apple.security.app-sandbox`, `com.apple.security.network.client`, `com.apple.security.network.server` (loopback listener for Google Calendar OAuth 2.0 in `gcal.py`), `com.apple.security.files.user-selected.read-write`, `com.apple.security.files.bookmarks.app-scope` |
| `packaging/entitlements/mas-inherit.plist` | Any nested helper executable | `com.apple.security.app-sandbox`, `com.apple.security.inherit` |

Neither `com.apple.security.automation.apple-events` nor `com.apple.security.cs.allow-jit` is requested.

## Local sandboxed build (no Apple certificates required)

macOS `secinitd` enforces the full App Sandbox on an ad-hoc signed `.app` bundle
when none of the entitlements are provisioning-restricted:

```sh
./scripts/build-mas.sh
```

Verify the packaged self-tests inside the real sandbox container:

```sh
"dist/Blackboard Sync.app/Contents/MacOS/Blackboard Sync" --check-login-runtime
"dist/Blackboard Sync.app/Contents/MacOS/Blackboard Sync" --check-note-pdf
"dist/Blackboard Sync.app/Contents/MacOS/Blackboard Sync" --check-mas-sandbox
```

Open `"dist/Blackboard Sync.app"` to test onboarding, `NSOpenPanel` security-scoped
bookmarks, **Try the demo**, in-app `WKWebView` sign-in, and notifications inside
`~/Library/Containers/io.github.umutylcn.blackboard-sync.mas/Data`.

## Building and signing the `.pkg` for App Store Connect

### One-time certificate & profile setup

1. **Bundle ID (App ID):** In <https://developer.apple.com/account/resources/identifiers/list>,
   register an explicit macOS App ID matching `io.github.umutylcn.blackboard-sync.mas`
   (or your chosen bundle ID, passed as `BBSYNC_MAS_BUNDLE_ID`).
2. **Certificates** (<https://developer.apple.com/account/resources/certificates/list>):
   - **Apple Distribution** (or **Mac App Distribution** / `3rd Party Mac Developer Application`) — signs the `.app` bundle and its inner Mach-O binaries.
   - **Mac Installer Distribution** (`3rd Party Mac Developer Installer`) — signs the `.pkg` installer built by `productbuild`.
3. **Provisioning Profile** (<https://developer.apple.com/account/resources/profiles/list>):
   - Create a **Mac App Store** provisioning profile for that App ID and your Apple Distribution certificate, and download `Blackboard_Sync_MAS.provisionprofile`.
4. **Numeric App ID (optional until created):** Once the app record exists in
   App Store Connect, set `MAS_APP_ID` in `src/blackboard_sync/updater.py` (or
   `BBSYNC_MAS_APP_ID` at build time) so `updater.store_update_url()` links
   directly to `macappstore://apps.apple.com/app/id<APP_ID>` instead of the
   generic `macappstore://showUpdatesPage` fallback.

### Build, sign, and package command

With both certificates in your keychain and the downloaded `.provisionprofile`:

```sh
BBSYNC_GOOGLE_OAUTH_CLIENT_FILE=.bbsync/google-oauth-client.json \
BBSYNC_REQUIRE_GOOGLE_OAUTH=1 \
BBSYNC_MAS_BUNDLE_ID="io.github.umutylcn.blackboard-sync.mas" \
BBSYNC_MAS_BUILD_NUMBER="1" \
MAS_APP_IDENTITY="Apple Distribution: Your Name (H4JR94W8MJ)" \
MAS_INSTALLER_IDENTITY="3rd Party Mac Developer Installer: Your Name (H4JR94W8MJ)" \
MAS_PROVISIONING_PROFILE="/path/to/Blackboard_Sync_MAS.provisionprofile" \
  ./scripts/build-mas.sh
```

Or sign and package an already-built `dist/Blackboard Sync.app` directly:

```sh
./scripts/sign-mas.sh "dist/Blackboard Sync.app" \
  --app-identity "Apple Distribution: Your Name (H4JR94W8MJ)" \
  --installer-identity "3rd Party Mac Developer Installer: Your Name (H4JR94W8MJ)" \
  --provisioning-profile "/path/to/Blackboard_Sync_MAS.provisionprofile" \
  --pkg-output "dist/Blackboard-Sync-1.7.2-mas.pkg"
```

This embeds `Contents/embedded.provisionprofile`, signs every inner Mach-O binary
and framework inside-out, signs `Blackboard Sync.app` with `packaging/entitlements/mas.plist`,
verifies the bundle with `codesign --verify --deep --strict`, builds
`dist/Blackboard-Sync-<version>-mas.pkg` via `productbuild --component "dist/Blackboard Sync.app" /Applications --sign ...`,
and checks the installer signature with `pkgutil --check-signature`.

Upload the resulting `.pkg` to App Store Connect with **Transporter** (or
`xcrun altool --upload-package ...`). Note that locally launching an `.app` signed
with an `Apple Distribution` certificate fails with `EXC_CRASH (Code Signature Invalid)`
on macOS by design — use the default ad-hoc (`-`) or an `Apple Development` identity
for local testing, and `Apple Distribution` + `3rd Party Mac Developer Installer`
for the `.pkg` uploaded to App Store Connect.
