# PyInstaller hook for OpenImageIO
# This hook helps PyInstaller collect OpenImageIO without crashing

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

# Collect all dynamic libraries and data files
datas = collect_data_files('OpenImageIO', include_py_files=False)
binaries = collect_dynamic_libs('OpenImageIO')

# Add hidden imports if needed
hiddenimports = []
