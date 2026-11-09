#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "anime-nyaa-windows-x86_64-setup"
#endif

[Setup]
AppId={{8F6D8E42-9C3B-4E91-A72E-5C0B19E4A2D1}
AppName=Anime Nyaa
AppVersion={#MyAppVersion}
AppPublisher=Anime Nyaa
AppPublisherURL=https://github.com/desenrolado-s/animes-nyaa
AppSupportURL=https://github.com/desenrolado-s/animes-nyaa
AppUpdatesURL=https://github.com/desenrolado-s/animes-nyaa/releases
DefaultDirName={autopf}\Anime Nyaa
DefaultGroupName=Anime Nyaa
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename={#MyOutputBaseFilename}
SetupIconFile=anime-nyaa.ico
UninstallDisplayIcon={app}\anime-nyaa.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\anime-nyaa\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Anime Nyaa"; Filename: "{app}\anime-nyaa.exe"
Name: "{autodesktop}\Anime Nyaa"; Filename: "{app}\anime-nyaa.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\anime-nyaa.exe"; Description: "{cm:LaunchProgram,Anime Nyaa}"; Flags: nowait postinstall skipifsilent
