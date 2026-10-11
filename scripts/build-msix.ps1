# Build the Microsoft Store package, dist\Blackboard-Sync-<version>-x64.msix.
# Run from a Windows machine with Python 3.12 and the Windows 10/11 SDK
# (makeappx.exe). Freezes the tray app (freeze-windows.ps1), lays out the
# package (packaging\msix\make_layout.py) and packs it.
# The package is unsigned: the Store signs what it publishes. To install it
# yourself, sign a copy with a test certificate (docs/MSIX.md).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
. (Join-Path $PSScriptRoot "windows-sdk.ps1")

& (Join-Path $PSScriptRoot "freeze-windows.ps1")
$version = python -c "import blackboard_sync; print(blackboard_sync.__version__)"
python packaging\msix\make_layout.py "dist\Blackboard Sync" build\msix
if ($LASTEXITCODE -ne 0) { throw "MSIX layout failed" }
$msix = "dist\Blackboard-Sync-$version-x64.msix"
& (Find-SdkTool makeappx.exe) pack /o /d build\msix /p $msix
if ($LASTEXITCODE -ne 0) { throw "makeappx failed" }
Write-Host "Built $msix"
