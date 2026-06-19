; ============================================================
; Inno Setup Script - AUTOQ Radiology Queue Client Room
; Version: 3.0 (Cloud Firestore)
; ============================================================

#define MyAppName      "AUTOQ - Gọi số Phòng khám & TV"
#define MyAppVersion   "3.0"
#define MyAppPublisher "BVĐK Thị xã Kỳ Anh"
#define MyAppExeName   "RadiologyQueue.exe"
#define MySourceDir    "dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}

DefaultDirName={autopf}\AUTOQ_ClientRoom
DefaultGroupName={#MyAppName}

OutputDir=installer
OutputBaseFilename=AUTOQ_ClientRoom_Setup_v{#MyAppVersion}

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
Name: "{group}\AUTOQ Gọi số Phòng & TV"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\hospital.ico"
Name: "{group}\Gỡ cài đặt AUTOQ";  Filename: "{uninstallexe}"
Name: "{autodesktop}\AUTOQ Gọi số Phòng & TV"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\hospital.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy AUTOQ Gọi số Phòng & TV"; Flags: nowait postinstall skipifsilent
