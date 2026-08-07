import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
from vispy import scene
from vispy.scene import visuals
from vispy.scene.visuals import create_visual_node
from vispy.gloo import Texture2D
from vispy.visuals.image import ImageVisual
from vispy.visuals.shaders import Function, FunctionChain
from vispy.visuals._scalable_textures import GPUScaledTexture2D

# Override parent class-level fragment shader template to strip the varying declaration.
# We redeclare varying vec2 v_texcoord; inside our custom _WIPE_GRADING_TEMPLATE 
# to make it visible inside helper functions without redeclaration conflicts.
if 'varying vec2 v_texcoord;' in ImageVisual._shaders['fragment']:
    ImageVisual._shaders['fragment'] = ImageVisual._shaders['fragment'].replace('varying vec2 v_texcoord;', '')

_WIPE_GRADING_TEMPLATE = """
varying vec2 v_texcoord;

vec4 apply_grading(vec4 color) {
    vec2 tc = v_texcoord;
    vec4 top_color = color;
    if ($wipe_enabled == 1) {
        if (tc.x > $wipe_ratio) {
            top_color = texture2D($texture_b, tc);
        }
    }
    float gain = pow(2.0, $exposure);
    top_color.rgb *= gain;
    top_color.rgb = max(top_color.rgb, 0.0);
    if ($gamma > 0.01) {
        top_color.rgb = pow(top_color.rgb, vec3(1.0 / $gamma));
    }
    if ($channel_mode == 1) {
        top_color.rgb = vec3(top_color.r);
    } else if ($channel_mode == 2) {
        top_color.rgb = vec3(top_color.g);
    } else if ($channel_mode == 3) {
        top_color.rgb = vec3(top_color.b);
    } else if ($channel_mode == 4) {
        top_color.rgb = vec3(top_color.a);
    }
    top_color.rgb = clamp(top_color.rgb, 0.0, 1.0);
    return top_color;
}
"""

class GradedWipeImageVisual(ImageVisual):
    def __init__(self, *args, **kwargs):
        self._grading_fn = Function(_WIPE_GRADING_TEMPLATE)
        self._grading_fn['exposure'] = 0.0
        self._grading_fn['gamma'] = 1.0
        self._grading_fn['channel_mode'] = 0
        self._grading_fn['wipe_ratio'] = 0.5
        self._grading_fn['wipe_enabled'] = 0
        self._texture_b = GPUScaledTexture2D(data=np.zeros((1, 1, 3), dtype=np.uint8), internalformat='auto')
        self._grading_fn['texture_b'] = self._texture_b
        super().__init__(*args, **kwargs)

    def _build_color_transform(self):
        # Bypass VisPy default fclim and fgamma completely to preserve HDR values
        null_fn = Function(self._func_templates['null_color_transform'])
        return FunctionChain(None, [null_fn, self._grading_fn])

    def set_data_b(self, data):
        if not data.flags['C_CONTIGUOUS']:
            data = np.ascontiguousarray(data)
        self._texture_b.set_data(data)

GradedWipeImage = create_visual_node(GradedWipeImageVisual)

try:
    import OpenGL.GL as gl
    _HAS_PYOPENGL = True
except ImportError:
    _HAS_PYOPENGL = False


class PBOTextureUploader:
    """Async OpenGL Pixel Buffer Object (PBO) ring buffer for zero-stutter GPU DMA texture uploads."""
    def __init__(self, pbo_count=2):
        self.pbo_count = pbo_count
        self.pbos = []
        self.pbo_index = 0
        self._current_size = 0

    def init_pbos(self, size_bytes):
        if self.pbos and self._current_size >= size_bytes:
            return
        self.cleanup()
        try:
            self.pbos = gl.glGenBuffers(self.pbo_count)
            for pbo in self.pbos:
                gl.glBindBuffer(gl.GL_PIXEL_UNPACK_BUFFER, pbo)
                gl.glBufferData(gl.GL_PIXEL_UNPACK_BUFFER, size_bytes, None, gl.GL_STREAM_DRAW)
            gl.glBindBuffer(gl.GL_PIXEL_UNPACK_BUFFER, 0)
            self._current_size = size_bytes
            self.pbo_index = 0
        except Exception:
            self.pbos = []

    def upload_async(self, texture_id, width, height, data_array, format_gl=gl.GL_RGB, type_gl=gl.GL_UNSIGNED_BYTE):
        if not self.pbos or data_array.nbytes > self._current_size:
            self.init_pbos(data_array.nbytes)
        if not self.pbos:
            return False

        try:
            # 1. Bind next PBO in ring to write data
            next_pbo = self.pbos[self.pbo_index]
            self.pbo_index = (self.pbo_index + 1) % self.pbo_count

            gl.glBindBuffer(gl.GL_PIXEL_UNPACK_BUFFER, next_pbo)
            gl.glBufferSubData(gl.GL_PIXEL_UNPACK_BUFFER, 0, data_array.nbytes, data_array)

            # 2. Bind target OpenGL texture and upload asynchronously from PBO
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
            gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, 0, 0, width, height, format_gl, type_gl, None)
            gl.glBindBuffer(gl.GL_PIXEL_UNPACK_BUFFER, 0)
            return True
        except Exception:
            try:
                gl.glBindBuffer(gl.GL_PIXEL_UNPACK_BUFFER, 0)
            except Exception:
                pass
            return False

    def cleanup(self):
        if self.pbos:
            try:
                gl.glDeleteBuffers(len(self.pbos), self.pbos)
            except Exception:
                pass
            self.pbos = []


class VispyViewport(QtWidgets.QWidget):
    """VisPy-based viewport with click interactions:
       - Single click: play/pause toggle
       - Double click: fullscreen toggle
    """
    # Custom signals for click interactions
    single_clicked = QtCore.pyqtSignal()
    double_clicked = QtCore.pyqtSignal()
    right_clicked = QtCore.pyqtSignal(QtCore.QPoint)
    pixel_probe_hover = QtCore.pyqtSignal(float, float) # image x, y
    stroke_finished = QtCore.pyqtSignal(list, tuple) # list of (x,y) points, color tuple

    def __init__(self, main_window=None, role='primary'):
        super().__init__()
        self.main_window = main_window
        self.role = role
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        
        self.canvas = scene.SceneCanvas(keys='interactive', show=False, parent=self)
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = 'panzoom'
        self.view.camera.aspect = 1.0
        self.view.camera.set_range(margin=0)
        
        # Image visual
        # Use our custom GradedWipeImage node supporting GPU grading & wipe compositing
        self.image_visual = GradedWipeImage(
            data=np.zeros((1, 1, 3), dtype=np.uint8),
            parent=self.view.scene, 
            method='auto',
            shading='simple',
            texture_format='auto'  # Uses GPUScaledTexture2D for direct GPU floats upload without CPU scaling/clamping
        )
        self.image_visual.interactive = True

        # PBO Async Texture Uploader
        if _HAS_PYOPENGL:
            self._pbo_uploader = PBOTextureUploader(pbo_count=2)
        
        # Layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.canvas.native)
        
        # Annotations (Drawing) Layer
        self._is_drawing = False
        self.draw_color = (1.0, 0.0, 0.0, 1.0) # Default Red
        self._current_stroke = []
        self._stroke_visual = None
        self._all_stroke_visuals = [] # References to active line visuals
        
        self._last_shape = None
        self._zoom = 1.0
        
        # Wire up click detection and canvas mouse events
        self._init_click_detection()
        
        # Intercept VisPy default key handling for Esc
        self.canvas.events.key_press.connect(self._on_canvas_key_press)

    def _on_canvas_key_press(self, event):
        """Consume Esc key at the VisPy level to prevent default behavior."""
        if event.key == 'Escape':
            if self.main_window:
                QtCore.QTimer.singleShot(0, self.main_window.close)
            event.handled = True

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Handle Qt-level key events; ensure Esc is consumed."""
        if event.key() == QtCore.Qt.Key.Key_Escape:
            if self.main_window:
                QtCore.QTimer.singleShot(0, self.main_window.close)
            event.accept()
            return
        super().keyPressEvent(event)

    def _ensure_shader_hooked(self):
        """No longer needed with Filter system, but kept as stub for compatibility."""
        pass

    def set_exposure(self, val: float):
        """val: exposure in stops."""
        self.image_visual._grading_fn['exposure'] = float(val)
        self.canvas.update()

    def set_gamma(self, val: float):
        """val: gamma value."""
        self.image_visual._grading_fn['gamma'] = float(val)
        self.canvas.update()

    def set_channel_mode(self, mode: str):
        """mode: RGB, R, G, B, A."""
        mapping = {'RGB': 0, 'R': 1, 'G': 2, 'B': 3, 'A': 4}
        self.image_visual._grading_fn['channel_mode'] = mapping.get(mode, 0)
        self.canvas.update()

    @property
    def is_drawing(self):
        return getattr(self, '_is_drawing', False)
        
    @is_drawing.setter
    def is_drawing(self, val: bool):
        self._is_drawing = val
        if hasattr(self, 'view') and hasattr(self.view, 'camera') and self.view.camera:
            self.view.camera.interactive = not val
        
    def _init_click_detection(self):
        """Initialize click detection and canvas mouse events. Called from __init__."""
        # Click detection (distinguish single vs double click)
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)  # Wait 250ms to distinguish single from double
        self._click_timer.timeout.connect(self._emit_single_click)
        self._pending_double = False
        
        # Connect VisPy canvas mouse events
        self.canvas.events.mouse_press.connect(self._on_canvas_mouse_press)
        self.canvas.events.mouse_release.connect(self._on_canvas_mouse_release)
        self.canvas.events.mouse_double_click.connect(self._on_canvas_double_click)
        self.canvas.events.mouse_move.connect(self._on_mouse_move)

    def _map_to_scene(self, screen_pos):
        """Map screen pixel coordinate to the exact pan/zoom World Scene coordinate."""
        tr = self.canvas.scene.node_transform(self.view.scene)
        scene_coords = tr.imap(screen_pos)
        return float(scene_coords[0]), float(scene_coords[1])

    def _map_to_image(self, screen_pos):
        """Map screen pixel coordinate to image local coordinate."""
        tr = self.canvas.scene.node_transform(self.image_visual)
        mapped = tr.imap(screen_pos)
        
        x = mapped[0]
        vispy_y = mapped[1]
        
        # Keep Y flipped for UI hover reporting probe values
        h = self._last_shape[0] if self._last_shape else 0
        y = h - vispy_y 
        
        return float(x), float(y), float(vispy_y)

    def _create_line_visual(self, pts_array):
        """Helper to create a line visual configured to always draw on top in the scene."""
        vis = visuals.Line(pos=pts_array, color=self.draw_color, width=3, method='gl', parent=self.view.scene)
        # Force it to draw over everything else without depth testing occlusion
        vis.order = 10
        vis.set_gl_state('translucent', depth_test=False)
        return vis

    def _on_mouse_move(self, event):
        if not self.image_visual.visible or self._last_shape is None:
            return
            
        try:
            # For probing
            x, y, vispy_y = self._map_to_image(event.pos)
            
            # For drawing (in pure World Scene space)
            scene_x, scene_y = self._map_to_scene(event.pos)
            
            # Draw Mode
            is_dragging = (event.button == 1) or (hasattr(event, 'buttons') and 1 in event.buttons) or getattr(event, 'is_dragging', False)
            if self.is_drawing and is_dragging and hasattr(self, '_current_stroke'):
                if len(self._current_stroke) < 10000:
                    self._current_stroke.append((scene_x, scene_y))
                
                # Update visual live
                if len(self._current_stroke) >= 2:
                    pts = np.array(self._current_stroke, dtype=np.float32)
                    if self._stroke_visual is None:
                        self._stroke_visual = self._create_line_visual(pts)
                        self._all_stroke_visuals.append(self._stroke_visual)
                    else:
                        self._stroke_visual.set_data(pos=pts, color=self.draw_color, width=3)
                
                event.handled = True
                return
            
            # Hover Probe Mode
            self.pixel_probe_hover.emit(x, y)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _on_canvas_mouse_press(self, event):
        """Handle single click on the canvas."""
        if event.button == 2:  # Right button
            pos = QtGui.QCursor.pos()
            self.right_clicked.emit(pos)
            event.handled = True
            return
        elif event.button == 1:  # Left button
            if self.is_drawing:
                try:
                    scene_x, scene_y = self._map_to_scene(event.pos)
                    self._current_stroke = [(scene_x, scene_y)]
                    self._stroke_visual = None
                    event.handled = True # Block pan/zoom while drawing
                except Exception as e:
                    import traceback
                    traceback.print_exc()
            else:
                # Start timer for single click toggle (cancelled if double click follows)
                if not self._click_timer.isActive():
                    self._click_timer.start()

    def _on_canvas_mouse_release(self, event):
        if event.button == 1 and self.is_drawing:
            if hasattr(self, '_current_stroke') and len(self._current_stroke) > 1:
                self.stroke_finished.emit(self._current_stroke, tuple(self.draw_color))
            self._current_stroke = []
            self._stroke_visual = None
            event.handled = True
    
    def _on_canvas_double_click(self, event):
        """Handle double click on the canvas."""
        if event.button == 1:
            self._click_timer.stop()  # Cancel pending single click
            self.double_clicked.emit()

    def _emit_single_click(self):
        """Emitted after timer confirms it was a single click, not double."""
        self.single_clicked.emit()

    def set_frame(self, frame):
        """frame: numpy array (H, W, C), uint8 [0, 255] or float32 [0, 1]."""
        if frame is None:
            self.image_visual.visible = False
            return
            
        self.image_visual.visible = True
        
        # Ensure array is C-contiguous
        if not frame.flags['C_CONTIGUOUS']:
            frame = np.ascontiguousarray(frame)
            
        h, w = frame.shape[:2]
        
        dtype_changed = not hasattr(self, '_last_dtype') or self._last_dtype != frame.dtype
        shape_changed = getattr(self, '_last_shape', None) != (h, w)

        if shape_changed or dtype_changed:
            self._last_shape = (h, w)
            self._last_dtype = frame.dtype
            
            # Recreate VisPy texture to match the new size and format (uint8 vs float32)
            self.image_visual._grading_fn['wipe_enabled'] = 0
            self.image_visual.set_data(frame)
            self.image_visual.transform = scene.transforms.STTransform(scale=(1, -1, 1), translate=(0, h, 0))
            self.fit_to_window()
            uploaded_pbo = True
        else:
            # Upload frame data (Async PBO or direct VisPy upload)
            uploaded_pbo = False
            if _HAS_PYOPENGL and hasattr(self, '_pbo_uploader') and hasattr(self.image_visual, '_texture'):
                try:
                    tex = self.image_visual._texture
                    if tex and hasattr(tex, 'id') and tex.id:
                        # Disable wipe mode during standard frame load
                        self.image_visual._grading_fn['wipe_enabled'] = 0
                        
                        fmt = gl.GL_RGBA if (len(frame.shape) > 2 and frame.shape[2] == 4) else gl.GL_RGB
                        dtype = gl.GL_FLOAT if frame.dtype == np.float32 else gl.GL_UNSIGNED_BYTE
                        uploaded_pbo = self._pbo_uploader.upload_async(tex.id, w, h, frame, fmt, dtype)
                except Exception:
                    uploaded_pbo = False

            if not uploaded_pbo:
                # Fallback to VisPy standard upload (zero-copy GPU flip preserved)
                self.image_visual._grading_fn['wipe_enabled'] = 0
                self.image_visual.set_data(frame)

        self.canvas.update()

    def set_annotations(self, strokes):
        """Draw a list of strokes for the current frame.
        strokes format: [ {'points': [(x,y), ...], 'color': (r,g,b,a)}, ... ]
        """
        # Clear existing
        for vis in getattr(self, '_all_stroke_visuals', []):
            vis.parent = None
        self._all_stroke_visuals = []
        
        if not strokes or self._last_shape is None:
            return
            
        for stroke in strokes:
            pts = stroke.get('points', [])
            color = stroke.get('color', (1,0,0,1))
            if len(pts) > 1:
                pts_array = np.array(pts, dtype=np.float32)
                vis = self._create_line_visual(pts_array)
                # Overwrite color since helper uses current UI color
                vis.set_data(color=color, width=3)
                self._all_stroke_visuals.append(vis)
            
    def composite_wipe(self, base_np, top_np, ratio: float):
        """GPU-side wipe composite. Both arrays loaded to GPU textures."""
        if base_np is None:
            self.set_frame(top_np)
            return
        if top_np is None:
            self.set_frame(base_np)
            return
            
        # 1. Update the base texture as usual
        self.set_frame(base_np)
        
        # 2. Re-scale/re-align the comparison top_np to match base texture dimensions if they differ
        h, w = base_np.shape[:2]
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

        # 3. Upload top_np to texture_b on GPU and enable GPU wipe shader mapping
        self.image_visual.set_data_b(top_np)
        self.image_visual._grading_fn['wipe_ratio'] = float(ratio)
        self.image_visual._grading_fn['wipe_enabled'] = 1
        self.canvas.update()

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
