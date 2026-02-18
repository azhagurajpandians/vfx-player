# PyInstaller hook for PyOpenColorIO
# This hook helps PyInstaller collect PyOpenColorIO without crashing

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

# Collect all dynamic libraries and data files
datas = collect_data_files('PyOpenColorIO', include_py_files=False)
binaries = collect_dynamic_libs('PyOpenColorIO')

# Add hidden imports if needed
hiddenimports = []
