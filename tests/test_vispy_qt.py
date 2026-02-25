import sys
import numpy as np
from PyQt6 import QtWidgets
from vispy import scene
from vispy.scene import visuals

class TestVispyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VisPy Test")
        self.resize(800, 600)
        
        # Create canvas
        # keys='interactive' allows pan/zoom
        self.canvas = scene.SceneCanvas(keys='interactive', show=False, parent=self)
        self.view = self.canvas.central_widget.add_view()
        
        # Create image visual
        self.image = visuals.Image(parent=self.view.scene, method='subdivide')
        
        # Set dummy data
        data = np.random.rand(1024, 1024, 3).astype(np.float32)
        self.image.set_data(data)
        self.view.camera = 'panzoom'
        self.view.camera.set_range(margin=0)
        
        self.setCentralWidget(self.canvas.native)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = TestVispyWindow()
    win.show()
    print("VisPy window shown, closing in 3 seconds...")
    
    # Auto-close for test
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(3000, app.quit)
    
    app.exec()
