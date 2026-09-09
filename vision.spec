# -*- mode: python ; coding: utf-8 -*-
import glob, os

# Proje klasöründeki tüm PNG ve MP3 dosyalarını otomatik topla
asset_files = [(f, '.') for f in glob.glob('*.png')] + [(f, '.') for f in glob.glob('*.mp3')]

a = Analysis(
    ['vision.py'],
    pathex=['.'],
    binaries=[
        ('interception.dll', '.'),  # Kernel sürücü DLL - şart
    ],
    datas=asset_files + [
        ('config.json', '.'),       # Kayıtlı ayarlar (varsa)
    ],
    hiddenimports=[
        'cv2',
        'numpy',
        'mss',
        'keyboard',
        'PIL',
        'tkinter',
        'pygame',
        'pygame.mixer',
    ],
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
    a.binaries,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Siyah konsol penceresini gizle (yalnızca GUI açılır)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
