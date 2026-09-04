; =====================================================================
; Inno Setup Script for VFX Review Player (cx_Freeze Version)
; Builds a compact, single-file per-user installer in %LOCALAPPDATA%
; =====================================================================

#define MyAppName "VFX Review Player"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "VFX Tools"
#define MyAppExeName "VFX Review Player.exe"

[Setup]
AppId={{5E58941C-2AA4-4D2A-9494-BC5FCEBE30D6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DisableProgramGroupPage=yes
; PrivilegesRequired=lowest ensures non-admin installation in %LOCALAPPDATA%
PrivilegesRequired=lowest
OutputDir=dist_installer
OutputBaseFilename=VFX_Review_Player_Setup_v{#MyAppVersion}
SetupIconFile=logo.ico
LicenseFile=LICENSE
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "contextmenu"; Description: "Add 'Open with VFX Review Player' to right-click context menu"; GroupDescription: "File Explorer Integration:"
Name: "assoc_vfx"; Description: "Associate EXR, DPX, CIN files with VFX Review Player"; GroupDescription: "File Associations:"
Name: "assoc_media"; Description: "Associate MOV, MP4, PNG, JPG, TIFF files with VFX Review Player"; GroupDescription: "File Associations:"

[Files]
Source: "build\exe.win-amd64-3.11\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Registry]
; Right-click context menu integration under HKCU
Root: HKCU; Subkey: "Software\Classes\*\shell\VFXReviewPlayer"; ValueType: string; ValueData: "Open with VFX Review Player"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\VFXReviewPlayer\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: contextmenu

; File Associations for VFX Formats (.exr, .dpx, .cin)
Root: HKCU; Subkey: "Software\Classes\.exr"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_vfx
Root: HKCU; Subkey: "Software\Classes\.dpx"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_vfx
Root: HKCU; Subkey: "Software\Classes\.cin"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_vfx

; File Associations for Media Formats (.mov, .mp4, .png, .jpg, .jpeg, .tif, .tiff)
Root: HKCU; Subkey: "Software\Classes\.mov"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media
Root: HKCU; Subkey: "Software\Classes\.mp4"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media
Root: HKCU; Subkey: "Software\Classes\.png"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media
Root: HKCU; Subkey: "Software\Classes\.jpg"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media
Root: HKCU; Subkey: "Software\Classes\.jpeg"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media
Root: HKCU; Subkey: "Software\Classes\.tif"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media
Root: HKCU; Subkey: "Software\Classes\.tiff"; ValueType: string; ValueData: "VFXReviewPlayer.File"; Flags: uninsdeletevalue; Tasks: assoc_media

; Application File Type Handler Registration
Root: HKCU; Subkey: "Software\Classes\VFXReviewPlayer.File"; ValueType: string; ValueData: "VFX Review Player Media File"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VFXReviewPlayer.File\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExeName},0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VFXReviewPlayer.File\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
