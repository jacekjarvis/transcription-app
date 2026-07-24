; Whisper Transcriber -- Inno Setup installer script.
; Compile with: ISCC.exe WhisperTranscriber.iss
; Produces a single WhisperTranscriberSetup.exe in the "dist" folder.

#define MyAppName "Whisper Transcriber"
#define MyAppVersion "1.0"
#define MyAppPublisher "Jay"
#define MyAppExeName "Transcriber.bat"

[Setup]
AppId={{9C2E7B3A-4F1D-4C6E-9A8E-3B7C1F2E5D6A}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=WhisperTranscriberSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={sys}\imageres.dll,264
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "transcriber.pyw"; DestDir: "{app}"; Flags: ignoreversion
Source: "Transcriber.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "InstallPrereqs.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 264
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 264; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent shellexec; Check: PrereqsSucceeded

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  PrereqsOk: Boolean;

function PrereqsSucceeded: Boolean;
begin
  Result := PrereqsOk;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ScriptPath: String;
  Ran: Boolean;
begin
  if CurStep = ssPostInstall then
  begin
    ScriptPath := ExpandConstant('{app}\InstallPrereqs.ps1');
    WizardForm.StatusLabel.Caption :=
      'Installing Python, ffmpeg, and the Whisper engine (this can take ' +
      'several minutes on first install)...';

    Ran := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
      '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
    PrereqsOk := Ran and (ResultCode = 0);
    Log('InstallPrereqs.ps1: Ran=' + IntToStr(Ord(Ran)) +
      ' ResultCode=' + IntToStr(ResultCode) +
      ' PrereqsOk=' + IntToStr(Ord(PrereqsOk)));

    if not PrereqsOk then
    begin
      MsgBox(
        'Whisper Transcriber was installed, but setting up Python, ffmpeg, ' +
        'and the Whisper engine did not finish successfully (see the ' +
        'PowerShell window that appeared during install for details).' + #13#10 + #13#10 +
        'The app has NOT been launched, since it would not work yet.' + #13#10 + #13#10 +
        'To fix this: try running this installer again (it is safe to ' +
        're-run), or open a terminal and run:  pip install openai-whisper',
        mbError, MB_OK);
    end;
  end;
end;
