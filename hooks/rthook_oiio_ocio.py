# Runtime hook for OpenImageIO and PyOpenColorIO
# This ensures the _internal directory is in sys.path so these modules can be imported

import sys
import os

# Get the directory where the executable is running from
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    bundle_dir = sys._MEIPASS
    
    # Add the bundle directory to sys.path if not already there
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)
