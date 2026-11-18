; ============================================================
; Inno Setup 7 Script - AUTOQ Radiology & Functional Suite (v6.0 All-In-One)
; Bộ cài đặt All-In-One chạy độc lập trên mọi máy tính:
; - Gọi số 11 phòng (Siêu âm 1..5, Nội soi TMH, Nội soi Tiêu hóa, ĐTĐ, ĐNĐ, LHN, CNHH)
; - Trạm Phát Loa Trung Tâm tại Phòng Siêu Âm 2 (kèm nhạc hiệu dingdong.wav & giọng đọc Online/Offline)
; - Kiểm soát lượng bệnh nhân, lịch mùa Đông/Hè, bảo mật mật khẩu & Báo cáo Realtime (Admin Center)
; ============================================================

#define MyAppName      "AUTOQ - Hệ Thống Gọi Số Khoa CĐHA & TDCN"
#define MyAppVersion   "7.0"
#define MyAppPublisher "Khoa Chẩn Đoán Hình Ảnh - BVĐK Thị Xã Kỳ Anh"
#define MySourceDir    "dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{B8F7D6E5-4C3B-2A10-9876-FEDCBA987654}

DefaultDirName={autopf}\AUTOQ
DefaultGroupName={#MyAppName}

OutputDir=installer
OutputBaseFilename=AUTOQ_AllInOne_Setup_v{#MyAppVersion}

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

[Types]
Name: "full";   Description: "Cài đặt Đầy Đủ (Phòng Khám + Quản Trị Admin)"
Name: "clinic"; Description: "Máy Bác Sĩ / Phòng Khám (Dashboard, MiniPanel, TV & Trạm Loa)"
Name: "admin";  Description: "Máy Quản Trị & Kiểm Soát Lượng Bệnh Nhân 11 Phòng (Admin Center)"
Name: "custom"; Description: "Tùy chỉnh thành phần cài đặt"; Flags: iscustom

[Components]
Name: "common"; Description: "Tài nguyên âm thanh (dingdong.wav, giọng đọc Offline 11 phòng), Logo & Cơ sở dữ liệu"; Types: full clinic admin custom; Flags: fixed
Name: "clinic"; Description: "Ứng dụng Gọi Số Phòng Khám, TV Display & Trạm Loa Trung Tâm (RadiologyQueue.exe)"; Types: full clinic
Name: "admin";  Description: "Ứng dụng Quản Trị & Kiểm Soát Lượng Bệnh Nhân 11 Phòng (AdminQueue.exe)"; Types: full admin

[Tasks]
Name: "desktopicon";   Description: "Tạo shortcut trên Desktop";    GroupDescription: "Tùy chọn Shortcut:"
Name: "startmenuicon"; Description: "Tạo shortcut trong Start Menu"; GroupDescription: "Tùy chọn Shortcut:"

[Dirs]
Name: "{app}\assets"; Permissions: users-modify
Name: "{app}\assets\tts_offline"; Permissions: users-modify
Name: "{commonappdata}\AUTOQ"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\database"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\database\tts_cache"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\logs"; Permissions: users-full

[Files]
Source: "{#MySourceDir}\RadiologyQueue.exe"; DestDir: "{app}"; Components: clinic; Flags: ignoreversion
Source: "{#MySourceDir}\AdminQueue.exe"; DestDir: "{app}"; Components: admin; Flags: ignoreversion
Source: "hospital.ico"; DestDir: "{app}"; Components: common; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Components: common; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AUTOQ - Gọi Số & Màn Hình TV"; Filename: "{app}\RadiologyQueue.exe"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: clinic
Name: "{autodesktop}\AUTOQ - Gọi Số & Màn Hình TV"; Filename: "{app}\RadiologyQueue.exe"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: clinic; Tasks: desktopicon

Name: "{group}\AUTOQ - Quản Trị & Báo Cáo"; Filename: "{app}\AdminQueue.exe"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: admin
Name: "{autodesktop}\AUTOQ - Quản Trị & Báo Cáo"; Filename: "{app}\AdminQueue.exe"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: admin; Tasks: desktopicon

Name: "{group}\Gỡ cài đặt AUTOQ"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\RadiologyQueue.exe"; Description: "Chạy Ứng dụng Gọi Số & TV Display"; WorkingDir: "{app}"; Components: clinic; Flags: nowait postinstall skipifsilent
Filename: "{app}\AdminQueue.exe"; Description: "Chạy Ứng dụng Quản Trị & Báo Cáo"; WorkingDir: "{app}"; Components: admin; Flags: nowait postinstall skipifsilent unchecked
