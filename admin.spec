# -*- mode: python ; coding: utf-8 -*-
# Build lệnh: pyinstaller admin.spec

a = Analysis(
    ['admin_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('hospital.ico', '.'),      # icon trong thư mục gốc
    ],
    hiddenimports=[
        'google.cloud.firestore',
        'google.auth.credentials',
        'google.api_core',
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
        'tkinter',
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
    name='AdminQueue',
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
