# TEMPORARY reproduction of "installed, launched, nothing opened" (removed before merge).
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
. .\scripts\windows-gui-snapshot.ps1
$setup = (Get-ChildItem dist\Blackboard-Sync-*-Setup.exe | Select-Object -First 1).FullName
$app = Join-Path $env:LOCALAPPDATA "Programs\Blackboard Sync"
$exe = Join-Path $app "Blackboard Sync.exe"
$real = Join-Path $env:APPDATA "blackboard-sync"
Remove-Item Env:\BBSYNC_DATA_DIR -ErrorAction SilentlyContinue
$env:BBSYNC_STACK_DUMP = "15"
function StopApp { Get-Process -Name "Blackboard Sync", pythonw -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2 }

Write-Host "session: $([Environment]::UserInteractive) user=$env:USERNAME"
Get-Process explorer -ErrorAction SilentlyContinue | Format-Table Id, SessionId | Out-String | Write-Host
Write-Host "APPDATA before install: $(Test-Path $real)"

# A: fresh profile, silent install starts the app (default %APPDATA% data folder).
$p = Start-Process $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
$p.WaitForExit()
Start-Sleep 25
Show-AppSnapshot "A fresh profile, started by the silent installer" -Dir $real
Get-ChildItem $env:LOCALAPPDATA -ErrorAction SilentlyContinue | Where-Object Name -match "blackboard|Programs" | Format-Table FullName | Out-String | Write-Host

# E: a second launch while it runs (Start Menu click again).
Start-Process $exe
Start-Sleep 8
Show-AppSnapshot "E second launch while running" -Dir $real

# B: a profile left by an earlier run: saved settings and an expired session.
StopApp
Set-Content (Join-Path $real "settings.json") '{"base_url": "https://blackboard.istun.edu.tr", "dest": "C:\\Okul", "check_updates": true}' -Encoding utf8
Set-Content (Join-Path $real "session.json") '{"base_url": "https://blackboard.istun.edu.tr", "cookies": [{"name": "s", "value": "x", "domain": "blackboard.istun.edu.tr", "expires": 1}]}' -Encoding utf8
Start-Process $exe
Start-Sleep 20
Show-AppSnapshot "B earlier profile (saved settings, expired session), started from the Start Menu" -Dir $real

# D: the proven path, from source with pythonw and a fresh data folder.
StopApp
$src = Join-Path $env:TEMP "bbsync-src-data"
$env:BBSYNC_DATA_DIR = $src
$pythonw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
Start-Process $pythonw -ArgumentList "-m", "blackboard_sync.windows"
Start-Sleep 25
Show-AppSnapshot "D from source with pythonw, fresh data folder" -ProcessName pythonw -Dir $src
StopApp
Remove-Item Env:\BBSYNC_DATA_DIR
