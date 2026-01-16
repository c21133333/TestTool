#define MyAppName "EazyTestinstall"
#define MyAppExeName "EazyTest.exe"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "Eazy Test"
#define MyAppId "0bb6466f-def6-4f61-bfed-6d79000eb89c"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EazyTest
DefaultGroupName={#MyAppName}
OutputBaseFilename=EazyTestinstall
OutputDir=dist_installer
SetupIconFile=assets\lightning.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EazyTest"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\EazyTest"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch EazyTest"; Flags: nowait postinstall skipifsilent
