; ============================================================
; Inno Setup Script - AUTOQ Kiosk Tiếp đón Bệnh nhân
; Version: 3.0 (Cloud Firestore)
; ============================================================

#define MyAppName      "AUTOQ - Kiosk Tiếp đón"
#define MyAppVersion   "3.0"
#define MyAppPublisher "BVĐK Thị xã Kỳ Anh"
#define MyAppExeName   "KioskQueue.exe"
#define MySourceDir    "dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{B2C3D4E5-F6A7-8901-BCDE-F0123456789A}

DefaultDirName={autopf}\AUTOQ_Kiosk
DefaultGroupName={#MyAppName}

OutputDir=installer
OutputBaseFilename=AUTOQ_Kiosk_Setup_v{#MyAppVersion}

SetupIconFile=hospital.ico
WizardStyle=modern
WizardSizePercent=120

Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

PrivilegesRequired=admin
AllowNoIcons=yes
RestartIfNeededByRun=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Tạo shortcut trên Desktop";    GroupDescription: "Shortcut:"
Name: "startmenuicon";  Description: "Tạo shortcut trong Start Menu"; GroupDescription: "Shortcut:"

[Files]
Source: "{#MySourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "hospital.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AUTOQ Kiosk Tiếp đón"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\hospital.ico"
Name: "{group}\Gỡ cài đặt AUTOQ";  Filename: "{uninstallexe}"
Name: "{autodesktop}\AUTOQ Kiosk Tiếp đón"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\hospital.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy AUTOQ Kiosk Tiếp đón"; Flags: nowait postinstall skipifsilent
