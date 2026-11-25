; installer.iss — Kryonyx Music installer for Windows (Inno Setup 6).
; A regular setup wizard: install folder, desktop shortcut, Start menu entry,
; optional autostart and an uninstaller.
; Build:  iscc build\installer.iss   (after PyInstaller)

#define AppName "Kryo"
; build_windows.ps1 passes /DAppVersion=<kryonyx.__version__>; 1.0.0 is the fallback.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "Kryonyx"
#define AppExe "Kryo.exe"
#define DistDir AddBackslash(SourcePath) + "..\dist\Kryo"

; A clear error instead of "Source file not found": the installer can only be
; built after PyInstaller, otherwise there is nothing to package.
#if !FileExists(DistDir + "\" + AppExe)
  #error "No PyInstaller build in dist\Kryo. First run from the project root: powershell -ExecutionPolicy Bypass -File build\build_windows.ps1"
#endif

[Setup]
AppId={{8F3D2A61-6C4E-4C9B-9E2A-5B1C7D0A9E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} setup engine
OutputDir=..\dist
OutputBaseFilename=Kryo-{#AppVersion}-engine
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LanguageDetectionMethod=none
UsePreviousLanguage=no
; Installs into the user profile when there are no admin rights.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=no
DisableDirPage=no
LicenseFile=..\LICENSE
SetupIconFile=icon.ico
AllowNoIcons=yes
MinVersion=10.0
; Updating over a running copy: the wizard asks Kryonyx to close first; Restart
; Manager is the backstop (/CLOSEAPPLICATIONS). Python extension modules (*.pyd)
; count as "in use" too. The wizard relaunches the app itself, so no restart here.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
en.CreateDesktopIcon=Create a desktop shortcut
en.AutoStart=Start Kryo when Windows starts
en.LaunchApp=Launch {#AppName}

en.DeleteUserData=Delete all personal data, including playlists, likes, history and uploaded avatars? Choose No to keep it for a later installation.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Every build ships a complete PyInstaller runtime. Remove the previous one so
; stale modules and package metadata never mix with the new version.
; Personal data lives in %LOCALAPPDATA%\KryonyxMusic and is not touched.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\KryonyxMusic.exe"
; The wizard's choices are authoritative on update: shortcuts for options that
; were switched off are removed instead of lingering from the last install.
Type: files; Name: "{autodesktop}\{#AppName}.lnk"; Tasks: not desktopicon
Type: files; Name: "{userstartup}\{#AppName}.lnk"; Tasks: not autostart

[Files]
; Contents of the PyInstaller onedir build.
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\TERMS.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ARTWORK_RIGHTS.md"; DestDir: "{app}"; Flags: ignoreversion
; v72: optional AI module setup (creates {app}\.ai-venv on demand from the player).
Source: "..\setup-ai.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-ai.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; IconFilename is set explicitly: shortcuts take the Kryonyx Core icon from icon.ico
; and do not depend on Explorer's icon cache.
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: autostart

[Run]
; Refresh the Windows icon cache, otherwise Explorer may keep showing
; the old icon for the new .exe for days.
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden skipifdoesntexist
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; App logs and cache; the playlist database stays unless the user agrees to delete it.
Type: filesandordirs; Name: "{localappdata}\Kryo\cache"
; Optional AI environment created by setup-ai.bat next to the program (several GB).
Type: filesandordirs; Name: "{app}\.ai-venv"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox(CustomMessage('DeleteUserData'),
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{localappdata}\Kryo'), True, True, True);
  end;
end;
