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

Two hidden self-tests check an installed package; CI runs both:

- `blackboard-sync-cli.exe --check-login-runtime` (from the package's install
  folder, `(Get-AppxPackage <name>).InstallLocation`): Playwright and WebView2 load.
- `blackboard-sync-cli.exe --check-package`, run inside the package's context
  (`Invoke-CommandInDesktopPackage`): the process has package identity, and the
  startup task can be turned on and off (it is left as it was).

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

## Not done yet

The packaged build still behaves like the installer build otherwise. Before a
Store submission: turn off the self-updater and the app's own uninstall path in
the package, give update toasts the package identity, and test the package end
to end on a real Windows PC. Note also that in a package, new files the app
writes under `%APPDATA%` go to the package's own folder
(`%LOCALAPPDATA%\Packages\<family name>\LocalCache\Roaming`).
