"""
cx_Freeze setup script for Knack VFX Player
"""
import sys
import os
from cx_Freeze import setup, Executable

# Find VisPy library path to include GLSL shaders
import vispy
vispy_path = os.path.dirname(vispy.__file__)

# Include binaries from OpenImageIO site-package "bin" directory
# This ensures we match the version of the installed python bindings
import OpenImageIO
oiio_path = os.path.dirname(OpenImageIO.__file__)
oiio_bin = os.path.join(oiio_path, "bin")

include_files = [
    (vispy_path, "lib/vispy"),
    ("configs/ocio", "ocio"), # Map entire config directory to root/ocio
    ("logo.ico", "logo.ico"),
]

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
# Check next to python executable first
py_dir = os.path.dirname(sys.executable)
vc_dlls = ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"]
system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")

for dll in vc_dlls:
    src = os.path.join(py_dir, dll)
    if not os.path.exists(src):
        src = os.path.join(system32, dll)
    
    if os.path.exists(src):
        include_files.append((src, dll)) # Put in root next to exe


# Dependencies are automatically detected, but some modules need help
build_exe_options = {
    "packages": [
        "PyQt6",
        "vispy",
        "numpy",
        "cv2",
        "scipy",
        "imageio",
        "OpenImageIO",
        "PyOpenColorIO",
    ],
    "include_msvcr": True, # Try to include MSVC runtime (might not work on all versions)

    "includes": [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "vispy.app.backends._pyqt6",
        "vispy.visuals",
        "vispy.scene",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "PyQt5",
        "PySide2",
        "PySide6",
    ],
    "include_files": include_files,
    "zip_include_packages": ["*"],
    "zip_exclude_packages": ["vispy"],
}

# GUI applications require a different base on Windows
base = "Win32GUI" if sys.platform == "win32" else None
# base = None # Enable console for debugging

setup(
    name="Knack VFX Player",
    version="1.0",
    description="High-performance VFX sequence player with ACES color management",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="Knack VFX Player.exe",
            icon="logo.ico",
        )
    ],
)
