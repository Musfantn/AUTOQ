# -*- mode: python ; coding: utf-8 -*-
# Build lệnh: pyinstaller main.spec

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),       # logo.png
        ('hospital.ico', '.'),      # icon trong thư mục gốc
    ],
    hiddenimports=[
        'PySide6.QtNetwork',        # dùng trong tv_display.py
        'google.cloud.firestore',
        'google.auth.credentials',
        'google.api_core',
        'sqlite3',
        'urllib.request',
        'urllib.parse',
        'json',
        'datetime',
        'threading',
        'his_bridge',
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
