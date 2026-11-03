; Mavis 0.1.0: per-user install; no DSH/Codex cleanup, no user-data deletion.
#ifndef MyAppDir
  #error MyAppDir must name the exact verified onedir candidate
#endif
#ifndef MyOutputDir
  #error MyOutputDir is required
#endif
#define MyVersion "0.1.0"
[Setup]
AppId={{80409E71-51A4-46F3-AD0D-6E8B11D91010}
AppName=DaFeiYu Mavis
AppVersion={#MyVersion}
AppPublisher=Favio8
AppPublisherURL=https://github.com/Favio8/dafeiyu-mavis
DefaultDirName={localappdata}\Programs\DaFeiYuMavis
DefaultGroupName=DaFeiYu Mavis
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assistant\assets\mavis.ico
UninstallDisplayIcon={app}\DaFeiYuMavis.exe
OutputDir={#MyOutputDir}
OutputBaseFilename=DaFeiYu-Mavis-0.1.0-win-x64-setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
CloseApplicationsFilter=DaFeiYuMavis.exe,mavis-worker.exe
RestartApplications=no
LicenseFile=mavis-license.txt
[Languages]
Name: english; MessagesFile: compiler:Default.isl
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "{#MyAppDir}\*"; DestDir: "{app}"; Excludes: "portable.json,data\*"; Flags: ignoreversion recursesubdirs createallsubdirs
[INI]
Filename: "{app}\mavis-location.ini"; Section: Mavis; Key: DataHome; String: "{code:GetDataHome}"
[Icons]
Name: "{autoprograms}\DaFeiYu Mavis"; Filename: "{app}\DaFeiYuMavis.exe"
Name: "{autodesktop}\DaFeiYu Mavis"; Filename: "{app}\DaFeiYuMavis.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\DaFeiYuMavis.exe"; Description: "Launch DaFeiYu Mavis"; Flags: nowait postinstall skipifsilent; Check: CanLaunch
[Code]
var
  DataPage: TInputDirWizardPage;
  BackupOK: Boolean;
function MavisMoveFile(OldName, NewName: String; Flags: LongWord): Boolean;
  external 'MoveFileExW@kernel32.dll stdcall';
function MavisTick: LongWord;
  external 'GetTickCount@kernel32.dll stdcall';
function GetDataHome(Param: String): String;
begin
  Result := DataPage.Values[0];
end;
function CanLaunch: Boolean;
begin
  Result := BackupOK;
end;
procedure InitializeWizard;
var Initial: String;
begin
  DataPage := CreateInputDirPage(wpSelectDir, 'Mavis data folder',
    'Choose where settings and task history are stored.',
    'Uninstall keeps your data and Windows credentials. If a folder cannot save settings, select another drive. Existing data is not moved or overwritten.', False, '');
  DataPage.Add('Data folder:');
  Initial := ExpandConstant('{param:DATAHOME|}');
  if Initial = '' then
    Initial := GetIniString('Mavis', 'DataHome', ExpandConstant('{localappdata}'), ExpandConstant('{app}\mavis-location.ini'));
  DataPage.Values[0] := Initial;
  BackupOK := True;
end;
function CheckDataFolder: Boolean;
var Folder, A, B: String;
begin
  Folder := AddBackslash(GetDataHome('')) + 'DaFeiYuMavis';
  A := AddBackslash(Folder) + '.mavis-install-probe-' + IntToStr(MavisTick) + '.tmp';
  B := A + '.renamed';
  Result := False;
  if FileExists(A) or FileExists(B) then exit;
  if not ForceDirectories(Folder) then exit;
  if SaveStringToFile(A, 'Mavis temporary write check', False) then
    Result := MavisMoveFile(A, B, 1);
  DeleteFile(A);
  DeleteFile(B);
end;
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DataPage.ID then begin
    Result := CheckDataFolder;
    if not Result then MsgBox('This folder cannot save Mavis settings. Select another folder or drive. Existing data has not been changed.', mbError, MB_OK);
  end;
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CheckDataFolder then Result := 'The data folder does not support the required safe writes. Choose another drive.';
end;
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer; OK: Boolean;
begin
  if CurStep = ssPostInstall then begin
    OK := Exec(ExpandConstant('{app}\mavis-worker.exe'),
      '--backup-data --data-home "' + GetDataHome('') + '"', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code);
    BackupOK := OK and (Code = 0);
    if not BackupOK then MsgBox('Mavis could not back up existing data. Do not start an upgrade until the backup issue is resolved. Your data has not been cleared.', mbError, MB_OK);
  end;
end;
; No UninstallDelete, DSH bridge commands, hook cleanup or credential deletion.
