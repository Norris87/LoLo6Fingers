# -*- mode: python ; coding: utf-8 -*-
# EXPERIMENTAL Windows build. Run from the repository root on Windows:
#   python -m PyInstaller windows\LoLo6Fingers_windows.spec --noconfirm --clean
# Needs ffmpeg.exe and ffprobe.exe in the repository root
# (from https://www.gyan.dev/ffmpeg/builds/ — "release essentials").
import os
from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

datas = []
datas += collect_data_files('certifi')

# yt-dlp imports these at runtime — PyInstaller does not find them by itself
hiddenimports = [
    'Cryptodome', 'Cryptodome.Cipher', 'Cryptodome.Cipher.AES',
    'websockets', 'brotli', 'mutagen', 'requests', 'urllib3', 'yt_dlp_ejs',
]
try:
    datas += collect_data_files('yt_dlp_ejs')
except Exception:
    pass

icon_file = os.path.join(ROOT, 'icon.ico')
icon_file = icon_file if os.path.exists(icon_file) else None

a = Analysis(
    [os.path.join(ROOT, 'lolo6fingers.py')],
    pathex=[ROOT],
    binaries=[(os.path.join(ROOT, 'ffmpeg.exe'), '.'),
              (os.path.join(ROOT, 'ffprobe.exe'), '.')],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LoLo6Fingers',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LoLo6Fingers',
)
