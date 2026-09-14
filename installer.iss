[Setup]
AppId={{E8F5D92A-4B72-4B44-9B5A-617F9A1B2C3D}}
AppName=Windows Multi-Audio Router
AppVersion=1.1.1
AppPublisher=Veolinan
AppPublisherURL=https://github.com/Veolinan/Audio_router
AppSupportURL=https://github.com/Veolinan/Audio_router/issues
AppUpdatesURL=https://github.com/Veolinan/Audio_router/releases

; 1. Request Admin Privileges & install cleanly in 64-bit Program Files
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Windows Multi-Audio Router
DefaultGroupName=Windows Multi-Audio Router
DisableProgramGroupPage=no

; 2. About & Info Screen displayed before installation files unpack
InfoBeforeFile=about.txt

; 3. Setup Wizard Visuals & Progress Bar Settings
OutputDir=dist
OutputBaseFilename=AudioRouter-Setup-v1.1.1
SetupIconFile=app.ico
UninstallDisplayName=Windows Multi-Audio Router
UninstallDisplayIcon={app}\AudioRouter.exe
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ShowLanguageDialog=no
WizardStyle=modern

[Tasks]
; Checked by default: user can uncheck either
Name: "startmenuicon"; Description: "Add shortcut to the &Start Menu (Windows Search)"; GroupDescription: "Shortcuts:"
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The main application files copied to {app} during the progress bar phase
Source: "dist\AudioRouter-v1.1.1-win64.exe"; DestDir: "{app}"; DestName: "AudioRouter.exe"; Flags: ignoreversion
Source: "app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "about.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Registered shortcuts for Start Menu and Desktop
Name: "{autoprograms}\Windows Multi-Audio Router"; Filename: "{app}\AudioRouter.exe"; IconFilename: "{app}\app.ico"; Tasks: startmenuicon
Name: "{autodesktop}\Windows Multi-Audio Router"; Filename: "{app}\AudioRouter.exe"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
; Option to launch after progress bar completes
Filename: "{app}\AudioRouter.exe"; Description: "Launch Windows Multi-Audio Router"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Cleanup config and icon if left behind
Type: files; Name: "{app}\config.json"