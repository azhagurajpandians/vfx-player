import math
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


# ─────────────────────────────────────────────────────────────────
# Geometry helpers for shape tools
# ─────────────────────────────────────────────────────────────────

def _ellipse_points(x0, y0, x1, y1, steps=64) -> np.ndarray:
    """Return a closed polyline approximating an axis-aligned ellipse."""
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    rx = abs(x1 - x0) / 2.0
    ry = abs(y1 - y0) / 2.0
    angles = np.linspace(0, 2 * math.pi, steps + 1)
    xs = cx + rx * np.cos(angles)
    ys = cy + ry * np.sin(angles)
    return np.column_stack([xs, ys]).astype(np.float32)


def _rect_points(x0, y0, x1, y1) -> np.ndarray:
    """Return a closed polyline for a rectangle."""
    return np.array([
        [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]
    ], dtype=np.float32)


def _arrow_points(x0, y0, x1, y1, head_size: float = 12.0):
    """
    Return (shaft_pts, head_pts) for an arrow from (x0,y0) to (x1,y1).
    shaft_pts: 2-point line for the main body
    head_pts:  3-point triangle for the arrowhead (not closed)
    """
    shaft = np.array([[x0, y0], [x1, y1]], dtype=np.float32)

    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return shaft, None

    # Unit vector along shaft
    ux = dx / length
    uy = dy / length
    # Perpendicular
    px = -uy
    py = ux

    # Arrow head: base at (x1,y1) stepped back by head_size along shaft
    base_x = x1 - ux * head_size
    base_y = y1 - uy * head_size
    half = head_size * 0.45

    head = np.array([
        [base_x + px * half, base_y + py * half],
        [x1, y1],
        [base_x - px * half, base_y - py * half],
    ], dtype=np.float32)

    return shaft, head


def _eraser_radius_sq(draw_width: int) -> float:
    """Return squared eraser hit radius in scene units."""
    return (max(draw_width, 8) * 2.5) ** 2


# ─────────────────────────────────────────────────────────────────
# PBO Uploader
# ─────────────────────────────────────────────────────────────────

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
            next_pbo = self.pbos[self.pbo_index]
            self.pbo_index = (self.pbo_index + 1) % self.pbo_count

            gl.glBindBuffer(gl.GL_PIXEL_UNPACK_BUFFER, next_pbo)
            gl.glBufferSubData(gl.GL_PIXEL_UNPACK_BUFFER, 0, data_array.nbytes, data_array)

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


# ─────────────────────────────────────────────────────────────────
# VispyViewport
# ─────────────────────────────────────────────────────────────────

class VispyViewport(QtWidgets.QWidget):
    """VisPy-based viewport with click interactions:
       - Single click: play/pause toggle
       - Double click: fullscreen toggle

    Annotation layer now supports multiple tools:
        pen, line, arrow, rect, ellipse, text, eraser
    """
    # Custom signals for click interactions
    single_clicked = QtCore.pyqtSignal()
    double_clicked = QtCore.pyqtSignal()
    right_clicked = QtCore.pyqtSignal(QtCore.QPoint)
    pixel_probe_hover = QtCore.pyqtSignal(float, float)   # image x, y
    stroke_finished = QtCore.pyqtSignal(dict)             # full stroke dict

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
        self.image_visual = GradedWipeImage(
            data=np.zeros((1, 1, 3), dtype=np.uint8),
            parent=self.view.scene, 
            method='auto',
            shading='simple',
            texture_format='auto'
        )
        self.image_visual.interactive = True

        # PBO Async Texture Uploader
        if _HAS_PYOPENGL:
            self._pbo_uploader = PBOTextureUploader(pbo_count=2)
        
        # Layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.canvas.native)
        
        # ── Annotation / Drawing state ───────────────────────────
        self._is_drawing = False
        self.draw_tool = 'pen'                # active tool
        self.draw_color = (1.0, 0.3, 0.3, 1.0)  # default: vivid red
        self.draw_width = 3                   # default stroke width

        self._current_stroke = []             # accumulates points during drag
        self._stroke_start = None             # (x, y) for two-point tools
        self._stroke_visual = None            # live preview visual (current drag)
        self._stroke_visual_extra = None      # arrowhead preview visual
        self._all_stroke_visuals = []         # references to committed stroke visuals
        self._text_overlays: list[dict] = []  # committed text annotation widgets

        # Text input widget (inline overlay)
        self._text_input: QtWidgets.QLineEdit | None = None

        self._last_shape = None
        self._zoom = 1.0
        
        # Wire up click detection and canvas mouse events
        self._init_click_detection()
        
        # Intercept VisPy default key handling for Esc
        self.canvas.events.key_press.connect(self._on_canvas_key_press)

    # ─────────────────────────────────────────────────────────────
    # Key handling
    # ─────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────
    # Shader / grading API
    # ─────────────────────────────────────────────────────────────

    def _ensure_shader_hooked(self):
        """No longer needed with Filter system, but kept as stub for compatibility."""
        pass

    def set_exposure(self, val: float):
        self.image_visual._grading_fn['exposure'] = float(val)
        self.canvas.update()

    def set_gamma(self, val: float):
        self.image_visual._grading_fn['gamma'] = float(val)
        self.canvas.update()

    def set_channel_mode(self, mode: str):
        mapping = {'RGB': 0, 'R': 1, 'G': 2, 'B': 3, 'A': 4}
        self.image_visual._grading_fn['channel_mode'] = mapping.get(mode, 0)
        self.canvas.update()

    # ─────────────────────────────────────────────────────────────
    # Drawing mode property
    # ─────────────────────────────────────────────────────────────

    @property
    def is_drawing(self):
        return getattr(self, '_is_drawing', False)

    @is_drawing.setter
    def is_drawing(self, val: bool):
        self._is_drawing = val
        if not val:
            self._finish_text_input()
        if hasattr(self, 'view') and hasattr(self.view, 'camera') and self.view.camera:
            self.view.camera.interactive = not val
        
    # ─────────────────────────────────────────────────────────────
    # Click detection init
    # ─────────────────────────────────────────────────────────────

    def _init_click_detection(self):
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)
        self._click_timer.timeout.connect(self._emit_single_click)
        self._pending_double = False
        
        self.canvas.events.mouse_press.connect(self._on_canvas_mouse_press)
        self.canvas.events.mouse_release.connect(self._on_canvas_mouse_release)
        self.canvas.events.mouse_double_click.connect(self._on_canvas_double_click)
        self.canvas.events.mouse_move.connect(self._on_mouse_move)

    # ─────────────────────────────────────────────────────────────
    # Coordinate mapping
    # ─────────────────────────────────────────────────────────────

    def _map_to_scene(self, screen_pos):
        """Map canvas screen position (event.pos) to view.scene coordinates (0,0 bottom-left of image)."""
        tr = self.canvas.scene.node_transform(self.view.scene)
        mapped = tr.map(screen_pos)
        return float(mapped[0]), float(mapped[1])

    def _map_to_image(self, screen_pos):
        """Map canvas screen position (event.pos) to image pixel coordinates (0,0 top-left of image)."""
        tr = self.canvas.scene.node_transform(self.image_visual)
        mapped = tr.map(screen_pos)
        x = float(mapped[0])
        y = float(mapped[1])
        h = self._last_shape[0] if self._last_shape else 0
        vispy_y = h - y
        return x, y, vispy_y

    def _scene_to_screen(self, scene_x: float, scene_y: float):
        """Map scene coordinate back to canvas screen pixel position."""
        tr = self.canvas.scene.node_transform(self.view.scene)
        mapped = tr.imap([scene_x, scene_y, 0, 1])
        return int(mapped[0]), int(mapped[1])


    # ─────────────────────────────────────────────────────────────
    # VisPy visual factory helpers
    # ─────────────────────────────────────────────────────────────

    def _create_line_visual(self, pts_array: np.ndarray, color=None, width: int = None) -> visuals.Line:
        """Create a Line visual that always renders on top."""
        c = color if color is not None else self.draw_color
        w = width if width is not None else self.draw_width
        vis = visuals.Line(pos=pts_array, color=c, width=w, method='gl', parent=self.view.scene)
        vis.order = 10
        vis.set_gl_state('translucent', depth_test=False)
        return vis

    def _remove_live_preview(self):
        """Remove in-progress preview visuals without committing them."""
        if self._stroke_visual is not None:
            self._stroke_visual.parent = None
            self._stroke_visual = None
        if self._stroke_visual_extra is not None:
            self._stroke_visual_extra.parent = None
            self._stroke_visual_extra = None

    # ─────────────────────────────────────────────────────────────
    # Mouse events
    # ─────────────────────────────────────────────────────────────

    def _on_canvas_mouse_press(self, event):
        if event.button == 2:  # Right-click
            pos = QtGui.QCursor.pos()
            self.right_clicked.emit(pos)
            event.handled = True
            return

        if event.button == 1:
            # If text input widget is active, commit it before starting a new action
            if self._text_input is not None:
                self._finish_text_input()
            if self.is_drawing:
                try:
                    scene_x, scene_y = self._map_to_scene(event.pos)

                    if self.draw_tool == 'eraser':
                        # Immediate erase on press
                        self._erase_at(scene_x, scene_y)
                        event.handled = True
                        return

                    if self.draw_tool == 'text':
                        # Show inline text input at click position
                        self._start_text_input(scene_x, scene_y, event.pos)
                        event.handled = True
                        return

                    # For all other tools: record start point
                    self._stroke_start = (scene_x, scene_y)
                    self._current_stroke = [(scene_x, scene_y)]
                    self._remove_live_preview()
                    event.handled = True
                except Exception:
                    import traceback; traceback.print_exc()
            else:
                if not self._click_timer.isActive():
                    self._click_timer.start()

    def _on_mouse_move(self, event):
        try:
            # Always attempt coordinate mapping, even outside image bounds.
            # Drawing must work across the FULL canvas area.
            scene_x, scene_y = self._map_to_scene(event.pos)

            is_dragging = (
                (event.button == 1)
                or (hasattr(event, 'buttons') and 1 in event.buttons)
                or getattr(event, 'is_dragging', False)
            )

            if self.is_drawing and is_dragging and self._stroke_start is not None:
                x0, y0 = self._stroke_start
                self._update_live_preview(x0, y0, scene_x, scene_y)
                event.handled = True
                return

            # Hover pixel probe — only when image is loaded
            if self.image_visual.visible and self._last_shape is not None:
                x, y, _vy = self._map_to_image(event.pos)
                self.pixel_probe_hover.emit(x, y)
        except Exception:
            import traceback; traceback.print_exc()

    def _on_canvas_mouse_release(self, event):
        if event.button == 1 and self.is_drawing:
            if self.draw_tool in ('eraser', 'text'):
                event.handled = True
                return

            if self._stroke_start is None:
                return

            try:
                scene_x, scene_y = self._map_to_scene(event.pos)
                x0, y0 = self._stroke_start

                stroke = self._build_stroke(x0, y0, scene_x, scene_y)
                if stroke:
                    self._remove_live_preview()
                    self._commit_stroke_visual(stroke)
                    self.stroke_finished.emit(stroke)
                else:
                    self._remove_live_preview()
            except Exception:
                import traceback; traceback.print_exc()

            self._stroke_start = None
            self._current_stroke = []
            event.handled = True
    
    def _on_canvas_double_click(self, event):
        if event.button == 1:
            self._click_timer.stop()
            self.double_clicked.emit()

    def _emit_single_click(self):
        self.single_clicked.emit()

    # ─────────────────────────────────────────────────────────────
    # Live preview during drag
    # ─────────────────────────────────────────────────────────────

    def _update_live_preview(self, x0: float, y0: float, x1: float, y1: float):
        """Refresh the in-progress stroke preview visual for the active tool."""
        tool = self.draw_tool

        if tool == 'pen':
            # Accumulate points and UPDATE the existing visual in-place.
            # Do NOT create a new visual every move frame (that leaks visuals).
            self._current_stroke.append((x1, y1))
            pts = np.array(self._current_stroke, dtype=np.float32)
            if len(pts) >= 2:
                if self._stroke_visual is None:
                    # First move: create the live visual
                    self._stroke_visual = self._create_line_visual(pts)
                else:
                    # Subsequent moves: update in-place (no new allocation)
                    self._stroke_visual.set_data(
                        pos=pts,
                        color=self.draw_color,
                        width=self.draw_width,
                    )
                self.canvas.update()
            return

        # ── Shape tools: remove old preview and create fresh ──────
        self._remove_live_preview()

        if tool == 'line':
            pts = np.array([[x0, y0], [x1, y1]], dtype=np.float32)
            self._stroke_visual = self._create_line_visual(pts)

        elif tool == 'arrow':
            shaft, head = _arrow_points(x0, y0, x1, y1, head_size=self.draw_width * 5)
            self._stroke_visual = self._create_line_visual(shaft)
            if head is not None:
                self._stroke_visual_extra = self._create_line_visual(head)

        elif tool == 'rect':
            pts = _rect_points(x0, y0, x1, y1)
            self._stroke_visual = self._create_line_visual(pts)

        elif tool == 'ellipse':
            pts = _ellipse_points(x0, y0, x1, y1)
            self._stroke_visual = self._create_line_visual(pts)

    # ─────────────────────────────────────────────────────────────
    # Stroke building + committing
    # ─────────────────────────────────────────────────────────────

    def _build_stroke(self, x0: float, y0: float, x1: float, y1: float) -> dict | None:
        """Build the final stroke dict for the active tool."""
        tool = self.draw_tool
        color = tuple(self.draw_color)
        w = self.draw_width

        if tool == 'pen':
            pts = self._current_stroke[:]
            if len(pts) < 2:
                return None
            return {'tool': 'pen', 'points': pts, 'points2': None,
                    'color': color, 'width': w, 'text': None}

        if tool == 'line':
            if abs(x1 - x0) < 1 and abs(y1 - y0) < 1:
                return None
            return {'tool': 'line',
                    'points': [(x0, y0), (x1, y1)], 'points2': None,
                    'color': color, 'width': w, 'text': None}

        if tool == 'arrow':
            if abs(x1 - x0) < 1 and abs(y1 - y0) < 1:
                return None
            head_size = w * 5
            shaft, head = _arrow_points(x0, y0, x1, y1, head_size=head_size)
            head_pts = head.tolist() if head is not None else None
            return {'tool': 'arrow',
                    'points': shaft.tolist(), 'points2': head_pts,
                    'color': color, 'width': w, 'text': None}

        if tool == 'rect':
            if abs(x1 - x0) < 1 and abs(y1 - y0) < 1:
                return None
            pts = _rect_points(x0, y0, x1, y1)
            return {'tool': 'rect', 'points': pts.tolist(), 'points2': None,
                    'color': color, 'width': w, 'text': None}

        if tool == 'ellipse':
            if abs(x1 - x0) < 1 and abs(y1 - y0) < 1:
                return None
            pts = _ellipse_points(x0, y0, x1, y1)
            return {'tool': 'ellipse', 'points': pts.tolist(), 'points2': None,
                    'color': color, 'width': w, 'text': None}

        return None

    def _commit_stroke_visual(self, stroke: dict):
        """Render a finished stroke dict into VisPy visuals."""
        tool = stroke.get('tool', 'pen')
        pts = stroke.get('points', [])
        pts2 = stroke.get('points2')
        color = stroke.get('color', (1, 0, 0, 1))
        width = stroke.get('width', 3)

        if not pts:
            return

        pts_array = np.array(pts, dtype=np.float32)

        if tool in ('pen', 'line', 'rect', 'ellipse'):
            if len(pts_array) >= 2:
                vis = self._create_line_visual(pts_array, color=color, width=width)
                self._all_stroke_visuals.append(vis)

        elif tool == 'arrow':
            if len(pts_array) >= 2:
                vis = self._create_line_visual(pts_array, color=color, width=width)
                self._all_stroke_visuals.append(vis)
            if pts2 and len(pts2) >= 2:
                head_array = np.array(pts2, dtype=np.float32)
                vis2 = self._create_line_visual(head_array, color=color, width=width)
                self._all_stroke_visuals.append(vis2)

        elif tool == 'text':
            # Text is handled by the text overlay widget, not VisPy visuals
            # (already added via _commit_text_stroke)
            pass

    # ─────────────────────────────────────────────────────────────
    # Eraser tool
    # ─────────────────────────────────────────────────────────────

    def _erase_at(self, scene_x: float, scene_y: float):
        """
        Notify main_window to erase the topmost stroke near (scene_x, scene_y).
        We emit a special stroke dict with tool='eraser' so main_window can pop
        from the annotation list and call set_annotations to refresh.
        """
        eraser_stroke = {
            'tool': 'eraser',
            'points': [(scene_x, scene_y)],
            'points2': None,
            'color': (0, 0, 0, 0),
            'width': self.draw_width,
            'text': None,
        }
        self.stroke_finished.emit(eraser_stroke)

    # ─────────────────────────────────────────────────────────────
    # Text tool
    # ─────────────────────────────────────────────────────────────

    def _start_text_input(self, scene_x: float, scene_y: float, screen_pos):
        """Show an inline QLineEdit for text input, positioned over click point."""
        if self._text_input is not None:
            self._finish_text_input()

        # Map scene coord back to screen coord within the canvas native widget
        sx, sy = self._scene_to_screen(scene_x, scene_y)

        self._text_input = QtWidgets.QLineEdit(self.canvas.native)
        self._text_input.setPlaceholderText("Type text, press Enter")
        r, g, b, a = self.draw_color
        qc = QtGui.QColor.fromRgbF(r, g, b, a)
        self._text_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0,0,0,180);
                color: {qc.name()};
                border: 1px solid {qc.name()};
                border-radius: 3px;
                font-size: {max(11, self.draw_width * 3)}px;
                font-weight: bold;
                padding: 2px 6px;
            }}
        """)
        self._text_input.resize(200, 28)
        self._text_input.move(max(0, sx), max(0, sy))
        self._text_input.show()
        self._text_input.setFocus()

        self._text_scene_pos = (scene_x, scene_y)

        self._text_input.returnPressed.connect(self._finish_text_input)
        self._text_input.installEventFilter(self)

    def finish_text_input(self):
        """Public API to commit any open text input widget."""
        self._finish_text_input()

    def _finish_text_input(self):
        """Commit the typed text as an annotation stroke."""
        if self._text_input is None:
            return

        text = self._text_input.text().strip()
        self._text_input.hide()
        self._text_input.deleteLater()
        self._text_input = None

        if text and hasattr(self, '_text_scene_pos') and self._text_scene_pos:
            x, y = self._text_scene_pos
            stroke = {
                'tool': 'text',
                'points': [(x, y)],
                'points2': None,
                'color': tuple(self.draw_color),
                'width': self.draw_width,
                'text': text,
            }
            # Render the text visual
            self._render_text_visual(stroke)
            self.stroke_finished.emit(stroke)

        self._text_scene_pos = None

    def _render_text_visual(self, stroke: dict):
        """Add a VisPy Text visual for a text stroke."""
        pts = stroke.get('points', [])
        text = stroke.get('text', '')
        color = stroke.get('color', (1, 1, 0, 1))
        width = stroke.get('width', 3)
        if not pts or not text:
            return
        x, y = pts[0]
        font_size = max(10, width * 4)
        try:
            vis = visuals.Text(
                text=text,
                color=color,
                font_size=font_size,
                pos=(x, y),
                parent=self.view.scene,
                anchor_x='left',
                anchor_y='top',
            )
            vis.order = 11
            vis.set_gl_state('translucent', depth_test=False)
            self._all_stroke_visuals.append(vis)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        """Catch Escape, FocusOut, or Return on the text input widget to commit or cancel it."""
        if self._text_input is not None and obj is self._text_input:
            if event.type() == QtCore.QEvent.Type.FocusOut:
                self._finish_text_input()
                return True
            elif event.type() == QtCore.QEvent.Type.KeyPress:
                if event.key() == QtCore.Qt.Key.Key_Escape:
                    # Cancel text input without committing
                    self._text_input.hide()
                    self._text_input.deleteLater()
                    self._text_input = None
                    self._text_scene_pos = None
                    return True
                elif event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    self._finish_text_input()
                    return True
        return super().eventFilter(obj, event)

    # ─────────────────────────────────────────────────────────────
    # Public annotation API
    # ─────────────────────────────────────────────────────────────

    def set_annotations(self, strokes: list):
        """
        Redraw all strokes for the current frame.

        strokes format (per item):
        {
            'tool': 'pen'|'line'|'arrow'|'rect'|'ellipse'|'text'|'eraser',
            'points': [(x,y), ...],
            'points2': [(x,y), ...] | None,   # arrowhead, etc.
            'color': (r,g,b,a),
            'width': int,
            'text': str | None,
        }
        Also accepts legacy format: {'points': [...], 'color': (...)}
        """
        # Clear existing stroke visuals
        for vis in list(self._all_stroke_visuals):
            vis.parent = None
        self._all_stroke_visuals = []

        # Also remove in-progress preview
        self._remove_live_preview()

        if not strokes or self._last_shape is None:
            self.canvas.update()
            return
            
        for stroke in strokes:
            tool = stroke.get('tool', 'pen')
            pts = stroke.get('points', [])
            color = stroke.get('color', (1, 0, 0, 1))
            width = stroke.get('width', 3)

            if tool == 'text':
                self._render_text_visual(stroke)
                continue

            if tool == 'eraser':
                continue  # Eraser doesn't draw anything

            if not pts or len(pts) < 2:
                continue

            pts_array = np.array(pts, dtype=np.float32)
            vis = self._create_line_visual(pts_array, color=color, width=width)
            self._all_stroke_visuals.append(vis)

            # Arrow head (points2)
            pts2 = stroke.get('points2')
            if tool == 'arrow' and pts2 and len(pts2) >= 2:
                head_array = np.array(pts2, dtype=np.float32)
                vis2 = self._create_line_visual(head_array, color=color, width=width)
                self._all_stroke_visuals.append(vis2)

        self.canvas.update()

    def get_frame_with_annotations(self) -> np.ndarray | None:
        """
        Return a numpy uint8 RGB array of the current viewport with annotations baked in.
        Uses VisPy's canvas.render() which captures the full OpenGL scene.
        """
        try:
            # Force a canvas update so all annotation visuals are rendered
            self.canvas.update()
            QtWidgets.QApplication.processEvents()
            rendered = self.canvas.render(alpha=False)
            if rendered is None:
                return None
            if len(rendered.shape) == 3 and rendered.shape[2] == 4:
                return np.ascontiguousarray(rendered[:, :, :3])
            return np.ascontiguousarray(rendered)
        except Exception:
            import traceback; traceback.print_exc()
            return None

    # ─────────────────────────────────────────────────────────────
    # Frame display
    # ─────────────────────────────────────────────────────────────

    def set_frame(self, frame):
        """frame: numpy array (H, W, C), uint8 [0, 255] or float32 [0, 1]."""
        if frame is None:
            self.image_visual.visible = False
            return
            
        self.image_visual.visible = True
        
        if not frame.flags['C_CONTIGUOUS']:
            frame = np.ascontiguousarray(frame)
            
        h, w = frame.shape[:2]
        
        dtype_changed = not hasattr(self, '_last_dtype') or self._last_dtype != frame.dtype
        shape_changed = getattr(self, '_last_shape', None) != (h, w)

        if shape_changed or dtype_changed:
            self._last_shape = (h, w)
            self._last_dtype = frame.dtype
            
            self.image_visual._grading_fn['wipe_enabled'] = 0
            self.image_visual.set_data(frame)
            self.image_visual.transform = scene.transforms.STTransform(scale=(1, -1, 1), translate=(0, h, 0))
            self.fit_to_window()
            uploaded_pbo = True
        else:
            uploaded_pbo = False
            if _HAS_PYOPENGL and hasattr(self, '_pbo_uploader') and hasattr(self.image_visual, '_texture'):
                try:
                    tex = self.image_visual._texture
                    if tex and hasattr(tex, 'id') and tex.id:
                        self.image_visual._grading_fn['wipe_enabled'] = 0
                        fmt = gl.GL_RGBA if (len(frame.shape) > 2 and frame.shape[2] == 4) else gl.GL_RGB
                        dtype = gl.GL_FLOAT if frame.dtype == np.float32 else gl.GL_UNSIGNED_BYTE
                        uploaded_pbo = self._pbo_uploader.upload_async(tex.id, w, h, frame, fmt, dtype)
                except Exception:
                    uploaded_pbo = False

            if not uploaded_pbo:
                self.image_visual._grading_fn['wipe_enabled'] = 0
                self.image_visual.set_data(frame)

        self.canvas.update()

    # ─────────────────────────────────────────────────────────────
    # Wipe composite
    # ─────────────────────────────────────────────────────────────

    def composite_wipe(self, base_np, top_np, ratio: float):
        """GPU-side wipe composite. Both arrays loaded to GPU textures."""
        if base_np is None:
            self.set_frame(top_np)
            return
        if top_np is None:
            self.set_frame(base_np)
            return
            
        self.set_frame(base_np)
        
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

        self.image_visual.set_data_b(top_np)
        self.image_visual._grading_fn['wipe_ratio'] = float(ratio)
        self.image_visual._grading_fn['wipe_enabled'] = 1
        self.canvas.update()

    # ─────────────────────────────────────────────────────────────
    # Camera helpers
    # ─────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────
    # Drag-and-drop
    # ─────────────────────────────────────────────────────────────

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
