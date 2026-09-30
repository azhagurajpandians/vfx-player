# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import glob

sys.setrecursionlimit(5000)

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all

datas = [
    ('configs', 'configs'),
    ('core', 'core'),
    ('gui', 'gui'),
    ('logo.png', '.'),
    ('LICENSE', '.'),
]

if os.path.exists('VERSION'):
    datas.append(('VERSION', '.'))

if os.path.exists('bin/ffmpeg/linux'):
    datas.append(('bin/ffmpeg/linux', 'bin/ffmpeg/linux'))
elif os.path.exists('bin/ffmpeg'):
    datas.append(('bin/ffmpeg', 'bin/ffmpeg'))

binaries = []

# Collect cv2, numpy, imageio, and vispy resources
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all('cv2')
np_datas, np_binaries, np_hiddenimports = collect_all('numpy')
imgio_datas, imgio_binaries, imgio_hiddenimports = collect_all('imageio')
vispy_datas, vispy_binaries, vispy_hiddenimports = collect_all('vispy')

# Collect OIIO/OCIO
try:
    oiio_datas = collect_data_files('OpenImageIO', include_py_files=True)
    oiio_binaries = collect_dynamic_libs('OpenImageIO')
except Exception:
    oiio_datas, oiio_binaries = [], []

try:
    ocio_datas = collect_data_files('PyOpenColorIO', include_py_files=True)
    ocio_binaries = collect_dynamic_libs('PyOpenColorIO')
except Exception:
    ocio_datas, ocio_binaries = [], []

try:
    av_datas, av_binaries, av_hiddenimports = collect_all('av')
except Exception:
    av_datas, av_binaries, av_hiddenimports = [], [], []

datas += vispy_datas + oiio_datas + ocio_datas + av_datas
binaries += cv2_binaries + np_binaries + imgio_binaries + vispy_binaries + oiio_binaries + ocio_binaries + av_binaries

hiddenimports = list(set(
    cv2_hiddenimports + np_hiddenimports + imgio_hiddenimports + vispy_hiddenimports + av_hiddenimports + [
        'cv2',
        'cv2.typing',
        'vispy',
        'vispy.visuals',
        'vispy.scene',
        'vispy.app.backends._pyqt6',
        'OpenGL',
        'OpenGL.GL',
        'OpenGL.GLU',
        'OpenGL.platform',
        'OpenGL.platform.glx',
        'OpenGL.platform.egl',
        'OpenGL.arrays',
        'OpenGL.arrays.ctypesarrays',
        'OpenGL.arrays.numpymodule',
        'freetype',
        'scipy',
        'psutil',
    ]
))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide2', 'PySide6', 'tkinter', '_tkinter', 'OpenGL_accelerate', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='vfx-player',
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
    icon='logo.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='vfx-player',
)
