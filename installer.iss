; ============================================================
; Inno Setup 7 Script - AUTOQ Radiology & Functional Suite
; Đóng gói bộ cài đặt độc lập (Standalone Installer) chạy trên mọi máy tính:
; - Bao gồm ứng dụng Phòng Khám / TV Display / Trạm Loa Trung Tâm (RadiologyQueue.exe)
; - Bao gồm ứng dụng Quản Trị & Báo Cáo Thống Kê 11 Phòng (AdminQueue.exe)
; - Đóng gói đầy đủ toàn bộ tài nguyên assets (logo.png, dingdong.wav, 29 file giọng đọc tts_offline/*.mp3)
; ============================================================

#define MyAppName      "AUTOQ - Hệ Thống Gọi Số Khoa CĐHA & TDCN"
#define MyAppVersion   "7.2.0"
#define MyAppPublisher "Bs Nguyễn Việt Phương - BVĐK Thị Xã Kỳ Anh"
#define MyAppExeName   "RadiologyQueue.exe"
#define MyAdminExeName "AdminQueue.exe"
#define MySourceDir    "dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}

DefaultDirName={autopf}\AUTOQ
DefaultGroupName={#MyAppName}

OutputDir=installer
OutputBaseFilename=AUTOQ_Setup_v{#MyAppVersion}

SetupIconFile=hospital.ico
WizardStyle=modern
WizardSizePercent=120

Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

PrivilegesRequired=admin
AllowNoIcons=yes
RestartIfNeededByRun=no
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full";   Description: "Cài đặt Đầy Đủ (Máy Phòng Khám + Quản Trị Admin)"
Name: "clinic"; Description: "Máy Bác Sĩ / Phòng Khám (Dashboard, MiniPanel, TV & Trạm Loa)"
Name: "admin";  Description: "Máy Quản Trị & Thống Kê Báo Cáo 11 Phòng (Admin Center)"
Name: "custom"; Description: "Tùy chỉnh thành phần cài đặt"; Flags: iscustom

[Components]
Name: "common"; Description: "Tài nguyên âm thanh (dingdong.wav, giọng đọc Offline 11 phòng), Logo & Cơ sở dữ liệu"; Types: full clinic admin custom; Flags: fixed
Name: "clinic"; Description: "Ứng dụng Gọi Số Phòng Khám, TV Display & Trạm Loa Trung Tâm (RadiologyQueue.exe)"; Types: full clinic
Name: "admin";  Description: "Ứng dụng Quản Trị & Thống Kê 11 Phòng (AdminQueue.exe)"; Types: full admin

[Tasks]
Name: "desktopicon";   Description: "Tạo shortcut trên Desktop";    GroupDescription: "Shortcut:"
Name: "startmenuicon"; Description: "Tạo shortcut trong Start Menu"; GroupDescription: "Shortcut:"

[Dirs]
Name: "{app}\assets"; Permissions: users-modify
Name: "{app}\assets\tts_offline"; Permissions: users-modify
Name: "{commonappdata}\AUTOQ"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\database"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\database\tts_cache"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\logs"; Permissions: users-full

[Files]
; Các file thực thi độc lập (đã tích hợp Python runtime, PySide6, QtMultimedia FFmpeg)
Source: "{#MySourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Components: clinic; Flags: ignoreversion
Source: "{#MySourceDir}\{#MyAdminExeName}"; DestDir: "{app}"; Components: admin; Flags: ignoreversion

; Icon ứng dụng
Source: "hospital.ico"; DestDir: "{app}"; Components: common; Flags: ignoreversion

; Đầy đủ toàn bộ thư mục assets (logo.png, dingdong.wav, bộ 29 file giọng đọc tiếng Việt tts_offline/*.mp3)
Source: "assets\*"; DestDir: "{app}\assets"; Components: common; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Shortcut Start Menu
Name: "{group}\AUTOQ - Gọi Số & Màn Hình TV"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: clinic
Name: "{group}\AUTOQ - Quản Trị & Báo Cáo (Admin)"; Filename: "{app}\{#MyAdminExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: admin
Name: "{group}\Gỡ cài đặt AUTOQ"; Filename: "{uninstallexe}"

; Shortcut Desktop
Name: "{autodesktop}\AUTOQ - Gọi Số & Màn Hình TV"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: clinic; Tasks: desktopicon
Name: "{autodesktop}\AUTOQ - Quản Trị & Báo Cáo (Admin)"; Filename: "{app}\{#MyAdminExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\hospital.ico"; Components: admin; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy AUTOQ Gọi Số & TV Display ngay bây giờ"; WorkingDir: "{app}"; Components: clinic; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAdminExeName}"; Description: "Chạy AUTOQ Quản Trị & Báo Cáo (Admin)"; WorkingDir: "{app}"; Components: admin; Flags: nowait postinstall skipifsilent unchecked
