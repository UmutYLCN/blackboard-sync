# One-line installer for Windows (PowerShell 5.1+, no admin, no execution-policy change):
#   irm https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.ps1 | iex
# Downloads the latest release, verifies its SHA-256 and runs the per-user installer silently.
& {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  $repo = 'UmutYLCN/blackboard-sync'
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ('blackboard-sync-' + [guid]::NewGuid().ToString('N'))
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $tmp | Out-Null

    Write-Host '==> Son sürüm aranıyor...'
    $release = Invoke-RestMethod -UseBasicParsing -Headers @{ Accept = 'application/vnd.github+json' } -Uri "https://api.github.com/repos/$repo/releases/latest"
    $setup = $release.assets | Where-Object { $_.name -like '*-Setup.exe' } | Select-Object -First 1
    $sums = $release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if (-not $setup -or -not $sums) { throw 'Son sürümde Setup.exe veya SHA256SUMS.txt bulunamadı.' }

    Write-Host "==> $($setup.name) indiriliyor..."
    $exe = Join-Path $tmp $setup.name
    Invoke-WebRequest -UseBasicParsing -Uri $setup.browser_download_url -OutFile $exe
    $sumsFile = Join-Path $tmp 'SHA256SUMS.txt'
    Invoke-WebRequest -UseBasicParsing -Uri $sums.browser_download_url -OutFile $sumsFile

    Write-Host '==> Sağlama toplamı doğrulanıyor...'
    $expected = $null
    foreach ($line in Get-Content $sumsFile) {
      $parts = $line.Trim() -split '\s+', 2
      if ($parts.Count -eq 2 -and $parts[1].TrimStart('*') -eq $setup.name) { $expected = $parts[0]; break }
    }
    if (-not $expected) { throw "SHA256SUMS.txt içinde $($setup.name) bulunamadı." }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $exe).Hash
    if ($actual -ne $expected) { throw 'Sağlama toplamı uyuşmuyor, kurulum iptal edildi.' }
    Write-Host '    Doğrulandı.'

    Write-Host '==> Kuruluyor (uygulama kurulumdan sonra kendiliğinden açılır)...'
    $p = Start-Process -FilePath $exe -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Kurulum başarısız oldu (çıkış kodu $($p.ExitCode))." }
    Write-Host 'Kurulum tamamlandı.'
  } catch {
    Write-Host "Hata: $($_.Exception.Message)" -ForegroundColor Red
  } finally {
    Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
  }
}
