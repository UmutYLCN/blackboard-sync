# Microsoft Store package (MSIX)

The Windows app can also ship as an MSIX package for the Microsoft Store. The
Store signs the packages it publishes, so the build needs no code-signing
certificate. The Inno Setup installer (`scripts/build-windows.ps1`) and the
GitHub release downloads are unchanged; the MSIX package is a second way to
ship the same PyInstaller build.

It is a full-trust desktop package (`Windows.FullTrustApplication`, capabilities
`runFullTrust` and `internetClient`): the frozen app runs as it does when
installed by Setup, but with package identity.

## Files

| File | What it is |
| --- | --- |
| `packaging/msix/identity.toml` | Package identity: the values Partner Center assigns (see below) |
| `packaging/msix/AppxManifest.xml.in` | The manifest template |
| `packaging/msix/make_layout.py` | Copies the PyInstaller build, writes the manifest and draws the logos from `assets/icon/logo.png` |
| `scripts/build-msix.ps1` | Freezes the app and runs `makeappx pack` |
| `scripts/smoke-test-msix.ps1` | CI: sideloads a test-signed copy and checks it |

The package version is the app version with a fourth part of 0 (`1.5.1` →
`1.5.1.0`); the Store reserves the fourth part. A pre-release suffix is dropped
(`1.6.0rc1` → `1.6.0.0`).

## Build

On Windows with Python 3.12 and the Windows 10/11 SDK (for `makeappx.exe`):

```powershell
./scripts/build-msix.ps1
```

This writes `dist\Blackboard-Sync-<version>-x64.msix`, unsigned. CI builds the
same file on every pull request and push to `main` (the `msix` job in
`.github/workflows/ci.yml`) and keeps it as the `msix` workflow artifact. It is
not attached to releases and nothing is submitted to the Store.

## Sideload test on your own PC

Windows installs only signed packages, so sign a copy with a self-signed test
certificate whose subject is the manifest's `Publisher`. In an administrator
PowerShell, from the repository:

```powershell
$publisher = ([xml](Get-Content build\msix\AppxManifest.xml)).Package.Identity.Publisher
$cert = New-SelfSignedCertificate -Type Custom -Subject $publisher -KeyUsage DigitalSignature `
  -FriendlyName "Blackboard Sync MSIX test" -CertStoreLocation Cert:\CurrentUser\My `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
Export-Certificate -Cert $cert -FilePath "$env:TEMP\bbsync-test.cer"
Import-Certificate -FilePath "$env:TEMP\bbsync-test.cer" -CertStoreLocation Cert:\LocalMachine\TrustedPeople

$msix = (Get-ChildItem dist\Blackboard-Sync-*-x64.msix).FullName
Copy-Item $msix "$env:TEMP\bbsync-test.msix"
signtool sign /fd SHA256 /sha1 $cert.Thumbprint "$env:TEMP\bbsync-test.msix"
Add-AppxPackage "$env:TEMP\bbsync-test.msix"
```

`signtool.exe` is in the Windows SDK (`C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64`).
Start **Blackboard Sync** from the Start menu. To remove it again:

```powershell
Get-AppxPackage PLACEHOLDER.BlackboardSync | Remove-AppxPackage
Remove-Item "Cert:\LocalMachine\TrustedPeople\$($cert.Thumbprint)", "Cert:\CurrentUser\My\$($cert.Thumbprint)"
```

(Use the package name from `identity.toml` once the placeholder is replaced.)
Uninstall a Setup-installed copy first, so that two copies do not both start at
login.

Two hidden self-tests check an installed package; CI runs both. Windows lets
only a process in the package's context start the package's programs, so run
them through `Invoke-CommandInDesktopPackage -PackageFamilyName <family name>
-AppId BlackboardSync -Command <exe> -Args <args>` (as
`scripts/smoke-test-msix.ps1` does, writing the output to a file):

- `blackboard-sync-cli.exe --check-login-runtime`: Playwright and WebView2 load.
- `blackboard-sync-cli.exe --check-package`: the process has package identity,
  the startup task can be turned on and off (it is left as it was), the
  self-updater is off, and a real toast notifier can be created with the GUI
  app's package AUMID. It does not display a toast. The smoke script also checks
  protocol activation with the app hidden in the tray and with the app closed.

## Start at login in the package

A packaged app cannot use the `HKCU\...\Run` value the installer build writes.
The manifest declares a startup task instead (`TaskId` `BlackboardSyncStartup`,
`Enabled="false"`), and `src/blackboard_sync/windows/autostart.py` turns it on
and off through the WinRT `StartupTask` API whenever the process has package
identity (`windows/package.py`, `is_packaged()`). Without package identity
(Setup install, running from source) it keeps using the Run value.

- Default: off, as in the installer build. The settings' "start at login"
  checkbox (on by default at first launch) turns it on when the user saves.
- The user also controls it in Task Manager > Startup apps and Settings > Apps >
  Startup. Once the user turns it off there, the app cannot turn it back on: the
  checkbox then shows it off and saving logs a warning.
- Windows starts the task without arguments, so there is no `--background`.
  Instead the app asks Windows how it was started
  (`AppInstance.GetActivatedEventArgs`, Windows 10 1809 or later, which is the
  package's minimum version). Started by the startup task, it stays in the tray
  as the installer build does with `--background`; started from the Start menu,
  it shows its main window.

## Placeholders to replace from Partner Center

After reserving the app name in Partner Center, copy these from **Product
management > Product identity** into `packaging/msix/identity.toml`:

| `identity.toml` | Partner Center | Placeholder now |
| --- | --- | --- |
| `name` | Package/Identity/Name | `PLACEHOLDER.BlackboardSync` |
| `publisher` | Package/Identity/Publisher | `CN=PLACEHOLDER-PUBLISHER` |
| `publisher_display_name` | Package/Properties/PublisherDisplayName | `PLACEHOLDER Publisher` |
| `display_name` | the reserved app name | `Blackboard Sync` (keep if that is the reserved name) |

`make_layout.py` prints a note for every value that is still a placeholder.

## Store-owned updates and removal

When `windows/package.is_packaged()` is true, the app never checks GitHub,
downloads an installer or runs a Setup EXE. Scheduled and manual update actions
are guarded, including stale saved releases and clicks on old update toasts.
The settings omit the automatic-check checkbox and update buttons, and show
"Güncellemeler Microsoft Store üzerinden yüklenir." The tray omits update actions.

The in-app uninstall button is replaced with a note pointing to **Windows
Settings > Apps**. The uninstall backend (including CLI `uninstall` and
`--delete-course-files`) returns that guidance before changing any app data,
startup settings or course files. **Hesaptan çıkış yap** still clears the session
normally. The unpackaged Setup build retains its updater and Inno uninstaller;
macOS behavior is unchanged.

## Notifications and activation

The PowerShell child process still sends toasts, with an explicit identity:
`<package family name>!BlackboardSync`. The family comes from Windows, so replacing
Partner Center placeholders needs no runtime code change. The app name and icon
come from the package manifest. Packaged toast clicks open the app through
`blackboard-sync-store://open`; this scheme is declared by a `uap3:Protocol`
manifest extension with the fixed `--store-notification` argument. Clicks show
the running window through the existing single-instance request mechanism or
start the packaged app if it is closed. They do not open course folders directly.

The packaged app skips HKCU protocol registration and legacy Run-key upgrades;
start-at-login uses only the manifest's StartupTask. The Setup build keeps its
`Blackboard Sync` notifier, file/folder click targets and
`blackboard-sync://update` registration. See Microsoft's
[desktop packaging extensions](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/desktop-to-uwp-extensions)
for protocol activation.

## Data when moving from Setup to Store

The Store package deliberately starts with fresh settings, session, browser
profiles and sync state. Its default data directory is explicitly
`%LOCALAPPDATA%\Packages\<family name>\LocalCache\Roaming\blackboard-sync`.
No migration or deletion of the Setup copy's `%APPDATA%\blackboard-sync` is
performed. Using an explicit package-private path avoids mixed state and locks:
[Windows AppData virtualization](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes)
can fall back to reading existing unpackaged files and, on Windows 1903 or later,
modify those files directly rather than redirecting them.

After switching, enter the school address, sign in again and select the previous
download folder if it differs from the default Documents/University. The data
location change never moves or deletes downloaded course files. The first sync
rebuilds tracking state; it may download content again. Uninstalling the package
lets Windows remove its private app data; course files remain outside the package.
Advanced `BBSYNC_DATA_DIR` / `--data-dir` overrides still select the requested
directory; the separation above describes the default. Stop the Setup copy and
disable its start-at-login before running the package against the same course
folder, since the two installs have separate locks. If removing the Setup copy
through its in-app uninstaller, leave its course-file deletion checkbox off.

## Manual Windows verification still required

CI creates the real notifier without showing a toast and exercises the manifest
protocol. A maintainer must still test a signed sideloaded package on a real
Windows 10/11 PC before submission:

1. Install using the test-certificate instructions above and run both hidden
   self-tests in package context (or `scripts/smoke-test-msix.ps1`). Confirm
   `--check-package` reports `updater off` and the expected `toast identity`.
2. In General settings confirm the Store update/removal notes, no updater or
   uninstall controls, and a working account sign-out action. Check start-at-login
   on/off and the Task Manager override as described above.
3. Sign in and sync a course with new content. Confirm the toast has the package's
   app name/icon. Click it with the window hidden, then quit and click a retained
   toast: both should show the packaged app. Direct protocol activation can also
   be tested with `Start-Process 'blackboard-sync-store://open'`.
4. With an existing Setup data directory, confirm the Store copy asks for fresh
   settings/sign-in, writes only its private data by default, and leaves the
   old session/state and downloaded files intact. Test Windows Settings removal;
   course files must remain. Verify the Setup build still checks GitHub, handles
   update/folder toasts and runs its own uninstaller normally.

Store submission, production signing and Partner Center identity replacement
remain separate steps.
