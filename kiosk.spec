# -*- mode: python ; coding: utf-8 -*-
# Build lệnh: pyinstaller kiosk.spec

a = Analysis(
    ['kiosk_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('hospital.ico', '.'),      # icon trong thư mục gốc
    ],
    hiddenimports=[
        'selenium',
        'sqlite3',
        'urllib.request',
        'urllib.parse',
        'json',
        'datetime',
        'threading',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
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
    name='KioskQueue',
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
