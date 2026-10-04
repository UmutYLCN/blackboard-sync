; Inno Setup script for the Windows installer. Build with scripts/build-windows.ps1,
; which passes /DAppVersion=<version> and the path of the frozen app.
; Per-user install: no administrator rights, nothing outside the user's profile.
; The user's downloaded files and %APPDATA% data are never touched, also on uninstall.

#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Blackboard Sync"
#endif

#define AppName "Blackboard Sync"
#define AppExe "Blackboard Sync.exe"

[Setup]
AppId={{6E2B3D0A-5B8C-4C57-9F43-1A7D2C0B8E91}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Umut Yalcin
AppPublisherURL=https://github.com/UmutYLCN/blackboard-sync
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Blackboard-Sync-{#AppVersion}-Setup
SetupIconFile=..\build\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; The running tray app is closed explicitly (see CloseRunningApp); the Restart
; Manager would not find a window to ask.
CloseApplications=no
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Registry]
; The app writes its start-at-login value itself; the uninstaller removes it.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "BlackboardSync"; Flags: dontcreatekey uninsdeletevalue
; Notification-click handler the app registers.
Root: HKCU; Subkey: "Software\Classes\blackboard-sync"; Flags: dontcreatekey uninsdeletekey
; An upgrade or reinstall keeps a start-at-login the user already chose, pointing at this exe.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "BlackboardSync"; ValueType: string; ValueData: """{app}\{#AppExe}"""; Check: RunValueExists

[Run]
; Also runs after a silent (updater) install, which is how the app restarts.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
function RunValueExists: Boolean;
begin
  Result := RegValueExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BlackboardSync');
end;

procedure StopApp;
var
  Code: Integer;
begin
  // Both programs of the app; ignore "not running".
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "blackboard-sync-cli.exe"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp;
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopApp;
end;
