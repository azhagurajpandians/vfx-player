# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import glob

sys.setrecursionlimit(5000)

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all

version = "1.1.4"
if os.path.exists("VERSION"):
    try:
        with open("VERSION", "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                version = v
    except Exception:
        pass

datas = [
    ("configs", "configs"),
    ("core", "core"),
    ("gui", "gui"),
    ("logo.png", "."),
    ("LICENSE", "."),
]

if os.path.exists("VERSION"):
    datas.append(("VERSION", "."))

if os.path.exists("logo.icns"):
    datas.append(("logo.icns", "."))

if os.path.exists("bin/ffmpeg/mac"):
    datas.append(("bin/ffmpeg/mac", "bin/ffmpeg/mac"))
elif os.path.exists("bin/ffmpeg/darwin"):
    datas.append(("bin/ffmpeg/darwin", "bin/ffmpeg/darwin"))
elif os.path.exists("bin/ffmpeg"):
    datas.append(("bin/ffmpeg", "bin/ffmpeg"))

binaries = []

# Collect cv2, numpy, imageio, and vispy resources
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")
np_datas, np_binaries, np_hiddenimports = collect_all("numpy")
imgio_datas, imgio_binaries, imgio_hiddenimports = collect_all("imageio")
vispy_datas, vispy_binaries, vispy_hiddenimports = collect_all("vispy")

# Collect OIIO/OCIO if installed in the build environment
try:
    oiio_datas = collect_data_files("OpenImageIO", include_py_files=True)
    oiio_binaries = collect_dynamic_libs("OpenImageIO")
except Exception:
    oiio_datas, oiio_binaries = [], []

try:
    ocio_datas = collect_data_files("PyOpenColorIO", include_py_files=True)
    ocio_binaries = collect_dynamic_libs("PyOpenColorIO")
except Exception:
    ocio_datas, ocio_binaries = [], []

try:
    av_datas, av_binaries, av_hiddenimports = collect_all("av")
except Exception:
    av_datas, av_binaries, av_hiddenimports = [], [], []

datas += vispy_datas + oiio_datas + ocio_datas + av_datas
binaries += cv2_binaries + np_binaries + imgio_binaries + vispy_binaries + oiio_binaries + ocio_binaries + av_binaries

hiddenimports = list(set(
    cv2_hiddenimports + np_hiddenimports + imgio_hiddenimports + vispy_hiddenimports + av_hiddenimports + [
        "cv2",
        "cv2.typing",
        "vispy",
        "vispy.visuals",
        "vispy.scene",
        "vispy.app.backends._pyqt6",
        "OpenGL",
        "OpenGL.GL",
        "OpenGL.GLU",
        "OpenGL.platform",
        "OpenGL.platform.darwin",
        "OpenGL.arrays",
        "OpenGL.arrays.ctypesarrays",
        "OpenGL.arrays.numpymodule",
        "freetype",
        "scipy",
        "psutil",
    ]
))

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PySide2", "PySide6", "tkinter", "_tkinter", "OpenGL_accelerate", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

icon_path = "logo.icns" if os.path.exists("logo.icns") else "logo.png"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vfx-player",
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
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vfx-player",
)

app = BUNDLE(
    coll,
    name="VFX Player.app",
    icon=icon_path if icon_path.endswith(".icns") else None,
    bundle_identifier="com.knacktools.vfxplayer",
    info_plist={
        "CFBundleName": "VFX Player",
        "CFBundleDisplayName": "VFX Player",
        "CFBundleIdentifier": "com.knacktools.vfxplayer",
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSMinimumSystemVersion": "11.0",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "NSHumanReadableCopyright": "Copyright © 2026 Knack VFX. All rights reserved.",
    },
)
