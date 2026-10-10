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
# Every thread's stack goes to windows-tray-faults.log every 10 s, printed on a failure.
$env:BBSYNC_STACK_DUMP = "10"
$log = Join-Path $dataDir "windows-tray.log"
$windowTitle = "Blackboard Sync"
. (Join-Path $PSScriptRoot "windows-gui-snapshot.ps1") -DataDir $dataDir
function Check($ok, $what) {
  if (-not $ok) { Show-AppSnapshot "FAILED: $what"; throw "FAILED: $what" } else { Write-Host "ok: $what" }
}
function Wait-Until([int]$Seconds, [scriptblock]$Condition) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) { if (& $Condition) { return $true }; Start-Sleep -Milliseconds 500 }
  return [bool](& $Condition)
}
function MainWindow { Get-AppWindows | Where-Object { $_.Visible -and $_.Title -eq $windowTitle } | Select-Object -First 1 }
function AnyWindow { Get-AppWindows | Where-Object { $_.Visible -and $_.Title -like "Blackboard Sync*" } | Select-Object -First 1 }
function TrayStarts { @(Select-String -Path $log -Pattern "Tray icon started" -ErrorAction SilentlyContinue).Count }

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
Check ($out -match "login runtime ok \(Playwright, WebView2\)") "the sign-in runtimes (Playwright driver, WebView2 window) load"

# The GUI itself: a fresh profile shows the main window (Başlangıç), in front.
$shown = Wait-Until 45 { (Test-Path $log) -and (MainWindow) }
Check ($null -ne (Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue)) "the installer started the app"
Check (Test-Path $log) "the app writes windows-tray.log"
Check $shown "the main window ($windowTitle) is shown"
Show-AppSnapshot "after the first start"
# Closed, the app stays in the tray; started again, the running copy shows it.
Close-AppWindow (MainWindow)
Check (Wait-Until 10 { -not (MainWindow) }) "the main window closes"
Check ($null -ne (Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue)) "the app keeps running in the tray"
Start-Process "$app\Blackboard Sync.exe"
Check (Wait-Until 20 { MainWindow }) "starting it again shows the running copy's window"
Check (Wait-Until 10 { @(Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue).Count -eq 1 }) "only one copy keeps running"
Check ((Get-Content $log -Raw) -match "Another copy is already running; asking it to show its window") "the second start was handed to the running copy"

# A profile left by an earlier install (saved settings): a start from the Start
# Menu shows the main window too, not only the tray icon.
Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Set-Content (Join-Path $dataDir "settings.json") '{"base_url": "https://blackboard.example.edu", "dest": "C:\\Okul", "check_updates": false}' -Encoding utf8
Start-Process "$app\Blackboard Sync.exe"
Check (Wait-Until 30 { MainWindow }) "with saved settings, starting the app shows its main window"
$starts = TrayStarts

# A later install (an update) replaces the running app and starts it again.
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty $runKey -Name BlackboardSync -Value "`"C:\old\Blackboard Sync.exe`"" -Force | Out-Null
Install
Check (Wait-Until 45 { (TrayStarts) -gt $starts }) "the app is running again after an update"
Start-Sleep -Seconds 3
Check ($null -ne (Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue)) "the updated app keeps running"
Check ($null -eq (AnyWindow)) "after a silent update it stays in the tray (no window)"
Check ((Get-ItemProperty $runKey).BlackboardSync -eq "`"$app\Blackboard Sync.exe`" --background") "start-at-login points at the installed exe, in the tray only"

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
