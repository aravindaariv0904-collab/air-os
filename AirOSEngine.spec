# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

PROJECT_ROOT = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(PROJECT_ROOT, 'assets', 'models', 'hand_landmarker.task'), os.path.join('assets', 'models')),
    (os.path.join(PROJECT_ROOT, 'assets', 'models', 'face_landmarker.task'), os.path.join('assets', 'models')),
    # PyInstaller copies a source DIRECTORY's contents into the destination, so the
    # model keeps its name by nesting the destination one level deeper.
    (os.path.join(PROJECT_ROOT, 'assets', 'models', 'vosk-model-small-en-us-0.15'),
     os.path.join('assets', 'models', 'vosk-model-small-en-us-0.15')),
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
    # Voice (all lazily imported -> must be hidden imports)
    'vosk',
    'sounddevice',
    '_sounddevice_data',
    'pyttsx3',
    'win32com',
    'win32com.client',
    'win32gui',
    'win32process',
    'win32con',
    'win32api',
    'pycaw',
    'pycaw.pycaw',
    'comtypes',
    'comtypes.stream',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    # New subsystems
    'engine.resources',
    'engine.voice',
    'engine.voice.audio',
    'engine.voice.recognizer',
    'engine.voice.intent',
    'engine.voice.speech_output',
    'engine.voice.assistant',
    'engine.vision',
    'engine.vision.face_tracker',
    'engine.vision.blink_detector',
    'engine.actions',
    'engine.actions.skills',
    'engine.actions.verifier',
    'engine.actions.executor',
    'engine.context',
    'input.screenshot',
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'run_engine.py')],
    pathex=[PROJECT_ROOT],
    # Vosk ships native DLLs (libvosk.dll, libstdc++, ...) in its package dir.
    # They must land in _internal/vosk so vosk's add_dll_directory() works.
    binaries=collect_dynamic_libs('vosk'),
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
