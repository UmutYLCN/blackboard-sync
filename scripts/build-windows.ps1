# Build the Windows installer, dist\Blackboard-Sync-<version>-Setup.exe.
# Run from a Windows machine with Python 3.12 and Inno Setup 6 (iscc) on PATH.
# Freezes the tray app with PyInstaller (it bundles its own Python, so the
# result needs nothing installed) and wraps it in a per-user installer.
# The installer is unsigned: Windows SmartScreen asks once ("Ek bilgi > Yine de çalıştır").
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --quiet -r requirements.lock -r requirements-build.txt
python -m pip install --quiet --no-deps -e .
$version = python -c "import blackboard_sync; print(blackboard_sync.__version__)"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python packaging\make_icon.py build\app.ico
python -m PyInstaller --noconfirm --clean packaging\blackboard_sync_windows.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
iscc /Qp "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Built dist\Blackboard-Sync-$version-Setup.exe"
