; ============================================================
; Inno Setup 7 Script - AUTOQ All-In-One Radiology Suite
; Bộ cài đặt tất cả trong một (All-In-One) cho hệ thống AUTOQ
; Tích hợp tùy chọn cài đặt theo vai trò: Kiosk, Phòng khám, Quản trị
; Lưu dữ liệu cấu hình tại ProgramData tránh lỗi Access Denied
; ============================================================

#define MyAppName      "AUTOQ - Hệ Thống Gọi Số Khoa CĐHA"
#define MyAppVersion   "4.5"
#define MyAppPublisher "Khoa Chẩn Đoán Hình Ảnh - BVĐK Thị Xã Kỳ Anh"
#define MySourceDir    "dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{B8F7D6E5-4C3B-2A10-9876-FEDCBA987654}

; Thư mục cài đặt chương trình (Binaries): Program Files\AUTOQ
DefaultDirName={autopf}\AUTOQ
DefaultGroupName={#MyAppName}

; File cài đặt đầu ra
OutputDir=installer
OutputBaseFilename=AUTOQ_AllInOne_Setup_v{#MyAppVersion}

; Giao diện Inno Setup 7
SetupIconFile=hospital.ico
WizardStyle=modern
WizardSizePercent=120

; Thuật toán nén tối ưu
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Yêu cầu quyền Admin để ghi Program Files & cấp quyền ProgramData
PrivilegesRequired=admin
AllowNoIcons=yes
RestartIfNeededByRun=no

[Types]
Name: "full";   Description: "Cài đặt Đầy Đủ (Tất cả ứng dụng cho Máy Trung Tâm / Server)"
Name: "kiosk";  Description: "Máy Tiếp Đón Bệnh Nhân (Kiosk App)"
Name: "clinic"; Description: "Máy Bác Sĩ / Phòng Siêu Âm (Dashboard & TV Display)"
Name: "admin";  Description: "Máy Quản Trị & Báo Cáo (Admin Center)"
Name: "custom"; Description: "Tùy chỉnh thành phần cài đặt"; Flags: iscustom

[Components]
Name: "common";  Description: "Cơ sở dữ liệu & Cấu hình dùng chung (ProgramData)"; Types: full kiosk clinic admin custom; Flags: fixed
Name: "kiosk";   Description: "Ứng dụng Kiosk Tiếp đón bệnh nhân (KioskQueue.exe)"; Types: full kiosk
Name: "clinic";  Description: "Ứng dụng Dashboard Gọi số & TV Display (RadiologyQueue.exe)"; Types: full clinic
Name: "admin";   Description: "Ứng dụng Quản trị & Báo cáo Realtime (AdminQueue.exe)"; Types: full admin

[Tasks]
Name: "desktopicon";    Description: "Tạo shortcut trên Desktop";    GroupDescription: "Tùy chọn Shortcut:"
Name: "startmenuicon";  Description: "Tạo shortcut trong Start Menu"; GroupDescription: "Tùy chọn Shortcut:"

[Dirs]
; Tạo các thư mục lưu dữ liệu có quyền ghi đầy đủ trên %PROGRAMDATA%\AUTOQ tránh lỗi Access Denied
Name: "{commonappdata}\AUTOQ"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\database"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\his_bridge"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\logs"; Permissions: users-full
Name: "{commonappdata}\AUTOQ\queue"; Permissions: users-full

[Files]
; === PROGRAM BINARIES ({app}) ===
Source: "{#MySourceDir}\KioskQueue.exe"; DestDir: "{app}"; Components: kiosk; Flags: ignoreversion
Source: "{#MySourceDir}\RadiologyQueue.exe"; DestDir: "{app}"; Components: clinic; Flags: ignoreversion
Source: "{#MySourceDir}\AdminQueue.exe"; DestDir: "{app}"; Components: admin; Flags: ignoreversion
Source: "hospital.ico"; DestDir: "{app}"; Flags: ignoreversion

; === DATA & CONFIGURATIONS (%PROGRAMDATA%\AUTOQ) ===
Source: "his_bridge\config.yaml"; DestDir: "{commonappdata}\AUTOQ\his_bridge"; Components: common; Flags: onlyifdoesntexist uninsneveruninstall
Source: "database\config.db"; DestDir: "{commonappdata}\AUTOQ\database"; Components: common; Flags: onlyifdoesntexist uninsneveruninstall; Check: FileExists('database\config.db')

[Icons]
; --- Kiosk App ---
Name: "{group}\AUTOQ - Kiosk Tiếp Đón"; Filename: "{app}\KioskQueue.exe"; IconFilename: "{app}\hospital.ico"; Components: kiosk
Name: "{autodesktop}\AUTOQ - Kiosk Tiếp Đón"; Filename: "{app}\KioskQueue.exe"; IconFilename: "{app}\hospital.ico"; Components: kiosk; Tasks: desktopicon

; --- Radiology Clinic Dashboard ---
Name: "{group}\AUTOQ - Gọi Số & Màn Hình TV"; Filename: "{app}\RadiologyQueue.exe"; IconFilename: "{app}\hospital.ico"; Components: clinic
Name: "{autodesktop}\AUTOQ - Gọi Số & Màn Hình TV"; Filename: "{app}\RadiologyQueue.exe"; IconFilename: "{app}\hospital.ico"; Components: clinic; Tasks: desktopicon

; --- Admin Center ---
Name: "{group}\AUTOQ - Quản Trị & Báo Cáo"; Filename: "{app}\AdminQueue.exe"; IconFilename: "{app}\hospital.ico"; Components: admin
Name: "{autodesktop}\AUTOQ - Quản Trị & Báo Cáo"; Filename: "{app}\AdminQueue.exe"; IconFilename: "{app}\hospital.ico"; Components: admin; Tasks: desktopicon

; --- Uninstall ---
Name: "{group}\Gỡ cài đặt AUTOQ"; Filename: "{uninstallexe}"

[Run]
; Tùy chọn chạy ứng dụng tương ứng ngay sau khi kết thúc cài đặt
Filename: "{app}\KioskQueue.exe"; Description: "Chạy Ứng dụng Kiosk Tiếp Đón"; Components: kiosk; Flags: nowait postinstall skipifsilent unchecked
Filename: "{app}\RadiologyQueue.exe"; Description: "Chạy Ứng dụng Gọi Số & TV Display"; Components: clinic; Flags: nowait postinstall skipifsilent
Filename: "{app}\AdminQueue.exe"; Description: "Chạy Ứng dụng Quản Trị & Báo Cáo"; Components: admin; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Giữ nguyên cơ sở dữ liệu ProgramData khi gỡ ứng dụng trừ khi người dùng xóa thủ công
