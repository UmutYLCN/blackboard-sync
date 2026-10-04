# What the Windows tray app is doing right now, for CI logs: whether it runs,
# its windows (title, visible, position), its data folder and log. Dot-source
# it for Get-AppWindows, or run it to print a snapshot.
param([string]$DataDir = $(if ($env:BBSYNC_DATA_DIR) { $env:BBSYNC_DATA_DIR } else { Join-Path $env:APPDATA "blackboard-sync" }))

if (-not ("BbsyncWindows" -as [type])) {
  Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class BbsyncWindows {
  delegate bool EnumProc(IntPtr hwnd, IntPtr lParam);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc proc, IntPtr lParam);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int max);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder text, int max);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public static List<string[]> List(uint[] pids) {
    var found = new List<string[]>();
    var wanted = new HashSet<uint>(pids);
    var front = GetForegroundWindow();
    EnumWindows((hwnd, l) => {
      uint pid; GetWindowThreadProcessId(hwnd, out pid);
      if (!wanted.Contains(pid)) return true;
      var title = new StringBuilder(512); GetWindowText(hwnd, title, title.Capacity);
      var cls = new StringBuilder(256); GetClassName(hwnd, cls, cls.Capacity);
      RECT r; GetWindowRect(hwnd, out r);
      found.Add(new[] { pid.ToString(), title.ToString(), cls.ToString(), IsWindowVisible(hwnd).ToString(),
                        (hwnd == front).ToString(), string.Format("{0},{1} {2}x{3}", r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top) });
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
}

function Get-AppWindows([string]$ProcessName = "Blackboard Sync") {
  $procs = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
  if (-not $procs) { return @() }
  [BbsyncWindows]::List([uint32[]]($procs | ForEach-Object { $_.Id })) | ForEach-Object {
    [pscustomobject]@{ Pid = $_[0]; Title = $_[1]; Class = $_[2]; Visible = $_[3] -eq "True"; Foreground = $_[4] -eq "True"; Rect = $_[5] }
  }
}

function Show-AppSnapshot([string]$Label, [string]$ProcessName = "Blackboard Sync", [string]$Dir = $DataDir) {
  Write-Host "===== $Label"
  $procs = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
  Write-Host "processes: $(($procs | ForEach-Object { "$($_.Id) $($_.Path)" }) -join '; ')"
  Get-AppWindows $ProcessName | Format-Table -AutoSize | Out-String -Width 250 | Write-Host
  Write-Host "data folder ${Dir}:"
  Get-ChildItem $Dir -Force -ErrorAction SilentlyContinue | Format-Table Name, Length, LastWriteTime -AutoSize | Out-String | Write-Host
  $log = Join-Path $Dir "windows-tray.log"
  if (Test-Path $log) { Write-Host "--- windows-tray.log"; Get-Content $log -Tail 200 | Write-Host } else { Write-Host "no windows-tray.log" }
}

if ($MyInvocation.InvocationName -ne ".") { Show-AppSnapshot "snapshot" }
