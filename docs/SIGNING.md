# macOS signing and notarization

Release builds of `Blackboard Sync.app` can be signed with the maintainer's
**Developer ID Application** certificate and notarized by Apple, so the app
opens without the "developer cannot be verified" warning and `install.sh` can
check it really comes from this project. The app is distributed outside the
App Store (GitHub Releases and the one-line installer), which is what a
Developer ID is for.

Nothing changes until the secrets below exist: without them every release is
built exactly as before (ad-hoc signed `.dmg`). Windows signing is separate
work.

## What the release workflow does

On a `v*` tag push, `.github/workflows/release.yml`:

1. `dmg` job: builds and tests the app as before and uploads both the unsigned
   `.dmg` and the unsigned `.app` (zipped with `ditto`).
2. `macos-sign` job, on a fresh macOS runner. Without signing secrets it only
   prints a notice. With them it:
   - imports the `.p12` into a temporary keychain and checks the certificate's
     team is the `TEAM_ID` in `install.sh` (it stops otherwise);
   - signs every library and executable in the app, then the app, with the
     hardened runtime and a secure timestamp (`scripts/sign-macos.sh`);
   - notarizes the app with `notarytool` and staples the ticket
     (`scripts/notarize-macos.sh`);
   - packs it into the `.dmg` (`scripts/make-dmg.sh`), signs, notarizes and
     staples the `.dmg`;
   - deletes the keychain and the notary key file;
   - checks the result the way `install.sh` and Gatekeeper will
     (`codesign --verify --deep --strict`, the team requirement,
     `stapler validate`, `spctl --assess`) and runs the app's sign-in self-test
     under the hardened runtime.
3. `release` job: publishes the signed `.dmg` (or the unsigned one when
   nothing was signed) with the Windows installer and `SHA256SUMS.txt`.

The signing secrets are used only by the `macos-sign` job, which runs only on
a tag push. Pull requests (including from forks) and manual runs never reach
it, and no third-party code (dependencies, PyInstaller) runs on that runner
while the certificate is in its keychain. All actions are pinned to commit SHAs.

Half-configured secrets (for example the certificate without notarization
credentials) fail the release instead of silently publishing an unsigned app.

## One-time setup (maintainer)

You need a paid Apple Developer Program membership. On an individual
membership you are the Account Holder, the only role that can create a
Developer ID certificate.

### 1. Check the Team ID

Open <https://developer.apple.com/account> → **Membership details** and note
the **Team ID** (10 characters). `install.sh` trusts exactly one team:

```sh
TEAM_ID="H4JR94W8MJ"
```

This value was read from the Apple Development certificate on the
maintainer's Mac (`O=UMUT YALCIN, OU=H4JR94W8MJ`). If your membership's Team
ID is different, change `TEAM_ID` in `install.sh` and merge that before the
first signed release. The workflow refuses to sign with a certificate of any
other team, so a mismatch fails the release and does not break installs.

### 2. Create the Developer ID Application certificate

1. On your Mac open **Keychain Access** → menu **Keychain Access** →
   **Certificate Assistant** → **Request a Certificate From a Certificate
   Authority…**. Enter your email and name, choose **Saved to disk**, and save
   `CertificateSigningRequest.certSigningRequest`.
2. Go to <https://developer.apple.com/account/resources/certificates/add>,
   choose **Developer ID Application**, continue, pick the **G2 Sub-CA**
   profile, upload the request file and download `developerID_application.cer`.
3. Double-click the `.cer` file to add it to your **login** keychain.

(Xcode can do the same: **Settings → Accounts → Manage Certificates… → + →
Developer ID Application**.)

Check it is there with its private key:

```sh
security find-identity -v -p codesigning | grep "Developer ID Application"
# 1) 0123ABCD... "Developer ID Application: Your Name (H4JR94W8MJ)"
```

The part in parentheses is the Team ID from step 1.

### 3. Export it as a .p12

1. In **Keychain Access** → **login** → **My Certificates**, find
   **Developer ID Application: Your Name (TEAMID)** and expand it: a private
   key must be underneath.
2. Right-click the certificate → **Export…** → format **Personal Information
   Exchange (.p12)** → save as `DeveloperID.p12`.
3. Set a long, random password (for example from your password manager). This
   is `MACOS_CERTIFICATE_PASSWORD`.

### 4. Create the notarization credentials

Recommended: an **App Store Connect API key**.

1. Open <https://appstoreconnect.apple.com/access/integrations/api> (**Users
   and Access → Integrations → App Store Connect API**). The first time, the
   Account Holder has to click **Request Access** and accept the terms.
2. Under **Team Keys**, click **+** (Generate API Key), name it
   `blackboard-sync notarization`, access **Developer**, and generate.
3. Download `AuthKey_<KEYID>.p8`. Apple lets you download it **once**.
4. Note the **Key ID** (in the table) and the **Issuer ID** (above the table).

Alternative: an Apple ID with an **app-specific password**: at
<https://account.apple.com> → **Sign-In and Security → App-Specific
Passwords**, create one named `blackboard-sync notarization`.

### 5. Add the repository secrets

GitHub → repository **Settings → Secrets and variables → Actions → New
repository secret** (repository secrets, not environment or Dependabot
secrets). Names must match exactly:

| Secret | Value |
| --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | `DeveloperID.p12`, base64-encoded |
| `MACOS_CERTIFICATE_PASSWORD` | the `.p12` password from step 3 |
| `MACOS_NOTARY_API_KEY` | the full text of `AuthKey_<KEYID>.p8`, including the `BEGIN`/`END` lines |
| `MACOS_NOTARY_API_KEY_ID` | the Key ID |
| `MACOS_NOTARY_API_ISSUER_ID` | the Issuer ID |

or, instead of the three `MACOS_NOTARY_API_*` secrets:

| Secret | Value |
| --- | --- |
| `MACOS_NOTARY_APPLE_ID` | your Apple ID email |
| `MACOS_NOTARY_APP_PASSWORD` | the app-specific password |

If both sets exist, the API key is used.

With the GitHub CLI, from the folder holding the files (the values never
appear on screen or in your shell history):

```sh
base64 -i DeveloperID.p12 | gh secret set MACOS_CERTIFICATE_P12_BASE64 -R UmutYLCN/blackboard-sync
gh secret set MACOS_CERTIFICATE_PASSWORD -R UmutYLCN/blackboard-sync        # paste, then Enter
gh secret set MACOS_NOTARY_API_KEY -R UmutYLCN/blackboard-sync < AuthKey_<KEYID>.p8
gh secret set MACOS_NOTARY_API_KEY_ID -R UmutYLCN/blackboard-sync
gh secret set MACOS_NOTARY_API_ISSUER_ID -R UmutYLCN/blackboard-sync
```

Then keep `DeveloperID.p12` (with its password) and the `.p8` file in your
password manager or another safe place, and delete the loose copies from
Downloads/Desktop. Never commit them.

Optional hardening: a repository **ruleset** for tags matching `v*` that only
lets you create them (Settings → Rules → Rulesets → New tag ruleset), since a
`v*` tag push is what unlocks the secrets.

## Test with a pre-release before a real release

A tag with a `-` is published as a **pre-release**: `install.sh` (which uses
`releases/latest`) and the in-app updater ignore it, so testing does not reach
students. The tag must match `__version__`, so make a throwaway commit:

```sh
git fetch origin
git switch -c signing-test origin/main
sed -i '' 's/^__version__ = .*/__version__ = "1.3.0-rc1"/' src/blackboard_sync/__init__.py
git commit -am "Test signed release 1.3.0-rc1"
git tag v1.3.0-rc1
git push origin v1.3.0-rc1        # pushes the tag and its commit, not a branch
```

Then in **Actions → Release** for that tag:

- `macos-sign` → **Import the Developer ID certificate** prints
  `Signing as: Developer ID Application: … (TEAMID)`;
- **Sign, notarize and staple** shows `Submission …: Accepted` twice (app,
  then `.dmg`) and `source=Notarized Developer ID`;
- **Verify the signed .dmg** and **Check the signed app can start the sign-in
  runtime** pass;
- the release `v1.3.0-rc1` is marked **Pre-release**.

On your Mac, download `Blackboard-Sync-1.3.0-rc1.dmg` from the pre-release
page with Safari (so it gets quarantined like a student's download) and open
it: there must be no "cannot be verified" warning. The same checks
`install.sh` makes, on the mounted image:

```sh
APP="/Volumes/Blackboard Sync/Blackboard Sync.app"
codesign --verify --deep --strict --verbose=2 "$APP"
codesign -dv --verbose=2 "$APP" 2>&1 | grep -E "^Authority=Developer ID Application|^TeamIdentifier"
spctl --assess --type execute --verbose=2 "$APP"     # accepted, source=Notarized Developer ID
xcrun stapler validate "$APP"
```

Clean up afterwards. If the pre-release was published, delete it and the tag
on GitHub:

```sh
gh release delete v1.3.0-rc1 --cleanup-tag --yes -R UmutYLCN/blackboard-sync
```

If the run failed before the `release` job, there is no release: that command
fails with `release not found` and leaves the tag. Delete the tag on GitHub
instead:

```sh
git push origin :refs/tags/v1.3.0-rc1
```

Either way, then remove the local tag (so a later `git push --tags` cannot push
it again) and the branch:

```sh
git tag -d v1.3.0-rc1
git switch main && git branch -D signing-test
```

If notarization is rejected, the step prints Apple's log listing each file and
the reason. The Windows job runs for the test tag too; its installer stays
unsigned.

## Real releases

Nothing new: bump `__version__`, merge, push the `v<version>` tag (see
[DEVELOPMENT.md](DEVELOPMENT.md#building-the-app-and-releases)). With the
secrets set, the published `.dmg` is signed and notarized. After the first
signed release:

- `install.sh` refuses a signed app that fails any check; unsigned releases
  (all releases before this one) still install as before.
- Students who installed an unsigned version get the signed one through the
  updater as usual (download the `.dmg`, drag it over the old app). macOS may
  ask once more for access to the Documents folder, because the app's
  identity changed from ad-hoc to Developer ID; from then on the permission
  survives updates.

## Entitlements

The hardened runtime is required for notarization. Each exception is an
entitlement in `packaging/entitlements/`:

- **The app (`app.plist`): none.** Python, PyObjC (the menu bar app, the
  settings and sign-in windows) and WebKit run under the plain hardened
  runtime. Library validation stays on: every library in the bundle is signed
  by the same team, so `disable-library-validation` is not needed.
  Checked by signing the bundle with the hardened runtime (an Apple
  Development identity, so library validation applied) and running the sign-in
  self-test, the menu bar app and a CLI command.
- **Playwright's Node.js driver (`node.plist`): `com.apple.security.cs.allow-jit`.**
  V8 compiles JavaScript into `MAP_JIT` memory at run time, which the hardened
  runtime allows only with this entitlement. The official Node.js binary
  carries five more (`allow-unsigned-executable-memory`,
  `disable-executable-page-protection`, `allow-dyld-environment-variables`,
  `disable-library-validation` and `get-task-allow`); the driver runs without
  them, and Apple rejects `get-task-allow` for notarization.

The app is signed inside out rather than with `codesign --deep`, so the JIT
entitlement goes only to Node.

## If the certificate or a key leaks

1. Delete the leaked secrets in GitHub (Settings → Secrets and variables →
   Actions) so no release can use them.
2. Certificate: revoke it at
   <https://developer.apple.com/account/resources/certificates/list> (select it
   → **Revoke**). macOS then rejects software signed with it, which can include
   releases already published. To keep earlier releases opening, contact Apple
   Developer Support through <https://developer.apple.com/contact/> and ask for
   the revocation to take effect from the date of the leak.
3. API key: App Store Connect → **Users and Access → Integrations → App Store
   Connect API** → **Revoke** next to the key. App-specific password: revoke
   it at <https://account.apple.com>.
4. Create a new certificate/key (steps 2–5 above) and publish a new version.
   The Team ID does not change, so `install.sh` keeps working.

## Signing locally

With a Developer ID Application identity in your keychain:

```sh
./scripts/build-app.sh
./scripts/sign-macos.sh app "dist/Blackboard Sync.app" "Developer ID Application: Your Name (TEAMID)"
MACOS_NOTARY_KEY_PATH=~/AuthKey_<KEYID>.p8 MACOS_NOTARY_KEY_ID=<KEYID> MACOS_NOTARY_ISSUER_ID=<ISSUER> \
  ./scripts/notarize-macos.sh "dist/Blackboard Sync.app"
```

`scripts/sign-macos.sh app "dist/Blackboard Sync.app" -` signs ad-hoc with the
hardened runtime; such an app does not start (library validation needs a team
identity), so use it only to check the signing script itself.
