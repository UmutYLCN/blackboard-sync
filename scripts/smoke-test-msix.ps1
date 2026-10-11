# Sideload dist\Blackboard-Sync-*-x64.msix as docs/MSIX.md describes (a copy
# signed with a throwaway self-signed certificate), check the installed app,
# then remove the package and the certificate. Meant for CI: it trusts the
# certificate machine-wide, which needs an administrator. The .msix in dist
# stays unsigned.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
. (Join-Path $PSScriptRoot "windows-sdk.ps1")
. (Join-Path $PSScriptRoot "windows-gui-snapshot.ps1")

$msix = (Get-ChildItem dist\Blackboard-Sync-*-x64.msix | Select-Object -First 1).FullName
[xml]$manifest = Get-Content build\msix\AppxManifest.xml -Encoding utf8
$identity = $manifest.Package.Identity
$appId = $manifest.Package.Applications.Application.Id
$work = Join-Path (Get-Location) "build\msix-test"
New-Item -ItemType Directory -Force $work | Out-Null
$windowTitle = "Blackboard Sync"
$package = $null

function Check($ok, $what) {
  if (-not $ok) {
    if ($package) {
      # A packaged app's writes to %APPDATA% land in the package's own folder.
      Show-AppSnapshot "FAILED: $what" -Dir (Join-Path $env:LOCALAPPDATA "Packages\$($package.PackageFamilyName)\LocalCache\Roaming\blackboard-sync")
    }
    throw "FAILED: $what"
  }
  Write-Host "ok: $what"
}
function Wait-Until([int]$Seconds, [scriptblock]$Condition) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) { if (& $Condition) { return $true }; Start-Sleep -Milliseconds 500 }
  return [bool](& $Condition)
}
function MainWindow { Get-AppWindows | Where-Object { $_.Visible -and $_.Title -eq $windowTitle } | Select-Object -First 1 }
# Run the CLI twin with one argument in the package's context; its output.
function Invoke-InPackage([string]$Argument) {
  $name = $Argument.TrimStart("-")
  $result = Join-Path $work "$name.txt"
  $script = Join-Path $work "$name.ps1"
  Remove-Item $result -ErrorAction SilentlyContinue
  Set-Content $script "& '$($package.InstallLocation)\blackboard-sync-cli.exe' $Argument *> '$result'; Add-Content '$result' `"exit=`$LASTEXITCODE`""
  Invoke-CommandInDesktopPackage -PackageFamilyName $package.PackageFamilyName -AppId $appId `
    -Command "powershell.exe" -Args "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" | Out-Null
  $finished = Wait-Until 120 { (Test-Path $result) -and ((Get-Content $result -Raw) -match "exit=") }
  $text = if (Test-Path $result) { Get-Content $result -Raw } else { "" }
  Write-Host $text
  Check $finished "blackboard-sync-cli $Argument finished in the package"
  Check ($text -match "exit=0") "blackboard-sync-cli $Argument exit code"
  return $text
}

# The certificate's subject must be the manifest's Publisher.
$cert = New-SelfSignedCertificate -Type Custom -Subject $identity.Publisher -KeyUsage DigitalSignature `
  -FriendlyName "Blackboard Sync MSIX test" -CertStoreLocation Cert:\CurrentUser\My `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
$cer = Join-Path $work "test.cer"
Export-Certificate -Cert $cert -FilePath $cer | Out-Null
Import-Certificate -FilePath $cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null
try {
  $signed = Join-Path $work "Blackboard-Sync-test.msix"
  Copy-Item $msix $signed
  & (Find-SdkTool signtool.exe) sign /q /fd SHA256 /sha1 $cert.Thumbprint /s My $signed
  Check ($LASTEXITCODE -eq 0) "signed a test copy"

  Add-AppxPackage -Path $signed
  $package = Get-AppxPackage -Name $identity.Name
  Check ($null -ne $package) "package installed"
  Check ($package.Version -eq $identity.Version) "package version $($identity.Version)"
  $app = $package.InstallLocation
  Check (Test-Path "$app\Blackboard Sync.exe") "app in the package"
  Check (Test-Path "$app\blackboard-sync-cli.exe") "CLI twin in the package"

  # The self-tests of scripts/smoke-test-windows.ps1 and --check-package (identity
  # and the startup task). Only a process in the package's context may run the
  # package's programs, so they run there, writing to a file.
  $out = Invoke-InPackage "--check-login-runtime"
  Check ($out -match "login runtime ok \(Playwright, WebView2\)") "the sign-in runtimes (Playwright driver, WebView2 window) load"
  $out = Invoke-InPackage "--check-package"
  Check ($out -match "package ok \(.+\)") "package identity and the startup task work"
  Check ($out -match "updater off") "the packaged self-updater is off"
  Check ($out.Contains("toast identity $($package.PackageFamilyName)!$appId")) "the toast notifier uses the packaged app's AUMID"

  # Started from the Start menu (an AppsFolder activation), the packaged app shows its main window.
  Start-Process "shell:AppsFolder\$($package.PackageFamilyName)!$appId"
  Check (Wait-Until 60 { MainWindow }) "the packaged app starts and shows its main window"
  Show-AppSnapshot "packaged app running" -Dir (Join-Path $env:LOCALAPPDATA "Packages\$($package.PackageFamilyName)\LocalCache\Roaming\blackboard-sync")
  $runningPid = (MainWindow).Pid
  Close-AppWindow (MainWindow)
  Check (Wait-Until 30 { -not (MainWindow) }) "closing the packaged window hides it"
  Start-Process "blackboard-sync-store://open"
  Check (Wait-Until 30 { MainWindow }) "the toast protocol shows the running packaged app"
  Check ((MainWindow).Pid -eq $runningPid) "the toast protocol reuses the running instance"
  Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  Start-Process "blackboard-sync-store://open"
  Check (Wait-Until 60 { MainWindow }) "the toast protocol starts the packaged app when closed"
  Get-Process -Name "Blackboard Sync" -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2

  Remove-AppxPackage -Package $package.PackageFullName
  Check ($null -eq (Get-AppxPackage -Name $identity.Name)) "package removed"
} finally {
  Get-Process -Name "Blackboard Sync", "blackboard-sync-cli" -ErrorAction SilentlyContinue | Stop-Process -Force
  Remove-Item "Cert:\LocalMachine\TrustedPeople\$($cert.Thumbprint)", "Cert:\CurrentUser\My\$($cert.Thumbprint)" -ErrorAction SilentlyContinue
}
