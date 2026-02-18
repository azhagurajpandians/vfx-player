import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
from vispy import scene
from vispy.scene import visuals

class VispyViewport(QtWidgets.QWidget):
    """VisPy-based viewport with click interactions:
       - Single click: play/pause toggle
       - Double click: fullscreen toggle
    """
    # Custom signals for click interactions
    single_clicked = QtCore.pyqtSignal()
    double_clicked = QtCore.pyqtSignal()

    def __init__(self, main_window=None, role='primary'):
        super().__init__()
        self.main_window = main_window
        self.role = role
        self.setAcceptDrops(True)
        
        self.canvas = scene.SceneCanvas(keys='interactive', show=False, parent=self)
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = 'panzoom'
        self.view.camera.aspect = 1.0
        self.view.camera.set_range(margin=0)
        
        # Image visual
        # Image visual (init with dummy 1x1 black frame to avoid NoneType shape errors)
        self.image_visual = visuals.Image(
            data=np.zeros((1, 1, 3), dtype=np.float32),
            parent=self.view.scene, 
            method='subdivide'
        )
        
        # Layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.canvas.native)
        
        self._last_shape = None
        self._zoom = 1.0
        
        # Click detection (distinguish single vs double click)
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)  # Wait 250ms to distinguish single from double
        self._click_timer.timeout.connect(self._emit_single_click)
        self._pending_double = False
        
        # Connect VisPy canvas mouse events
        self.canvas.events.mouse_press.connect(self._on_canvas_mouse_press)
        self.canvas.events.mouse_double_click.connect(self._on_canvas_double_click)

    def _on_canvas_mouse_press(self, event):
        """Handle single click on the canvas."""
        if event.button == 1:  # Left button
            # Start timer for single click (cancelled if double click follows)
            if not self._click_timer.isActive():
                self._click_timer.start()
    
    def _on_canvas_double_click(self, event):
        """Handle double click on the canvas."""
        if event.button == 1:
            self._click_timer.stop()  # Cancel pending single click
            self.double_clicked.emit()

    def _emit_single_click(self):
        """Emitted after timer confirms it was a single click, not double."""
        self.single_clicked.emit()

    def set_frame(self, frame):
        """frame: numpy array (H, W, C), float32 in [0, 1]."""
        if frame is None:
            self.image_visual.visible = False
            return
            
        self.image_visual.visible = True
        # Flip vertically for correct VisPy display (0,0 is bottom-left)
        self.image_visual.set_data(frame[::-1])
        
        # Auto-fit if first frame or size changed
        if self._last_shape != frame.shape[:2]:
            self._last_shape = frame.shape[:2]
            self.view.camera.set_range(margin=0)
            
    def composite_wipe(self, base_np, top_np, ratio: float):
        """CPU-side wipe composite. Both arrays: float32 0-1."""
        if base_np is None:
            self.set_frame(top_np)
            return
        if top_np is None:
            self.set_frame(base_np)
            return
            
        h, w = base_np.shape[:2]
        
        try:
            th, tw = top_np.shape[:2]
            if (th, tw) != (h, w):
                 temp = np.zeros_like(base_np)
                 sh = min(h, th)
                 sw = min(w, tw)
                 y0 = (h - sh) // 2
                 x0 = (w - sw) // 2
                 ty0 = (th - sh) // 2
                 tx0 = (tw - sw) // 2
                 temp[y0:y0+sh, x0:x0+sw] = top_np[ty0:ty0+sh, tx0:tx0+sw]
                 top_np = temp

            cut = int(w * ratio)
            cut = max(0, min(w, cut))
            
            comp = base_np.copy()
            comp[:, cut:] = top_np[:, cut:]
            self.set_frame(comp)
        except Exception:
            self.set_frame(base_np)

    def fit_to_window(self):
        if self._last_shape:
            h, w = self._last_shape
            self.view.camera.set_range(x=(0, w), y=(0, h), margin=0.01)
        else:
            self.view.camera.set_range(margin=0.01)
        self._zoom = 1.0

    def set_zoom(self, value: float):
        factor = value / self._zoom
        self._zoom = value
        self.view.camera.zoom(factor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        if paths and self.main_window:
            target = paths[0]
            if self.role == 'secondary':
                self.main_window.load_compare_media(target)
            else:
                self.main_window.load_media(target)
