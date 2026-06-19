; ============================================================
; Inno Setup Script - AUTOQ Radiology Queue System
; Tạo bộ cài 1 file duy nhất để chạy trên máy tính khác
; Cách dùng: Mở file này bằng Inno Setup Compiler và bấm Build
; Tải Inno Setup tại: https://jrsoftware.org/isdl.php
; ============================================================

#define MyAppName      "AUTOQ - Hệ thống Gọi số Khoa CĐHA"
#define MyAppVersion   "2.0"
#define MyAppPublisher "Bs Nguyễn Việt Phương"
#define MyAppExeName   "RadiologyQueue.exe"
#define MySourceDir    "dist"

[Setup]
; Thông tin ứng dụng
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}

; Thư mục cài đặt mặc định
DefaultDirName={autopf}\AUTOQ
DefaultGroupName={#MyAppName}

; File cài đặt đầu ra
OutputDir=installer
OutputBaseFilename=AUTOQ_Setup_v{#MyAppVersion}

; Icon và giao diện
SetupIconFile=hospital.ico
WizardStyle=modern
WizardSizePercent=120

; Nén tối đa
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Yêu cầu quyền admin để cài vào Program Files
PrivilegesRequired=admin

; Cho phép tạo desktop shortcut
AllowNoIcons=yes

; Không cần restart sau khi cài
RestartIfNeededByRun=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Tạo shortcut trên Desktop";    GroupDescription: "Shortcut:"
Name: "startmenuicon";  Description: "Tạo shortcut trong Start Menu"; GroupDescription: "Shortcut:"

[Files]
; File exe chính (1 file duy nhất từ PyInstaller --onefile)
Source: "{#MySourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Icon để dùng cho shortcut
Source: "hospital.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Shortcut Start Menu
Name: "{group}\AUTOQ Gọi số"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\hospital.ico"
Name: "{group}\Gỡ cài đặt AUTOQ";  Filename: "{uninstallexe}"

; Shortcut Desktop
Name: "{autodesktop}\AUTOQ Gọi số"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\hospital.ico"; Tasks: desktopicon

[Run]
; Hỏi người dùng có muốn chạy ngay sau khi cài không
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy AUTOQ ngay bây giờ"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Xóa thư mục database khi gỡ cài đặt (tuỳ chọn - bỏ comment nếu muốn)
; Type: filesandordirs; Name: "{app}\database"
