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
;   - Offers a finish-page checkbox to start the app (system tray) now
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
; Finish-page checkbox so the user can start the app (tray) right after install.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--watch"; Description: "Start {#MyAppName} now"; Flags: nowait postinstall skipifsilent

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

procedure LaunchWatcher;
var
  ExePath: string;
  PID: Integer;
begin
  { Start the always-on watcher (used for silent installs). Interactive
    installs use the [Run] finish-page checkbox instead of this so the user
    can choose. SW_SHOWNORMAL lets the tray icon appear. }
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  Exec(ExePath, '--watch', ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, PID);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteConfigFile;
    { Interactive installs start via the [Run] checkbox on the finish page.
      Silent installs have no finish page, so launch the tray watcher here. }
    if WizardSilent then
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
