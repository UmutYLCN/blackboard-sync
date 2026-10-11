# Freeze the Windows tray app with PyInstaller into dist\Blackboard Sync (it
# bundles its own Python, so the result needs nothing installed). Shared by
# build-windows.ps1 (Inno Setup installer) and build-msix.ps1 (Store package).
# Run from a Windows machine with Python 3.12 on PATH.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --quiet -r requirements.lock -r requirements-build.txt
python -m pip install --quiet --no-deps -e .
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean packaging\blackboard_sync_windows.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
