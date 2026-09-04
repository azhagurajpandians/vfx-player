"""
cx_Freeze setup script for Knack VFX Player
"""
import sys
import os
import site
from cx_Freeze import setup, Executable

# Find site-packages directory
site_packages = site.getsitepackages()[-1]

# Include PyAV (av) package path
import av
av_path = os.path.dirname(av.__file__)

# Base include files
include_files = [
    (av_path, "lib/av"),
    ("configs", "configs"),          # OCIO configs & LUTs (configs/ocio)
    ("bin/ffmpeg", "bin/ffmpeg"),    # Bundled FFmpeg & ffprobe binaries
    ("logo.ico", "logo.ico"),
    ("LICENSE", "LICENSE"),
]

# Automatically find and include delvewheel .libs directories (e.g. av.libs, numpy.libs, scipy.libs)
if os.path.exists(site_packages):
    for item in os.listdir(site_packages):
        if item.endswith(".libs"):
            src_path = os.path.join(site_packages, item)
            if os.path.isdir(src_path):
                include_files.append((src_path, f"lib/{item}"))

# Include binaries from OpenImageIO site-package "bin" directory
import OpenImageIO
oiio_path = os.path.dirname(OpenImageIO.__file__)
oiio_bin = os.path.join(oiio_path, "bin")

# Include binaries from PyOpenColorIO site-package "bin" directory
import PyOpenColorIO
ocio_path = os.path.dirname(PyOpenColorIO.__file__)
ocio_bin = os.path.join(ocio_path, "bin")

if os.path.exists(ocio_bin):
    for filename in os.listdir(ocio_bin):
        if filename.endswith(".dll") or filename.endswith(".exe"):
            source = os.path.join(ocio_bin, filename)
            target = os.path.join("lib", filename)
            include_files.append((source, target))

if os.path.exists(oiio_bin):
    for filename in os.listdir(oiio_bin):
        if filename.endswith(".dll") or filename.endswith(".exe"):
            source = os.path.join(oiio_bin, filename)
            target = os.path.join("lib", filename)
            include_files.append((source, target))
elif os.path.exists(os.path.join(oiio_path, "lib")):
     # Fallback for some installs where dlls are in lib
     oiio_lib = os.path.join(oiio_path, "lib")
     for filename in os.listdir(oiio_lib):
        if filename.endswith(".dll"):
            source = os.path.join(oiio_lib, filename)
            target = os.path.join("lib", filename)
            include_files.append((source, target))

# Manually include VC++ Runtime DLLs for portability
py_dir = os.path.dirname(sys.executable)
vc_dlls = ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"]
system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")

for dll in vc_dlls:
    src = os.path.join(py_dir, dll)
    if not os.path.exists(src):
        src = os.path.join(system32, dll)
    
    if os.path.exists(src):
        include_files.append((src, dll)) # Put in root next to exe

import freetype
freetype_path = os.path.dirname(freetype.__file__)
include_files.append((freetype_path, "lib/freetype"))

# Build options
build_exe_options = {
    "packages": [
        "PyQt6",
        "vispy",
        "freetype",
        "numpy",
        "cv2",
        "scipy",
        "imageio",
        "OpenImageIO",
        "PyOpenColorIO",
        "av",
        "OpenGL",
        "OpenGL.platform",
        "OpenGL.arrays",
        "OpenGL.GL",
    ],
    "include_msvcr": True,
    "includes": [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "vispy.visuals",
        "vispy.scene",
        "vispy.util.fonts",
        "vispy.util.fonts._triage",
        "vispy.util.fonts._vispy_fonts",
        "vispy.util.fonts._win32",
        "vispy.util.fonts._freetype",
        "freetype",
        "av",
        "OpenGL",
        "OpenGL.platform",
        "OpenGL.platform.baseplatform",
        "OpenGL.platform.ctypesloader",
        "OpenGL.platform.win32",
        "OpenGL.platform.glx",
        "OpenGL.platform.darwin",
        "OpenGL.platform.egl",
        "OpenGL.platform.osmesa",
        "OpenGL.platform.entrypoint31",
        "OpenGL.arrays",
        "OpenGL.arrays.arraydatatype",
        "OpenGL.arrays.arrayhelpers",
        "OpenGL.arrays.buffers",
        "OpenGL.arrays.ctypesarrays",
        "OpenGL.arrays.ctypesparameters",
        "OpenGL.arrays.ctypespointers",
        "OpenGL.arrays.formathandler",
        "OpenGL.arrays.lists",
        "OpenGL.arrays.nones",
        "OpenGL.arrays.numbers",
        "OpenGL.arrays.numpybuffers",
        "OpenGL.arrays.numpymodule",
        "OpenGL.arrays.strings",
        "OpenGL.arrays.vbo",
        "OpenGL.arrays._arrayconstants",
        "OpenGL.arrays._buffers",
        "OpenGL.arrays._strings",
        "OpenGL.GL",
        "OpenGL.GL.shaders",
        "OpenGL.GLU",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "PyQt5",
        "PySide2",
        "PySide6",
        "OpenGL_accelerate",
    ],
    "include_files": include_files,
    "zip_include_packages": ["*"],
    "zip_exclude_packages": [
        "av",
        "vispy",
        "freetype",
        "numpy",
        "scipy",
        "cv2",
        "imageio",
        "OpenImageIO",
        "PyOpenColorIO",
        "PyQt6",
        "OpenGL",
    ],
}

base = "Win32GUI" if sys.platform == "win32" else None

setup(
    name="VFX Review Player",
    version="1.0",
    description="High-performance VFX sequence player with ACES color management",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="VFX Review Player.exe",
            icon="logo.ico",
        )
    ],
)


