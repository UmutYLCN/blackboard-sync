# Install dist\Blackboard-Sync-*-Setup.exe silently (as the updater does), check
# the installed app, then uninstall. Meant for CI; it changes the current user's
# profile (installs into %LOCALAPPDATA%\Programs\Blackboard Sync).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$setup = (Get-ChildItem dist\Blackboard-Sync-*-Setup.exe | Select-Object -First 1).FullName
$version = python -c "import blackboard_sync; print(blackboard_sync.__version__)"
$app = Join-Path $env:LOCALAPPDATA "Programs\Blackboard Sync"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$dataDir = Join-Path $env:TEMP "bbsync-smoke-data"
$env:BBSYNC_DATA_DIR = $dataDir
function Check($ok, $what) { if (-not $ok) { throw "FAILED: $what" } else { Write-Host "ok: $what" } }

function Install {
  $p = Start-Process $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$env:TEMP\bbsync-setup.log" -PassThru
  # Not -Wait: that also waits for the app the installer starts.
  $p.WaitForExit()
  Check ($p.ExitCode -eq 0) "installer exit code $($p.ExitCode)"
}

Install
Check (Test-Path "$app\Blackboard Sync.exe") "app installed per-user"
Check (Test-Path "$app\blackboard-sync-cli.exe") "CLI twin installed"
Check (Test-Path (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Blackboard Sync.lnk")) "Start Menu shortcut"

$out = (& "$app\blackboard-sync-cli.exe" --version) -join "`n"
Write-Host $out
Check ($out -match [regex]::Escape($version)) "CLI answers --version $version"

$out = (& "$app\blackboard-sync-cli.exe" --check-login-runtime 2>&1) -join "`n"
Write-Host $out
Check ($out -match "login runtime ok") "the sign-in runtime (Playwright driver) starts"

Start-Sleep -Seconds 5
Check ($null -ne (Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue)) "the installer started the app"

# A later install (an update) replaces the running app and starts it again.
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty $runKey -Name BlackboardSync -Value "`"C:\old\Blackboard Sync.exe`"" -Force | Out-Null
Install
Start-Sleep -Seconds 5
Check ($null -ne (Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue)) "the app is running again after an update"
Check ((Get-ItemProperty $runKey).BlackboardSync -eq "`"$app\Blackboard Sync.exe`"") "start-at-login points at the installed exe"

# The user's data must survive an uninstall.
New-Item -ItemType Directory -Force $dataDir | Out-Null
Set-Content "$dataDir\keep.txt" "data"
$uninstaller = Get-ChildItem "$app\unins*.exe" | Select-Object -First 1
$p = Start-Process $uninstaller.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
$p.WaitForExit()
Check ($p.ExitCode -eq 0) "uninstaller exit code $($p.ExitCode)"
Start-Sleep -Seconds 2
Check (-not (Test-Path "$app\Blackboard Sync.exe")) "app removed"
Check ($null -eq (Get-ItemProperty $runKey -Name BlackboardSync -ErrorAction SilentlyContinue)) "start-at-login removed"
Check ($null -eq (Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue)) "app no longer running"
Check (Test-Path "$dataDir\keep.txt") "user data kept"
