# Build the Windows installer, dist\Blackboard-Sync-<version>-Setup.exe.
# Run from a Windows machine with Python 3.12 and Inno Setup 6 (iscc) on PATH.
# Freezes the tray app with PyInstaller (freeze-windows.ps1) and wraps it in a
# per-user installer.
# The installer is unsigned: Windows SmartScreen asks once ("More info > Run anyway").
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

& (Join-Path $PSScriptRoot "freeze-windows.ps1")
$version = python -c "import blackboard_sync; print(blackboard_sync.__version__)"
iscc /Qp "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Built dist\Blackboard-Sync-$version-Setup.exe"
