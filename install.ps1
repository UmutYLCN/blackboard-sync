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

    $base = "https://github.com/$repo/releases/latest/download"
    Write-Host '==> Son sürüm aranıyor...'
    $sumsFile = Join-Path $tmp 'SHA256SUMS.txt'
    Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS.txt" -OutFile $sumsFile
    $expected = $null
    $name = $null
    foreach ($line in Get-Content $sumsFile) {
      $parts = $line.Trim() -split '\s+', 2
      if ($parts.Count -eq 2 -and $parts[1].TrimStart('*') -like 'Blackboard-Sync-*-Setup.exe') { $expected = $parts[0]; $name = $parts[1].TrimStart('*'); break }
    }
    if (-not $name) { throw 'Son sürümde Setup.exe bulunamadı.' }

    Write-Host "==> $name indiriliyor..."
    $exe = Join-Path $tmp $name
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$name" -OutFile $exe

    Write-Host '==> Sağlama toplamı doğrulanıyor...'
    $actual = (Get-FileHash -Algorithm SHA256 -Path $exe).Hash
    if ($actual -ne $expected) { throw 'Sağlama toplamı uyuşmuyor, kurulum iptal edildi.' }
    Write-Host '    Doğrulandı.'

    Write-Host '==> Kuruluyor (uygulama kurulumdan sonra kendiliğinden açılır)...'
    $p = Start-Process -FilePath $exe -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -PassThru
    # Wait for the installer only: -Wait would also wait for the app it starts.
    $null = $p.Handle
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw "Kurulum başarısız oldu (çıkış kodu $($p.ExitCode))." }
    Write-Host 'Kurulum tamamlandı.'
  } catch {
    Write-Host "Hata: $($_.Exception.Message)" -ForegroundColor Red
  } finally {
    Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
  }
}
