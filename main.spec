# -*- mode: python ; coding: utf-8 -*-
# Build lệnh: pyinstaller main.spec

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),       # logo.png, dingdong.wav & tts_offline/*.mp3
        ('hospital.ico', '.'),      # icon trong thư mục gốc
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',        # dùng trong tv_display.py
        'PySide6.QtMultimedia',     # dùng trong tts_service.py
        'PySide6.QtTextToSpeech',   # fallback TTS
        'speaker_hub',              # Trạm phát loa trung tâm (11 phòng)
        'tts_service',              # Dịch vụ đọc loa TTS
        'firestore_client',
        'firestore_queue',
        'firestore_sync',
        'config_manager',
        'oncall_manager',
        'oncall_setup_window',
        'duty_mode_dialog',
        'mini_panel',
        'settings',
        'tv_display',
        'dashboard',
        'chat_service',
        'chat_window',
        'version',
        'updater',
        'sqlite3',
        'urllib.request',
        'urllib.parse',
        'json',
        'datetime',
        'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',      # an toàn loại bỏ - không dùng trong app
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RadiologyQueue',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # Không hiện cửa sổ console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='hospital.ico',
    version_file=None,
)
