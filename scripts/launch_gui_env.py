import os, sys

# Ensure project root importable
root = os.path.dirname(os.path.dirname(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

test_exr = os.environ.get('VFXPLAYER_TEST_EXR')
# Set test env vars
os.environ['VFXPLAYER_ALLOW_EXR'] = '1'
os.environ['VFXPLAYER_DEBUG'] = '1'
os.environ['VFXPLAYER_OIIO_BIN'] = r'D:\exrtojpg\VFXPlayer\bin\oiio\windows'

# Optional: set VFXPLAYER_TEST_EXR to a real EXR path to auto-load
test_exr = os.environ.get('VFXPLAYER_TEST_EXR')

def _preload_exr(path):
    """Run the exr_worker subprocess synchronously before creating the GUI
    to avoid invoking native image libraries while the GUI is in an
    input-sync state. Returns PNG bytes on success, otherwise None."""
    import tempfile, subprocess
    if not os.path.isfile(path):
        return None
    worker_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'exr_worker.py')
    tf = tempfile.NamedTemporaryFile(prefix='vfxp_exr_', suffix='.png', delete=False)
    tf.close()
    out_path = tf.name
    cmd = [sys.executable, worker_script, path, out_path]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wait_ms = int(os.environ.get('VFXPLAYER_PROC_TIMEOUT_MS', '5000'))
        try:
            out, err = proc.communicate(timeout=(wait_ms/1000.0))
        except Exception:
            proc.kill(); out, err = proc.communicate()
        if proc.returncode == 0:
            try:
                with open(out_path, 'rb') as f:
                    data = f.read()
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                return data
            except Exception:
                print('Failed to read PNG output from worker')
                try:
                    with open(out_path + '.err', 'rb') as f:
                        print(f.read().decode('utf-8', errors='ignore'))
                except Exception:
                    pass
        else:
            print('exr_worker returned', proc.returncode)
            try:
                print(err.decode('utf-8', errors='ignore'))
            except Exception:
                pass
    except Exception:
        print('Failed to start subprocess exr_worker')
    return None


try:
    # If test_exr provided, preload it before creating the QApplication
    preloaded = None
    if test_exr:
        print('Preloading EXR (before GUI):', test_exr)
        preloaded = _preload_exr(test_exr)
        if preloaded is None:
            print('Preload failed or returned no frame')

    from PyQt6.QtWidgets import QApplication
    from PyQt6 import QtGui
    from core.player_core import PlayerCore
    from gui.main_window import MainWindow
    from PyQt6.QtCore import QTimer

    app = QApplication([])
    core = PlayerCore()
    win = MainWindow(core)
    win.show()

    # If preloaded frame exists, set it now on the GUI thread
    if preloaded is not None:
        try:
            # If worker returned PNG bytes, build QImage here and apply directly
            if isinstance(preloaded, (bytes, bytearray)):
                qimg = QtGui.QImage.fromData(preloaded)
                if qimg and not qimg.isNull():
                    vp = win.viewport
                    vp._qimage = qimg
                    vp._orig_size = (qimg.width(), qimg.height())
                    try:
                        vp._update_fit_zoom()
                    except Exception:
                        pass
                    vp._update_pixmap()
                    print('Set preloaded frame to viewport (PNG)')
                else:
                    print('Failed to build QImage from preloaded bytes; falling back')
                    win.viewport.set_frame(preloaded)
            else:
                win.viewport.set_frame(preloaded)
                print('Set preloaded frame to viewport')
        except Exception as e:
            print('Failed to set preloaded frame:', e)

    # Quit after 5 seconds to avoid hanging test runs
    QTimer.singleShot(5000, app.quit)
    rc = app.exec()
    print('App exited with rc', rc)
    sys.exit(rc)
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
