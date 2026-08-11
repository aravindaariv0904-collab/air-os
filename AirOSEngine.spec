# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

PROJECT_ROOT = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(PROJECT_ROOT, 'assets', 'models', 'hand_landmarker.task'), os.path.join('assets', 'models')),
    (os.path.join(PROJECT_ROOT, 'gestures', 'registry', 'system_gestures.json'), os.path.join('gestures', 'registry')),
    (os.path.join(PROJECT_ROOT, 'gestures', 'profiles', 'profiles.json'), os.path.join('gestures', 'profiles')),
]

hiddenimports = [
    'mediapipe',
    'mediapipe.tasks',
    'mediapipe.tasks.python',
    'mediapipe.tasks.python.vision',
    'cv2',
    'numpy',
    'websockets',
    'psutil',
    'pynput',
    'pynput.keyboard',
    'pynput.mouse',
    'ctypes',
    'ctypes.wintypes',
    'asyncio',
    'json',
    'threading',
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'run_engine.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AirOSEngine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Run without console window in production
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'apps', 'desktop', 'public', 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AirOSEngine',
)
