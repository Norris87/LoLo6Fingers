# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the macOS app (Apple Silicon).
# Build it with package.command — do not run PyInstaller by hand.
import os
from PyInstaller.utils.hooks import collect_data_files

VERSION = '4.3'

datas = []
datas += collect_data_files('certifi')

# yt-dlp imports these libraries at runtime (try/import), so PyInstaller
# does not find them on its own and they would be missing from the .app.
# Without them the bundled app could do less than the dev environment —
# e.g. yt_dlp_ejs solves YouTube's JS challenges and websockets are
# needed for live streams.
hiddenimports = [
    'Cryptodome', 'Cryptodome.Cipher', 'Cryptodome.Cipher.AES',
    'websockets',
    'brotli',
    'mutagen',
    'requests',
    'urllib3',
    'yt_dlp_ejs',
]
try:
    datas += collect_data_files('yt_dlp_ejs')
except Exception:
    pass

# Deno = JavaScript runtime for YouTube. Without it yt-dlp tries only one
# client (visionos) and many videos fail. Most users have neither Node nor
# Deno, so we bundle it. package.command downloads it automatically.
binaries = [('ffmpeg', '.'), ('ffprobe', '.')]
if os.path.isfile('deno'):
    binaries.append(('deno', '.'))
    print(">>> Deno will be bundled into the .app")
else:
    print(">>> WARNING: deno is missing — the .app will work, but YouTube worse")

a = Analysis(
    ['lolo6fingers.py'],
    pathex=[],
    binaries=binaries,
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    # Deno is signed by Deno Land — UPX compression would break both the
    # signature and the binary
    upx_exclude=['deno'],
    name='LoLo6Fingers',
)
app = BUNDLE(
    coll,
    name='LoLo6Fingers.app',
    icon='icon.icns',
    bundle_identifier='com.norrislav.lolo6fingers',
    version=VERSION,
    info_plist={
        'CFBundleName': 'LoLo6Fingers',
        'CFBundleDisplayName': 'LoLo6Fingers',
        'CFBundleShortVersionString': VERSION,
        'CFBundleVersion': VERSION,
        'NSHighResolutionCapable': True,
    },
)
