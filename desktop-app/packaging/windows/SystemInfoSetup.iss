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

#define MyAppName "System Info Reporter"
#define MyAppVersion "0.1.0"
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
  ConfigPage.Add('Update manifest URL (optional):', False);
  ConfigPage.Values[0] := 'https://your-api.example.com';
  ConfigPage.Values[1] := '';
  ConfigPage.Values[2] := '';
  ConfigPage.Values[3] := '';
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
  { Full report every hour }
  ReportArgs :=
    '/Create /F /TN "SystemInfoReport" /SC HOURLY ' +
    '/TR "\"' + ExePath + '\"" ' +
    '/RL LIMITED';
  Exec('schtasks.exe', ReportArgs, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteConfigFile;
    CreateScheduledTask;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoReport"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoWatch"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('schtasks.exe', '/Delete /F /TN "SystemInfoPoll"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
