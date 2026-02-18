"""VFXPlayer application entry point."""

import os
import sys

# CRITICAL: Fix for OpenImageIO/OCIO delay-loaded dependencies
# These libraries use LoadLibrary() which doesn't check the application directory by default on Python 3.8+
def setup_ocio_runtime():
    """Configures the runtime environment for OpenColorIO and DLLs."""
    import sys
    import os

    if hasattr(sys, "_MEIPASS"):
        # PyInstaller root
        root = sys._MEIPASS
    else:
        # Standard python or cx_Freeze root
        root = os.path.dirname(os.path.abspath(__file__))

    # 1. DLL Visibility (Critical for Windows)
    if sys.platform == 'win32':
        try:
            os.add_dll_directory(root)
            # cx_Freeze puts some DLLs in lib
            lib_path = os.path.join(root, 'lib')
            if os.path.exists(lib_path):
                os.add_dll_directory(lib_path)
        except Exception:
            pass
        
        # Legacy PATH update for subprocesses/older loads
        os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")

    # 2. OCIO Configuration (Critical for PyOpenColorIO)
    # We mapped 'configs/ocio' to 'ocio' in setup.py
    ocio_config_path = os.path.join(root, "ocio", "config.ocio")
    
    if os.path.exists(ocio_config_path):
        os.environ["OCIO"] = ocio_config_path
        # print(f"DEBUG: Set OCIO env to {os.environ['OCIO']}") # Debug only
    else:
        # Fallback to local source structure if running from source
        local_config = os.path.join(root, "configs", "ocio", "config.ocio")
        if os.path.exists(local_config):
             os.environ["OCIO"] = local_config
    
    return root # Return root for external use if needed

# Initialize environment before importing image libraries
base_path = setup_ocio_runtime()

print(f"DEBUG: Base path for DLL search: {base_path}")

# Helper function to log to file
def log_debug(msg):
    try:
        with open("debug_log.txt", "a") as f:
            f.write(msg + "\n")
    except:
        pass

log_debug("DEBUG: Starting VFX Player...")
# input("Press Enter to continue...") # Commented out input for build automation, or enable for debug

# Pre-load OCIO to avoid DLL conflicts with PyQt6
try:
    log_debug("DEBUG: Importing OpenImageIO...")
    import OpenImageIO as oiio
    log_debug(f"DEBUG: OpenImageIO imported successfully: {oiio.__file__}")
except ImportError as e:
    log_debug(f"ERROR: Could not import OpenImageIO: {e}")
    oiio = None

try:
    log_debug("DEBUG: Importing PyOpenColorIO...")
    import PyOpenColorIO as OCIO
    log_debug(f"DEBUG: PyOpenColorIO imported successfully: {OCIO.__file__}")
except ImportError as e:
    log_debug(f"ERROR: Could not import PyOpenColorIO: {e}")
    OCIO = None
except Exception as e:
    log_debug(f"ERROR: Exception during PyOpenColorIO import: {e}")
    pass

import argparse
from PyQt6 import QtWidgets
from core.player_core import PlayerCore
from gui.main_window import MainWindow



def _get_cache_capacity(cli_value: int | None) -> int:
    if cli_value is not None:
        return max(0, int(cli_value))
    # Environment override
    env_val = os.environ.get("VFXPLAYER_CACHE_CAPACITY") or os.environ.get("VFXPLAYER_CACHE")
    if env_val:
        try:
            return max(0, int(env_val))
        except Exception:
            pass
    return 500


def main():
    # Global exception handler
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # Log to temp file
        import tempfile
        import traceback
        log_path = os.path.join(tempfile.gettempdir(), 'vfxplayer_crash.log')
        
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("VFXPlayer Crash Log\n")
            f.write("===================\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
            
        # Show error dialog
        try:
            app = QtWidgets.QApplication.instance()
            if not app:
                app = QtWidgets.QApplication(sys.argv)
            QtWidgets.QMessageBox.critical(None, "VFXPlayer Crash", 
                f"An unhandled exception occurred.\nLog saved to: {log_path}\n\nError: {exc_value}")
        except:
            pass
            
    sys.excepthook = handle_exception

    try:
        parser = argparse.ArgumentParser(add_help=True)
        parser.add_argument("--cache", type=int, default=None, help="LRU cache capacity (frames). Default 500; or set VFXPLAYER_CACHE_CAPACITY env var.")
        args, _ = parser.parse_known_args()

        # Ensure a QApplication exists before any QWidget
        qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

        cap = _get_cache_capacity(args.cache)
        core = PlayerCore(cache_capacity=cap)
        window = MainWindow(core)
        window.show()
        sys.exit(qt_app.exec())
    except Exception:
        # Catch exceptions during startup too
        sys.excepthook(*sys.exc_info())


if __name__ == "__main__":
    main()
