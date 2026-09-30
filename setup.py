"""
cx_Freeze setup script for VFX Review Player
"""
import sys
import os
import site
from cx_Freeze import setup, Executable

# Find site-packages directory
site_packages_dirs = site.getsitepackages()
if hasattr(site, 'getusersitepackages'):
    site_packages_dirs.append(site.getusersitepackages())

# Include PyAV (av) package path
import av
av_path = os.path.dirname(av.__file__)

# Base include files
include_files = [
    (av_path, "lib/av"),
    ("configs", "configs"),          # OCIO configs & LUTs (configs/ocio)
    ("LICENSE", "LICENSE"),
]
if os.path.exists("logo.ico"):
    include_files.append(("logo.ico", "logo.ico"))
if os.path.exists("logo.png"):
    include_files.append(("logo.png", "logo.png"))
if os.path.exists("bin/ffmpeg"):
    include_files.append(("bin/ffmpeg", "bin/ffmpeg"))

# Automatically find and include delvewheel / auditwheel .libs directories (e.g. av.libs, numpy.libs, scipy.libs)
for sp in site_packages_dirs:
    if os.path.exists(sp):
        for item in os.listdir(sp):
            if item.endswith(".libs"):
                src_path = os.path.join(sp, item)
                if os.path.isdir(src_path):
                    include_files.append((src_path, f"lib/{item}"))

# Include binaries from OpenImageIO site-package directory
try:
    import OpenImageIO
    oiio_path = os.path.dirname(OpenImageIO.__file__)
    for sub in ["bin", "lib", ".libs"]:
        p = os.path.join(oiio_path, sub)
        if os.path.exists(p):
            for filename in os.listdir(p):
                if filename.endswith((".dll", ".exe", ".so", ".so.1", ".so.2", ".so.3")):
                    source = os.path.join(p, filename)
                    target = os.path.join("lib", filename)
                    include_files.append((source, target))
except ImportError:
    pass

# Include binaries from PyOpenColorIO site-package directory
try:
    import PyOpenColorIO
    ocio_path = os.path.dirname(PyOpenColorIO.__file__)
    for sub in ["bin", "lib", ".libs"]:
        p = os.path.join(ocio_path, sub)
        if os.path.exists(p):
            for filename in os.listdir(p):
                if filename.endswith((".dll", ".exe", ".so", ".so.1", ".so.2", ".so.3")):
                    source = os.path.join(p, filename)
                    target = os.path.join("lib", filename)
                    include_files.append((source, target))
except ImportError:
    pass

# Include VC++ Runtime DLLs on Windows for portability
if sys.platform == "win32":
    py_dir = os.path.dirname(sys.executable)
    vc_dlls = ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"]
    system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")
    for dll in vc_dlls:
        src = os.path.join(py_dir, dll)
        if not os.path.exists(src):
            src = os.path.join(system32, dll)
        if os.path.exists(src):
            include_files.append((src, dll))

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
    "includes": [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "vispy.visuals",
        "vispy.scene",
        "vispy.util.fonts",
        "vispy.util.fonts._triage",
        "vispy.util.fonts._vispy_fonts",
        "vispy.util.fonts._freetype",
        "freetype",
        "av",
        "OpenGL",
        "OpenGL.platform",
        "OpenGL.platform.baseplatform",
        "OpenGL.platform.ctypesloader",
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

if sys.platform == "win32":
    build_exe_options["include_msvcr"] = True
    build_exe_options["includes"].extend([
        "vispy.util.fonts._win32",
        "OpenGL.platform.win32",
    ])

base = "Win32GUI" if sys.platform == "win32" else None
target_name = "VFX Review Player.exe" if sys.platform == "win32" else "vfx-player"
app_icon = "logo.ico" if sys.platform == "win32" else "logo.png"

# Read version from VERSION file if available
version = "1.1.4"
version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
if os.path.exists(version_file):
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                version = v
    except Exception:
        pass

setup(
    name="vfx-player",
    version=version,
    description="VFX Review Player - VFX Review, Playback & Media Delivery Platform",
    license="GPL-3.0-or-later",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name=target_name,
            icon=app_icon,
        )
    ],
)


