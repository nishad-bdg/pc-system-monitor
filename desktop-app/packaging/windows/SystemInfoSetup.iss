; Inno Setup 6 script — System Info Windows installer
; Prerequisites:
;   1. Build exe:  packaging\windows\build.ps1
;   2. Install Inno Setup 6
;   3. Open this file and compile (or: iscc SystemInfoSetup.iss)
;
; The installer:
;   - Copies system-info.exe
;   - Asks for API URL, API key, optional PC name + update manifest URL
;   - Writes %APPDATA%\system-info\config.env
;   - Creates Task Scheduler job SystemInfoReport every hour
;   - Creates Task Scheduler job SystemInfoHeartbeat every 5 minutes (online status)

#define MyAppName "System Info Reporter"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "RGM"
#define MyAppExeName "system-info.exe"

[Setup]
AppId={{A7C3E9F2-4B1D-4F8A-9C2E-SystemInfoWin01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\SystemInfo
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=SystemInfoSetup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Prefer one-file build output
Source: "..\..\dist\system-info.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release-manifest.example.json"; DestDir: "{app}"; DestName: "release-manifest.example.json"; Flags: ignoreversion

[Icons]
Name: "{group}\Run report now"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'API configuration',
    'The reporter needs your API endpoint and key.',
    'These values are stored in %APPDATA%\system-info\config.env and used by the scheduled task.');
  ConfigPage.Add('API URL:', False);
  ConfigPage.Add('API key (sk-...):', False);
  ConfigPage.Add('PC name (Windows only, optional):', False);
  ConfigPage.Add('Update manifest URL (optional, pre-filled):', False);
  ConfigPage.Values[0] := 'https://your-api.example.com';
  ConfigPage.Values[1] := '';
  ConfigPage.Values[2] := '';
  {
    Default to the repo's "latest" release manifest so installed PCs auto-update
    after any new v* release tag. "releases/latest" redirects to the newest tag.
  }
  ConfigPage.Values[3] := 'https://github.com/nishad-bdg/pc-system-monitor/releases/latest/download/release-manifest.json';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
  begin
    if Trim(ConfigPage.Values[0]) = '' then
    begin
      MsgBox('API URL is required.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    if Trim(ConfigPage.Values[1]) = '' then
    begin
      MsgBox('API key is required.', mbError, MB_OK);
      Result := False;
      exit;
    end;
  end;
end;

procedure WriteConfigFile;
var
  Dir, Path, Content: string;
begin
  Dir := ExpandConstant('{userappdata}\system-info');
  ForceDirectories(Dir);
  Path := Dir + '\config.env';
  Content :=
    'SYSTEM_INFO_API_URL=' + Trim(ConfigPage.Values[0]) + #13#10 +
    'SYSTEM_INFO_API_KEY=' + Trim(ConfigPage.Values[1]) + #13#10 +
    'SYSTEM_INFO_PC_NAME=' + Trim(ConfigPage.Values[2]) + #13#10 +
    'SYSTEM_INFO_UPDATE_URL=' + Trim(ConfigPage.Values[3]) + #13#10;
  SaveStringToFile(Path, Content, False);
end;

procedure CreateScheduledTask;
var
  ResultCode: Integer;
  ExePath, ReportArgs: string;
begin
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  { Full report every hour, start 08:00, runs only while this user is logged on }
  ReportArgs :=
    '/Create /F /TN "SystemInfoReport" /SC HOURLY /ST 08:00 /IT ' +
    '/TR "\"' + ExePath + '\"" ' +
    '/RL LIMITED';
  Exec('schtasks.exe', ReportArgs, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode <> 0 then
  begin
    MsgBox(
      'Could not create the scheduled task (SystemInfoReport).' + #13#10 +
      'schtasks exit code: ' + IntToStr(ResultCode) + #13#10 +
      'Run this manually as this user:' + #13#10 +
      'schtasks /Create /F /TN SystemInfoReport /SC HOURLY /ST 08:00 /IT ' +
      '/TR "\"' + ExePath + '\""' + #13#10 +
      'The installer will continue, but reports will not run automatically.',
      mbError, MB_OK);
  end;
end;

{ Heartbeat: keep the PC marked "online" between hourly reports AND flush new
  print jobs to the API (the --heartbeat run also syncs print jobs, so print
  activity shows in the dashboard within ~5 minutes).
  Runs every 5 minutes (only while the user is logged on). }
procedure CreateHeartbeatTask;
var
  ResultCode: Integer;
  ExePath, BeatArgs: string;
begin
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  BeatArgs :=
    '/Create /F /TN "SystemInfoHeartbeat" /SC MINUTE /MO 5 /IT ' +
    '/TR "\"' + ExePath + '\" --heartbeat" ' +
    '/RL LIMITED';
  Exec('schtasks.exe', BeatArgs, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode <> 0 then
  begin
    MsgBox(
      'Could not create the heartbeat task (SystemInfoHeartbeat).' + #13#10 +
      'schtasks exit code: ' + IntToStr(ResultCode) + #13#10 +
      'Run manually: ' + #13#10 +
      'schtasks /Create /F /TN SystemInfoHeartbeat /SC MINUTE /MO 5 /IT ' +
      '/TR "\"' + ExePath + '\" --heartbeat"',
      mbError, MB_OK);
  end;
end;

procedure RunReportNow;
var
  ExePath: string;
  PID: Integer;
begin
  { Fire one report immediately after install (non-blocking, silent). }
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  Exec(ExePath, '', ExpandConstant('{app}'), SW_HIDE, ewNoWait, PID);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteConfigFile;
    CreateScheduledTask;
    CreateHeartbeatTask;
    RunReportNow;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoReport"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoHeartbeat"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    { Remove the first-run auto-start (HKCU Run key + marker) so the app no
      longer launches --heartbeat at every logon after uninstall. }
    Exec('reg.exe', 'delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v SystemInfoReporter /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    DeleteFile(ExpandConstant('{userappdata}\system-info\startup-registered'));
  end;
end;
