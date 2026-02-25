import os, sys, subprocess, tempfile

# Minimal reproducer: request PNG bytes from exr_worker (stdout) and build QImage.fromData
root = os.path.dirname(os.path.dirname(__file__))
worker = os.path.join(root, 'scripts', 'exr_worker.py')
if not os.path.exists(worker):
    print('exr_worker not found at', worker)
    sys.exit(2)

if len(sys.argv) > 1:
    exr = sys.argv[1]
else:
    exr = os.environ.get('VFXPLAYER_TEST_EXR')

if not exr or not os.path.exists(exr):
    print('Please provide EXR path as first arg or set VFXPLAYER_TEST_EXR')
    sys.exit(2)

cmd = [sys.executable, worker, exr, '-']
print('Running worker:', cmd)
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
out, err = proc.communicate(timeout=10)
if proc.returncode != 0:
    print('Worker failed:', proc.returncode)
    print(err.decode('utf-8', errors='ignore'))
    sys.exit(3)

print('Got', len(out), 'bytes from worker')

# Now create a tiny Qt app and QImage.fromData
from PyQt6 import QtWidgets, QtGui, QtCore
app = QtWidgets.QApplication([])
qimg = QtGui.QImage.fromData(out)
print('QImage isNull?', qimg.isNull())
if qimg.isNull():
    print('Failed to build QImage from bytes')
    sys.exit(4)

w = QtWidgets.QLabel()
w.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
pm = QtGui.QPixmap.fromImage(qimg)
w.setPixmap(pm)
w.resize(pm.width(), pm.height())
w.show()
QtCore.QTimer.singleShot(3000, app.quit)
rc = app.exec()
print('App exited rc', rc)

sys.exit(0)
