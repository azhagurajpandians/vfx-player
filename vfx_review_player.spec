# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import glob

sys.setrecursionlimit(5000)

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all

datas = [
    ('configs', 'configs'),
    ('core', 'core'),
    ('gui', 'gui')
]
binaries = []

# Collect cv2, numpy, imageio, and vispy resources
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all('cv2')
np_datas, np_binaries, np_hiddenimports = collect_all('numpy')
imgio_datas, imgio_binaries, imgio_hiddenimports = collect_all('imageio')
vispy_datas, vispy_binaries, vispy_hiddenimports = collect_all('vispy')

# Collect OIIO/OCIO using PyInstaller functions
try:
    oiio_datas = collect_data_files('OpenImageIO', include_py_files=True)
    oiio_binaries = collect_dynamic_libs('OpenImageIO')
except Exception:
    oiio_datas = []
    oiio_binaries = []

try:
    ocio_datas = collect_data_files('PyOpenColorIO', include_py_files=True)
    ocio_binaries = collect_dynamic_libs('PyOpenColorIO')
except Exception:
    ocio_datas = []
    ocio_binaries = []

datas += vispy_datas + oiio_datas + ocio_datas

# Add .pyd and dependent DLLs from python environment site-packages
site_packages = r'C:\Users\raj\AppData\Local\Programs\Python\Python310\lib\site-packages'
oiio_pyd = os.path.join(site_packages, 'OpenImageIO', 'OpenImageIO.cp310-win_amd64.pyd')
ocio_pyd = os.path.join(site_packages, 'PyOpenColorIO', 'PyOpenColorIO.pyd')

if os.path.exists(oiio_pyd):
    oiio_binaries.append((oiio_pyd, 'OpenImageIO'))
if os.path.exists(ocio_pyd):
    ocio_binaries.append((ocio_pyd, 'PyOpenColorIO'))

oiio_bin = os.path.join(site_packages, 'OpenImageIO', 'bin')
if os.path.exists(oiio_bin):
    for dll in glob.glob(os.path.join(oiio_bin, '*.dll')):
        oiio_binaries.append((dll, '.'))

ocio_bin = os.path.join(site_packages, 'PyOpenColorIO', 'bin')
if os.path.exists(ocio_bin):
    for dll in glob.glob(os.path.join(ocio_bin, '*.dll')):
        ocio_binaries.append((dll, '.'))

binaries += cv2_binaries + np_binaries + imgio_binaries + vispy_binaries + oiio_binaries + ocio_binaries

hiddenimports = list(set(cv2_hiddenimports + np_hiddenimports + imgio_hiddenimports + \
                         vispy_hiddenimports + \
                         ['cv2', 'cv2.typing', 'vispy']))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/rthook_oiio_ocio.py'],
    excludes=['PyQt5', 'PySide2', 'PySide6', 'PyOpenColorIO', 'OpenImageIO'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VFX Review Player',
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
    icon=['logo.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VFX Review Player',
)
