# Dot-source for Find-SdkTool: a Windows 10/11 SDK tool (makeappx.exe,
# signtool.exe) from PATH or the newest SDK installed under Windows Kits.
function Find-SdkTool([string]$Name) {
  $onPath = Get-Command $Name -ErrorAction SilentlyContinue
  if ($onPath) { return $onPath.Source }
  $bin = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
  $tool = Get-ChildItem $bin -Directory -Filter "10.*" -ErrorAction SilentlyContinue |
    Sort-Object { [version]$_.Name } -Descending |
    ForEach-Object { Join-Path $_.FullName "x64\$Name" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
  if (-not $tool) { throw "$Name not found: install the Windows 10/11 SDK" }
  return $tool
}
