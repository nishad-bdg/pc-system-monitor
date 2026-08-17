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
;   - Always launches --watch after files are copied (tray). A finish-page
;     checkbox can start it again if the first launch was blocked (AV, etc.);
;     a process mutex prevents two watchers.
;   - On upgrade: stops a running watcher before replacing the exe, then
;     launches --watch again so the tray comes back.
;   - Creates Start Menu (and optional Desktop) shortcuts to start it later
;   - On first run the app self-registers an HKCU Run entry so --watch starts at logon

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
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Prefer one-file build output
Source: "..\..\dist\system-info.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release-manifest.example.json"; DestDir: "{app}"; DestName: "release-manifest.example.json"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--watch"; Comment: "Start {#MyAppName} in the system tray"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--watch"; Comment: "Start {#MyAppName} in the system tray"; Tasks: desktopicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Finish-page retry if the post-install launch was blocked (antivirus, etc.).
; Checked by default; a named mutex in the exe makes a second start a no-op.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--watch"; Description: "Start {#MyAppName} now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'API configuration',
    'The reporter needs your API endpoint and key.',
    'These values are stored in %APPDATA%\system-info\config.env and used by System Info Reporter.');
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

procedure StopWatcher;
var
  ResultCode: Integer;
begin
  { Unlock system-info.exe so this upgrade can replace it. The mutex would
    also make a post-install --watch a no-op while the old process is alive. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#MyAppExeName} /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
end;

procedure LaunchWatcher;
var
  ExePath: string;
  PID: Integer;
  I: Integer;
begin
  { Always start --watch after files + config.env are in place. Interactive
    installs used to wait for the skippable [Run] checkbox, so unchecking it
    (or a failed CreateProcess) left no tray. SW_SHOWNORMAL lets the icon
    appear. Retry a few times in case antivirus still has the new exe locked. }
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  for I := 1 to 3 do
  begin
    if Exec(ExePath, '--watch', ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, PID) then
      Exit;
    Sleep(1000);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopWatcher;
  if CurStep = ssPostInstall then
  begin
    WriteConfigFile;
    LaunchWatcher;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Legacy cleanup: delete any scheduled tasks from older installs. New
      installs no longer create them (startup is the HKCU Run key, admin-free). }
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoWatch"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoReport"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoHeartbeat"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    { Remove the first-run auto-start (HKCU Run key + marker) so the app no
      longer launches --watch at every logon after uninstall. }
    Exec('reg.exe', 'delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v SystemInfoReporter /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    DeleteFile(ExpandConstant('{userappdata}\system-info\startup-registered'));
  end;
end;
