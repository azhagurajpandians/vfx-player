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
    
    // 1. Exposure (Master Gain)
    float gain = pow(2.0, $exposure);
    top_color.rgb *= gain;
    
    // 2. ASC CDL Slope & Offset
    top_color.rgb = (top_color.rgb * $slope) + $offset;
    top_color.rgb = max(top_color.rgb, vec3(0.0));
    
    // 3. ASC CDL Power
    top_color.rgb = pow(top_color.rgb, $power);
    
    // 4. ASC CDL Saturation
    float luma = dot(top_color.rgb, vec3(0.2126, 0.7152, 0.0722));
    top_color.rgb = vec3(luma) + $saturation * (top_color.rgb - vec3(luma));
    
    // 5. Gamma
    if ($gamma > 0.01) {
        top_color.rgb = pow(top_color.rgb, vec3(1.0 / $gamma));
    }
    
    // 6. Channel Isolation
    if ($channel_mode == 1) {
        top_color.rgb = vec3(top_color.r);
    } else if ($channel_mode == 2) {
        top_color.rgb = vec3(top_color.g);
    } else if ($channel_mode == 3) {
        top_color.rgb = vec3(top_color.b);
    } else if ($channel_mode == 4) {
        top_color.rgb = vec3(top_color.a);
    } else if ($channel_mode == 5) {
        top_color.rgb = vec3(luma);
    }

    // 7. Alpha / Transparency Mode
    if ($alpha_mode == 1) { // Grayscale Alpha
        top_color.rgb = vec3(top_color.a);
    } else if ($alpha_mode == 2) { // VFX Checkerboard
        vec2 check_coord = floor(gl_FragCoord.xy / 16.0);
        float check_pattern = mod(check_coord.x + check_coord.y, 2.0);
        vec3 bg = mix(vec3(0.18), vec3(0.28), check_pattern);
        top_color.rgb = mix(bg, top_color.rgb, top_color.a);
    } else if ($alpha_mode == 3) { // Black background
        top_color.rgb = top_color.rgb * top_color.a;
    } else if ($alpha_mode == 4) { // White background
        top_color.rgb = mix(vec3(1.0), top_color.rgb, top_color.a);
    }

    // 8. False Color Exposure Heatmap (10 Zones)
    if ($false_color_enabled == 1) {
        float fc_luma = dot(top_color.rgb, vec3(0.2126, 0.7152, 0.0722));
        vec3 fc;
        if (fc_luma < 0.02) {
            fc = vec3(0.5, 0.0, 0.5);   // Purple: Crushed blacks (<2%)
        } else if (fc_luma < 0.10) {
            fc = vec3(0.0, 0.3, 1.0);   // Blue: Shadows (2%-10%)
        } else if (fc_luma < 0.25) {
            fc = vec3(0.0, 0.8, 0.8);   // Cyan: Low mids (10%-25%)
        } else if (fc_luma < 0.38) {
            fc = vec3(0.3, 0.3, 0.3);   // Dark Gray: Sub-mid (25%-38%)
        } else if (fc_luma < 0.45) {
            fc = vec3(0.1, 0.85, 0.2);  // Green: 18% Middle Gray (38%-45%)
        } else if (fc_luma < 0.52) {
            fc = vec3(0.5, 0.5, 0.5);   // Mid Gray (45%-52%)
        } else if (fc_luma < 0.58) {
            fc = vec3(1.0, 0.55, 0.65); // Pink: Skin tones (52%-58%)
        } else if (fc_luma < 0.75) {
            fc = vec3(0.65, 0.65, 0.65);// High Mids (58%-75%)
        } else if (fc_luma < 0.85) {
            fc = vec3(1.0, 0.9, 0.0);   // Yellow: High highlights (75%-85%)
        } else if (fc_luma < 0.98) {
            fc = vec3(1.0, 0.5, 0.0);   // Orange: Near clipping (85%-98%)
        } else {
            fc = vec3(1.0, 0.0, 0.0);   // Red: Clipped highlights (>=98%)
        }
        top_color.rgb = fc;
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
        self._grading_fn['alpha_mode'] = 0
        self._grading_fn['false_color_enabled'] = 0
        self._grading_fn['wipe_ratio'] = 0.5
        self._grading_fn['wipe_enabled'] = 0
        self._grading_fn['slope'] = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self._grading_fn['offset'] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._grading_fn['power'] = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self._grading_fn['saturation'] = 1.0
        self._texture_b = GPUScaledTexture2D(data=np.zeros((1, 1, 3), dtype=np.uint8), internalformat='auto')
        self._texture_b.set_clim('auto')
        self._grading_fn['texture_b'] = self._texture_b
        super().__init__(*args, **kwargs)

    def _build_color_transform(self):
        # Bypass VisPy default fclim and fgamma completely to preserve HDR values
        null_fn = Function(self._func_templates['null_color_transform'])
        return FunctionChain(None, [null_fn, self._grading_fn])

    def set_data_b(self, data):
        if data is None:
            return
        if not data.flags['C_CONTIGUOUS']:
            data = np.ascontiguousarray(data)
        if getattr(self._texture_b, '_clim', None) is None:
            self._texture_b.set_clim('auto')
        try:
            self._texture_b.set_data(data)
        except Exception:
            self._texture_b = GPUScaledTexture2D(data=data, internalformat='auto')
            self._texture_b.set_clim('auto')
            self._grading_fn['texture_b'] = self._texture_b

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


class FalseColorLegend(QtWidgets.QFrame):
    """Floating transparent overlay displaying the 10-zone False Color exposure key."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 22, 215);
                border: 1px solid #323238;
                border-radius: 6px;
                padding: 4px 6px;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        title = QtWidgets.QLabel("<b>FALSE COLOR (IRE)</b>")
        title.setStyleSheet("color: #0a84ff; font-size: 10px; font-weight: bold;")
        layout.addWidget(title)

        zones = [
            ("#ff0000", "Clipping (>98%)"),
            ("#ff8000", "Near Clip (85-98%)"),
            ("#ffe600", "Highs (75-85%)"),
            ("#ff8ca6", "Skin (52-58%)"),
            ("#1ad933", "18% Gray (38-45%)"),
            ("#00cccc", "Low Mids (10-25%)"),
            ("#004dff", "Shadows (2-10%)"),
            ("#800080", "Black Crush (<2%)"),
        ]

        for color_hex, label_text in zones:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            swatch = QtWidgets.QFrame()
            swatch.setFixedSize(12, 10)
            swatch.setStyleSheet(f"background-color: {color_hex}; border: 1px solid rgba(255,255,255,0.25); border-radius: 2px;")
            lbl = QtWidgets.QLabel(label_text)
            row.addWidget(swatch)
            row.addWidget(lbl)
            row.addStretch()
            layout.addLayout(row)


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

    def __init__(self, main_window=None, role='primary', slot_index: int = 0):
        super().__init__()
        self.main_window = main_window
        self.role = role
        self.slot_index = slot_index
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        
        self.canvas = scene.SceneCanvas(keys=None, show=False, parent=self)
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = 'panzoom'
        self.view.camera.aspect = 1.0
        self.view.camera.set_range(margin=0)
        self.view.camera.viewbox_key_event = lambda event: None
        
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
        self._show_guides = False
        self._show_guide_center = True
        self._show_guide_thirds = True
        self._show_guide_action = True
        self._show_guide_title = True
        self._guide_visuals = []
        
        self._false_color_enabled = False
        self._false_color_legend = FalseColorLegend(self)
        self._false_color_legend.hide()
        
        # Wire up click detection and canvas mouse events
        self._init_click_detection()
        
        # Intercept VisPy default key handling for Esc
        self.canvas.events.key_press.connect(self._on_canvas_key_press)

        # Ensure canvas native widget forwards drag and drop to VispyViewport
        if hasattr(self.canvas, 'native') and self.canvas.native:
            self.canvas.native.setAcceptDrops(True)
            self.canvas.native.dragEnterEvent = self.dragEnterEvent
            self.canvas.native.dragMoveEvent = self.dragMoveEvent
            self.canvas.native.dragLeaveEvent = self.dragLeaveEvent
            self.canvas.native.dropEvent = self.dropEvent

        # Slot Identifier Badge (shown in multi-view grid modes: 2-up, 4-up, 6-up)
        self.slot_badge = QtWidgets.QLabel(f"SLOT {self.slot_index + 1}", self)
        self.slot_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(18, 18, 20, 200);
                color: #60a5fa;
                border: 1px solid #2563eb;
                border-radius: 4px;
                font-family: monospace;
                font-size: 11px;
                font-weight: bold;
                padding: 3px 8px;
            }
        """)
        self.slot_badge.move(12, 12)
        self.slot_badge.hide()

        # Drop Target Overlay (visible when hovering drag from playlist or explorer)
        self._drop_overlay = QtWidgets.QLabel(f"Drop to Play in Slot {self.slot_index + 1}", self)
        self._drop_overlay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._drop_overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 58, 138, 175);
                color: #ffffff;
                font-size: 15px;
                font-weight: bold;
                border: 2px dashed #60a5fa;
                border-radius: 8px;
            }
        """)
        self._drop_overlay.hide()

    def set_slot_badge(self, visible: bool, title: str = None):
        if hasattr(self, 'slot_badge'):
            if title:
                self.slot_badge.setText(title)
            else:
                self.slot_badge.setText(f"SLOT {self.slot_index + 1}")
            self.slot_badge.setVisible(visible)
            if visible:
                self.slot_badge.adjustSize()
                self.slot_badge.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_false_color_legend()
        if hasattr(self, '_drop_overlay') and self._drop_overlay.isVisible():
            self._drop_overlay.setGeometry(8, 8, max(10, self.width() - 16), max(10, self.height() - 16))
        if hasattr(self, 'slot_badge') and self.slot_badge.isVisible():
            self.slot_badge.move(12, 12)
            self.slot_badge.raise_()

    def _reposition_false_color_legend(self):
        if hasattr(self, '_false_color_legend') and self._false_color_legend.isVisible():
            self._false_color_legend.adjustSize()
            self._false_color_legend.move(max(10, self.width() - self._false_color_legend.width() - 15), 15)
            self._false_color_legend.raise_()

    # ─────────────────────────────────────────────────────────────
    # Key handling
    # ─────────────────────────────────────────────────────────────

    def _on_canvas_key_press(self, event):
        """Consume Esc key at the VisPy level to prevent default behavior, and block Backspace from camera reset."""
        if self._text_input is not None or event.key in ('Backspace', 'backspace'):
            event.handled = True
            return

        if event.key == 'Escape':
            if self._text_input is not None:
                self._cancel_text_input()
            elif self.main_window:
                if getattr(self.main_window, 'fullscreen', False):
                    QtCore.QTimer.singleShot(0, lambda: self.main_window._toggle_fullscreen(False))
                elif getattr(self, 'is_drawing', False):
                    QtCore.QTimer.singleShot(0, self.main_window._toggle_annotate_mode)
            event.handled = True
        elif event.key in ('/', '\\', 'Slash', 'slash'):
            self.fit_to_window()
            if self.main_window:
                if hasattr(self.main_window, 'viewport_b') and self.main_window.viewport_b:
                    self.main_window.viewport_b.fit_to_window()
                if hasattr(self.main_window, '_update_zoom_label'):
                    self.main_window._update_zoom_label()
            event.handled = True

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Handle Qt-level key events; ensure Esc exits fullscreen or cancels annotation."""
        if event.key() == QtCore.Qt.Key.Key_Escape:
            if self._text_input is not None:
                self._cancel_text_input()
                event.accept()
                return
            if self.main_window:
                if getattr(self.main_window, 'fullscreen', False):
                    QtCore.QTimer.singleShot(0, lambda: self.main_window._toggle_fullscreen(False))
                    event.accept()
                    return
                elif getattr(self, 'is_drawing', False):
                    QtCore.QTimer.singleShot(0, self.main_window._toggle_annotate_mode)
                    event.accept()
                    return
            event.accept()
            return
        elif event.key() in (QtCore.Qt.Key.Key_Slash, QtCore.Qt.Key.Key_Backslash):
            self.fit_to_window()
            if self.main_window:
                if hasattr(self.main_window, 'viewport_b') and self.main_window.viewport_b:
                    self.main_window.viewport_b.fit_to_window()
                if hasattr(self.main_window, '_update_zoom_label'):
                    self.main_window._update_zoom_label()
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
        mapping = {'RGB': 0, 'R': 1, 'G': 2, 'B': 3, 'A': 4, 'Luma': 5}
        self.image_visual._grading_fn['channel_mode'] = mapping.get(mode, 0)
        self.canvas.update()

    def set_alpha_mode(self, mode: str):
        mapping = {'RGB': 0, 'Alpha': 1, 'Checkerboard': 2, 'Black': 3, 'White': 4}
        self.image_visual._grading_fn['alpha_mode'] = mapping.get(mode, 0)
        self.canvas.update()

    def set_false_color(self, enabled: bool):
        self._false_color_enabled = bool(enabled)
        self.image_visual._grading_fn['false_color_enabled'] = 1 if enabled else 0
        if hasattr(self, '_false_color_legend'):
            self._false_color_legend.setVisible(self._false_color_enabled)
            if self._false_color_enabled:
                self._reposition_false_color_legend()
        self.canvas.update()

    def set_cdl_params(self, slope: tuple, offset: tuple, power: tuple, saturation: float):
        self.image_visual._grading_fn['slope'] = np.array(slope, dtype=np.float32)
        self.image_visual._grading_fn['offset'] = np.array(offset, dtype=np.float32)
        self.image_visual._grading_fn['power'] = np.array(power, dtype=np.float32)
        self.image_visual._grading_fn['saturation'] = float(saturation)
        self.canvas.update()

    def set_guides_enabled(self, enabled: bool):
        self._show_guides = enabled
        self._update_safe_guides()

    def set_guides_config(self, center: bool, thirds: bool, action: bool, title: bool):
        self._show_guide_center = center
        self._show_guide_thirds = thirds
        self._show_guide_action = action
        self._show_guide_title = title
        self._update_safe_guides()

    def _create_guide_line(self, pts_array: np.ndarray, color, width: float = 2.0) -> visuals.Line:
        """Create a safe guide line with depth testing disabled so it always renders on top."""
        vis = visuals.Line(pos=pts_array, color=color, width=width, method='gl', parent=self.view.scene)
        vis.order = 20
        vis.set_gl_state('translucent', depth_test=False)
        return vis

    def _update_safe_guides(self):
        if hasattr(self, '_guide_visuals'):
            for vis in self._guide_visuals:
                try:
                    vis.parent = None
                except Exception:
                    pass
        self._guide_visuals = []

        if not getattr(self, '_show_guides', False):
            self.canvas.update()
            return

        if self._last_shape is None:
            if hasattr(self, 'image_visual') and hasattr(self.image_visual, '_data') and self.image_visual._data is not None:
                d = self.image_visual._data
                if hasattr(d, 'shape') and len(d.shape) >= 2 and d.shape[0] > 1 and d.shape[1] > 1:
                    self._last_shape = (d.shape[0], d.shape[1])
            if self._last_shape is None and self.main_window and hasattr(self.main_window, 'core') and self.main_window.core.media:
                sz = self.main_window.core.media.size
                if sz and sz[0] > 0 and sz[1] > 0:
                    self._last_shape = (sz[1], sz[0])

        if self._last_shape is None:
            return

        h, w = self._last_shape
        color_cross = (1.0, 0.25, 0.25, 0.95)   # Vibrant red center crosshair
        color_thirds = (0.2, 0.75, 1.0, 0.75)   # Clean blue-cyan rule of thirds
        color_action = (0.0, 1.0, 0.65, 0.90)   # High-visibility mint green (90% action safe)
        color_title = (1.0, 0.85, 0.0, 0.90)    # High-visibility gold yellow (80% title safe)

        if getattr(self, '_show_guide_center', True):
            cx = float(w) / 2.0
            cy = float(h) / 2.0
            v_pts = np.array([[cx, float(h) * 0.44], [cx, float(h) * 0.56]], dtype=np.float32)
            h_pts = np.array([[float(w) * 0.45, cy], [float(w) * 0.55, cy]], dtype=np.float32)
            v_line = self._create_guide_line(v_pts, color=color_cross, width=2.0)
            h_line = self._create_guide_line(h_pts, color=color_cross, width=2.0)
            self._guide_visuals.extend([v_line, h_line])

        if getattr(self, '_show_guide_thirds', True):
            x1, x2 = float(w) / 3.0, 2.0 * float(w) / 3.0
            y1, y2 = float(h) / 3.0, 2.0 * float(h) / 3.0
            t1 = self._create_guide_line(np.array([[x1, 0.0], [x1, float(h)]], dtype=np.float32), color=color_thirds, width=1.5)
            t2 = self._create_guide_line(np.array([[x2, 0.0], [x2, float(h)]], dtype=np.float32), color=color_thirds, width=1.5)
            t3 = self._create_guide_line(np.array([[0.0, y1], [float(w), y1]], dtype=np.float32), color=color_thirds, width=1.5)
            t4 = self._create_guide_line(np.array([[0.0, y2], [float(w), y2]], dtype=np.float32), color=color_thirds, width=1.5)
            self._guide_visuals.extend([t1, t2, t3, t4])

        if getattr(self, '_show_guide_action', True):
            ax1, ax2 = 0.05 * float(w), 0.95 * float(w)
            ay1, ay2 = 0.05 * float(h), 0.95 * float(h)
            rect_act = np.array([
                [ax1, ay1], [ax2, ay1],
                [ax2, ay2], [ax1, ay2],
                [ax1, ay1]
            ], dtype=np.float32)
            act_line = self._create_guide_line(rect_act, color=color_action, width=2.0)
            self._guide_visuals.append(act_line)

        if getattr(self, '_show_guide_title', True):
            tx1, tx2 = 0.10 * float(w), 0.90 * float(w)
            ty1, ty2 = 0.10 * float(h), 0.90 * float(h)
            rect_title = np.array([
                [tx1, ty1], [tx2, ty1],
                [tx2, ty2], [tx1, ty2],
                [tx1, ty1]
            ], dtype=np.float32)
            tit_line = self._create_guide_line(rect_title, color=color_title, width=2.0)
            self._guide_visuals.append(tit_line)

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
        
        self._press_pos = None
        self._pan_last_pos = None
        self._is_panning = False

        # Timeline scrubbing state (DJV style - middle mouse button)
        self._is_scrubbing = False
        self._scrub_start_x = 0.0
        self._scrub_start_frame = 0
        self._scrub_button = None
        
        self.canvas.events.mouse_press.connect(self._on_canvas_mouse_press)
        self.canvas.events.mouse_release.connect(self._on_canvas_mouse_release)
        self.canvas.events.mouse_double_click.connect(self._on_canvas_double_click)
        self.canvas.events.mouse_move.connect(self._on_mouse_move)
        self.canvas.events.mouse_wheel.connect(self._on_mouse_wheel)

    def _on_mouse_wheel(self, event):
        if self.main_window and hasattr(self.main_window, '_update_zoom_label'):
            QtCore.QTimer.singleShot(20, self.main_window._update_zoom_label)

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

        # Middle-click (button 3): start timeline scrubbing (DJV style), or pan with Alt/Space
        if event.button == 3:
            modifiers = getattr(event, 'modifiers', ()) or ()
            if 'Alt' in modifiers or 'Space' in modifiers:
                self._is_panning = True
                self._pan_last_pos = event.pos
                event.handled = True
                return
            else:
                self._is_scrubbing = True
                self._scrub_button = 3
                self._scrub_start_x = event.pos[0]
                self._scrub_start_frame = getattr(self.main_window, 'current_index', 0) if self.main_window else 0
                if self.canvas and hasattr(self.canvas, 'native') and self.canvas.native:
                    self.canvas.native.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.SizeHorCursor))
                if self.main_window and getattr(self.main_window, 'playing', False):
                    self.main_window.pause()
                event.handled = True
                return

        # Alt+Click or Space+Click: pan modifier
        modifiers = getattr(event, 'modifiers', ()) or ()
        if event.button == 1 and ('Alt' in modifiers or 'Space' in modifiers):
            self._is_panning = True
            self._pan_last_pos = event.pos
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
                self._press_pos = event.pos
                self._pan_last_pos = event.pos
                self._is_panning = False
                if not self._click_timer.isActive():
                    self._click_timer.start()

    def _on_mouse_move(self, event):
        try:
            # 0. Active timeline scrubbing (Middle-click drag or Left-click drag in scrub mode)
            if getattr(self, '_is_scrubbing', False):
                dx = event.pos[0] - self._scrub_start_x
                modifiers = getattr(event, 'modifiers', ()) or ()
                if 'Shift' in modifiers:
                    px_per_frame = 16.0  # Fine precision 1:1 scrub
                elif 'Control' in modifiers or 'Ctrl' in modifiers:
                    px_per_frame = 2.0   # Fast shuttle scrub
                else:
                    px_per_frame = 6.0   # Responsive smooth scrub

                frame_delta = int(dx / px_per_frame)
                if self.main_window and hasattr(self.main_window, 'core') and self.main_window.core:
                    total = self.main_window.core.frame_count()
                    if total > 0:
                        target = max(0, min(total - 1, self._scrub_start_frame + frame_delta))
                        if target != self.main_window.current_index:
                            self.main_window.seek(target, update_audio=False)
                            if hasattr(self.main_window, '_update_status'):
                                self.main_window._update_status(f"Scrubbing: Frame {target + 1} / {total}")
                event.handled = True
                return

            # 1. Direct active panning (middle click, alt+drag, or drag past threshold)
            if getattr(self, '_is_panning', False) and getattr(self, '_pan_last_pos', None) is not None:
                s1_x, s1_y = self._map_to_scene(self._pan_last_pos)
                s2_x, s2_y = self._map_to_scene(event.pos)
                dx = s1_x - s2_x
                dy = s1_y - s2_y
                self.view.camera.pan((dx, dy))
                self._pan_last_pos = event.pos
                self.canvas.update()
                event.handled = True
                return

            # 2. Left-drag when NOT drawing -> check if dragged past threshold to begin pan or scrub
            is_button_1_down = (
                event.button == 1
                or (hasattr(event, 'buttons') and 1 in event.buttons)
            )
            if not self.is_drawing and is_button_1_down:
                if getattr(self, '_press_pos', None) is not None:
                    p0 = self._press_pos
                    dist = math.hypot(event.pos[0] - p0[0], event.pos[1] - p0[1])
                    if dist >= 4.0:
                        self._click_timer.stop()
                        self._is_panning = True
                        s1_x, s1_y = self._map_to_scene(p0)
                        s2_x, s2_y = self._map_to_scene(event.pos)
                        dx = s1_x - s2_x
                        dy = s1_y - s2_y
                        self.view.camera.pan((dx, dy))
                        self._pan_last_pos = event.pos
                        self.canvas.update()
                        event.handled = True
                        return

            # 3. Drawing mode drag preview
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

            # 4. Hover pixel probe — only when image is loaded
            if self.image_visual.visible and self._last_shape is not None:
                x, y, _vy = self._map_to_image(event.pos)
                self.pixel_probe_hover.emit(x, y)
        except Exception:
            import traceback; traceback.print_exc()

    def _on_canvas_mouse_release(self, event):
        if getattr(self, '_is_scrubbing', False):
            self._is_scrubbing = False
            self._scrub_button = None
            self._press_pos = None
            if self.canvas and hasattr(self.canvas, 'native') and self.canvas.native:
                self.canvas.native.unsetCursor()
            if self.main_window:
                if hasattr(self.main_window, '_on_scrub_finished'):
                    self.main_window._on_scrub_finished()
                if hasattr(self.main_window, '_update_status') and hasattr(self.main_window, '_status_base'):
                    self.main_window._update_status(self.main_window._status_base)
            event.handled = True
            return

        if getattr(self, '_is_panning', False):
            self._is_panning = False
            self._pan_last_pos = None
            self._press_pos = None
            self._click_timer.stop()
            event.handled = True
            return

        self._press_pos = None
        self._pan_last_pos = None

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
        if not getattr(self, '_is_panning', False):
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
            self._render_text_visual(stroke)

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

    def _cancel_text_input(self):
        """Cancel active text input without committing text."""
        widget = self._text_input
        self._text_input = None
        self._text_scene_pos = None
        if widget is not None:
            try:
                widget.removeEventFilter(self)
            except Exception:
                pass
            widget.hide()
            widget.deleteLater()

    def finish_text_input(self):
        """Public API to commit any open text input widget."""
        self._finish_text_input()

    def _finish_text_input(self):
        """Commit the typed text as an annotation stroke."""
        widget = self._text_input
        if widget is None:
            return

        self._text_input = None
        try:
            widget.removeEventFilter(self)
        except Exception:
            pass
        
        text = widget.text().strip()
        widget.hide()
        widget.deleteLater()

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
            self.canvas.update()
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
        # Calculate legible font size based on annotation width setting
        font_size = max(14, width * 5)
        try:
            vis = visuals.Text(
                text=text,
                color=color,
                font_size=font_size,
                pos=(x, y, 0),
                parent=self.view.scene,
                anchor_x='left',
                anchor_y='top',
            )
            vis.order = 15
            vis.set_gl_state('translucent', depth_test=False)
            self._all_stroke_visuals.append(vis)
        except Exception as e:
            print(f"[Text Visual Error] {e}")

    def eventFilter(self, obj, event):
        """Catch Escape, FocusOut, or Return on the text input widget to commit or cancel it, and consume all keys."""
        if self._text_input is not None and obj is self._text_input:
            if event.type() == QtCore.QEvent.Type.FocusOut:
                self._finish_text_input()
                return True
            elif event.type() in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
                if event.type() == QtCore.QEvent.Type.KeyPress:
                    if event.key() == QtCore.Qt.Key.Key_Escape:
                        self._cancel_text_input()
                        return True
                    elif event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                        self._finish_text_input()
                        return True
                
                # Temporarily remove event filter to avoid recursion
                self._text_input.removeEventFilter(self)
                # Send the event directly to QLineEdit so it processes typing/backspace/etc. natively
                QtWidgets.QApplication.sendEvent(self._text_input, event)
                # Reinstall the event filter
                self._text_input.installEventFilter(self)
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
            self._update_safe_guides()
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

            if getattr(self, '_show_guides', False) and not getattr(self, '_guide_visuals', None):
                self._update_safe_guides()

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

    @property
    def current_zoom(self) -> float:
        """Calculate current effective zoom factor relative to native image size."""
        if getattr(self, '_last_shape', None) and hasattr(self.view, 'camera') and self.view.camera and hasattr(self.view.camera, 'rect'):
            h, w = self._last_shape
            rect = self.view.camera.rect
            if rect.width > 0:
                return float(w / rect.width)
        return float(getattr(self, '_zoom', 1.0))

    def fit_to_window(self):
        """Fit image to window, reset pan offset, and center image."""
        if self._last_shape:
            h, w = self._last_shape
            self.view.camera.set_range(x=(0, w), y=(0, h), margin=0.01)
        else:
            self.view.camera.set_range(margin=0.01)
        self._zoom = 1.0
        self.canvas.update()

    def set_zoom(self, value: float):
        """Zoom to specified magnification factor while keeping center."""
        curr = self.current_zoom
        if curr > 0.001:
            factor = value / curr
        else:
            factor = value / max(self._zoom, 0.001)
        self._zoom = value
        if abs(factor) > 0.0001:
            self.view.camera.zoom(1.0 / factor)
        self.canvas.update()

    # ─────────────────────────────────────────────────────────────
    # Drag-and-drop
    # ─────────────────────────────────────────────────────────────

    def _set_drop_highlight(self, active: bool):
        if hasattr(self, '_drop_overlay'):
            if active:
                self._drop_overlay.setGeometry(8, 8, max(10, self.width() - 16), max(10, self.height() - 16))
                self._drop_overlay.show()
                self._drop_overlay.raise_()
            else:
                self._drop_overlay.hide()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-vfxplayer-shot') or mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()
            self._set_drop_highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-vfxplayer-shot') or mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_highlight(False)
        event.accept()

    def dropEvent(self, event):
        self._set_drop_highlight(False)
        mime = event.mimeData()

        # 1. Custom playlist shot dropped
        if mime.hasFormat('application/x-vfxplayer-shot'):
            try:
                raw = mime.data('application/x-vfxplayer-shot').data().decode('utf-8')
                import json
                shot_data = json.loads(raw)
                if self.main_window and hasattr(self.main_window, 'handle_shot_dropped_on_slot'):
                    self.main_window.handle_shot_dropped_on_slot(self.slot_index, shot_data)
                elif shot_data.get('media_path') and self.main_window:
                    self.main_window.load_media_into_slot(self.slot_index, shot_data['media_path'])
                event.acceptProposedAction()
                return
            except Exception as e:
                print(f"[Drop Error] Failed to parse shot payload: {e}")

        # 2. File URLs dropped (external file explorer or playlist URLs)
        paths = [u.toLocalFile() for u in mime.urls() if u.toLocalFile()]
        if paths and self.main_window:
            target = paths[0]
            if hasattr(self.main_window, 'load_media_into_slot'):
                self.main_window.load_media_into_slot(self.slot_index, target)
            elif self.role == 'secondary':
                self.main_window.load_compare_media(target)
            else:
                self.main_window.load_media(target)
            event.acceptProposedAction()
            return

        # 3. Plain text path fallback
        if mime.hasText():
            text_p = mime.text().strip()
            if os.path.exists(text_p) and self.main_window:
                self.main_window.load_media_into_slot(self.slot_index, text_p)
                event.acceptProposedAction()
                return
