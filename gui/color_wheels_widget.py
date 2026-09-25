# gui/color_wheels_widget.py
"""
3-Way Color Grading Wheels Widget for VFX Review Player.
Matches reference UI:
  - Top sliders: Contrast, Stretch, Warmer (Temperature), Greener (Tint)
  - 3 Chromatic Color Wheels: Lift, Gamma, Gain with balance pucks and master controls
  - Bottom slider: Saturation
  - Individual reset buttons (↺) and Reset All
"""

import math
from typing import Tuple
from PyQt6 import QtWidgets, QtCore, QtGui


class ColorWheelWidget(QtWidgets.QWidget):
    """
    Interactive Chromatic Color Wheel.
    Renders outer hue circle with smooth conical gradient, inner dark well with crosshair ticks,
    draggable center balance puck, and fine-control drag.
    """
    balance_changed = QtCore.pyqtSignal(float, float)  # norm_x, norm_y in [-1.0, 1.0]

    def __init__(self, parent=None, wheel_radius=55, ring_thickness=None, puck_radius=None):
        super().__init__(parent)
        self.wheel_radius = wheel_radius
        self.ring_thickness = ring_thickness if ring_thickness is not None else max(6, int(wheel_radius * 0.18))
        self.puck_radius = puck_radius if puck_radius is not None else max(4, int(wheel_radius * 0.12))

        # Normalized balance coordinate (-1.0 to 1.0, clamped inside circle)
        self.norm_x = 0.0
        self.norm_y = 0.0

        self._dragging = False
        self._last_mouse_pos = QtCore.QPointF()

        margin = max(4, int(self.ring_thickness * 0.5))
        size = (self.wheel_radius + margin) * 2
        self.setFixedSize(size, size)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)

    def set_balance(self, x: float, y: float, emit_signal: bool = True):
        """Set balance coordinates programmatically."""
        r = math.hypot(x, y)
        if r > 1.0:
            x /= r
            y /= r
        self.norm_x = x
        self.norm_y = y
        self.update()
        if emit_signal:
            self.balance_changed.emit(self.norm_x, self.norm_y)

    def reset_balance(self):
        self.set_balance(0.0, 0.0)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from_mouse(event.position())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._dragging:
            self._update_from_mouse(event.position(), fine=bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier))

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = False

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.reset_balance()

    def _update_from_mouse(self, pos: QtCore.QPointF, fine: bool = False):
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        dx = pos.x() - cx
        dy = pos.y() - cy

        inner_r = self.wheel_radius - self.ring_thickness
        if inner_r <= 0:
            return

        target_x = dx / inner_r
        target_y = dy / inner_r

        if fine:
            # Damped response for micro adjustments
            target_x = self.norm_x + (target_x - self.norm_x) * 0.25
            target_y = self.norm_y + (target_y - self.norm_y) * 0.25

        dist = math.hypot(target_x, target_y)
        if dist > 1.0:
            target_x /= dist
            target_y /= dist

        self.norm_x = target_x
        self.norm_y = target_y
        self.update()
        self.balance_changed.emit(self.norm_x, self.norm_y)

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        outer_r = self.wheel_radius
        inner_r = outer_r - self.ring_thickness

        # 1. Outer Chromatic Hue Ring
        conical_grad = QtGui.QConicalGradient(cx, cy, 0)
        # Standard color wheel hues: Red(0), Yellow(60), Green(120), Cyan(180), Blue(240), Magenta(300), Red(360)
        conical_grad.setColorAt(0.0 / 6.0, QtGui.QColor("#ff2a2a"))
        conical_grad.setColorAt(1.0 / 6.0, QtGui.QColor("#ffe600"))
        conical_grad.setColorAt(2.0 / 6.0, QtGui.QColor("#00e640"))
        conical_grad.setColorAt(3.0 / 6.0, QtGui.QColor("#00d4ff"))
        conical_grad.setColorAt(4.0 / 6.0, QtGui.QColor("#2a52ff"))
        conical_grad.setColorAt(5.0 / 6.0, QtGui.QColor("#e600e6"))
        conical_grad.setColorAt(6.0 / 6.0, QtGui.QColor("#ff2a2a"))

        ring_pen = QtGui.QPen(QtGui.QBrush(conical_grad), self.ring_thickness)
        ring_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
        painter.setPen(ring_pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QtCore.QPointF(cx, cy), outer_r - self.ring_thickness / 2.0, outer_r - self.ring_thickness / 2.0)

        # 2. Inner Well
        painter.setPen(QtGui.QPen(QtGui.QColor("#3a3a40"), 1))
        painter.setBrush(QtGui.QColor("#18181c"))
        painter.drawEllipse(QtCore.QPointF(cx, cy), inner_r, inner_r)

        # 3. Subtle Crosshair Ticks
        painter.setPen(QtGui.QPen(QtGui.QColor("#2d2d34"), 1))
        painter.drawLine(QtCore.QPointF(cx - inner_r, cy), QtCore.QPointF(cx + inner_r, cy))
        painter.drawLine(QtCore.QPointF(cx, cy - inner_r), QtCore.QPointF(cx, cy + inner_r))

        # 4. Draggable Center Puck
        puck_x = cx + self.norm_x * inner_r
        puck_y = cy + self.norm_y * inner_r

        # Puck shadow
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 100))
        painter.drawEllipse(QtCore.QPointF(puck_x + 1, puck_y + 1), self.puck_radius, self.puck_radius)

        # Puck body with metallic radial gradient
        puck_grad = QtGui.QRadialGradient(puck_x - 1, puck_y - 1, self.puck_radius)
        puck_grad.setColorAt(0.0, QtGui.QColor("#d0d0d8"))
        puck_grad.setColorAt(0.7, QtGui.QColor("#8e8e96"))
        puck_grad.setColorAt(1.0, QtGui.QColor("#4e4e56"))

        painter.setPen(QtGui.QPen(QtGui.QColor("#202024"), 1.2))
        painter.setBrush(puck_grad)
        painter.drawEllipse(QtCore.QPointF(puck_x, puck_y), self.puck_radius, self.puck_radius)

        # Center dot on puck
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#ffffff") if (abs(self.norm_x) > 0.02 or abs(self.norm_y) > 0.02) else QtGui.QColor("#999"))
        painter.drawEllipse(QtCore.QPointF(puck_x, puck_y), 1.5, 1.5)


class SingleGradeWheelUnit(QtWidgets.QFrame):
    """
    Unit containing Title, Reset button, ColorWheelWidget, and Master Slider.
    """
    wheel_changed = QtCore.pyqtSignal()

    def __init__(self, title: str, default_master: float = 1.0, master_min: float = 0.0, master_max: float = 2.0, is_offset: bool = False, parent=None):
        super().__init__(parent)
        self.title = title
        self.default_master = default_master
        self.is_offset = is_offset
        self.master_min = master_min
        self.master_max = master_max

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1a1e;
                border: 1px solid #28282e;
                border-radius: 6px;
            }
            QLabel {
                color: #e0e0e6;
                font-size: 11px;
                font-weight: bold;
                border: none;
                background: transparent;
            }
            QPushButton#resetBtn {
                background-color: transparent;
                color: #888892;
                border: none;
                font-size: 13px;
                padding: 1px 4px;
            }
            QPushButton#resetBtn:hover {
                color: #38bdf8;
            }
            QSlider::groove:horizontal {
                border: 1px solid #2c2c34;
                height: 4px;
                background: #141416;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #a1a1aa;
                border: 1px solid #52525b;
                width: 10px;
                height: 12px;
                margin: -4px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #38bdf8;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header Row (Title + Reset button)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_title = QtWidgets.QLabel(self.title)
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.btn_reset = QtWidgets.QPushButton("↺")
        self.btn_reset.setObjectName("resetBtn")
        self.btn_reset.setToolTip(f"Reset {self.title} balance and master to neutral")
        self.btn_reset.clicked.connect(self.reset_all)
        header.addWidget(self.btn_reset)
        layout.addLayout(header)

        # Color Wheel
        wheel_container = QtWidgets.QHBoxLayout()
        wheel_container.setContentsMargins(0, 0, 0, 0)
        wheel_container.addStretch()
        self.wheel = ColorWheelWidget(wheel_radius=48)
        self.wheel.balance_changed.connect(lambda x, y: self.wheel_changed.emit())
        wheel_container.addWidget(self.wheel)
        wheel_container.addStretch()
        layout.addLayout(wheel_container)

        # Master Slider & Value readout
        master_row = QtWidgets.QHBoxLayout()
        master_row.setContentsMargins(0, 0, 0, 0)
        master_row.setSpacing(4)

        lbl_m = QtWidgets.QLabel("M:")
        lbl_m.setStyleSheet("color: #71717a; font-size: 10px; font-weight: normal;")
        master_row.addWidget(lbl_m)

        self.slider_master = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider_master.setRange(0, 1000)
        self._set_slider_from_master(self.default_master)
        self.slider_master.valueChanged.connect(self._on_slider_master_changed)
        master_row.addWidget(self.slider_master, stretch=1)

        self.lbl_val = QtWidgets.QLabel(f"{self.default_master:.2f}")
        self.lbl_val.setStyleSheet("color: #94a3b8; font-size: 10px; font-family: monospace;")
        self.lbl_val.setFixedWidth(34)
        master_row.addWidget(self.lbl_val)

        layout.addLayout(master_row)

    def _set_slider_from_master(self, val: float):
        t = (val - self.master_min) / max(1e-5, (self.master_max - self.master_min))
        slider_val = int(max(0.0, min(1.0, t)) * 1000)
        self.slider_master.blockSignals(True)
        self.slider_master.setValue(slider_val)
        self.slider_master.blockSignals(False)

    def _on_slider_master_changed(self, ival: int):
        val = self.get_master_value()
        self.lbl_val.setText(f"{val:.2f}")
        self.wheel_changed.emit()

    def get_master_value(self) -> float:
        t = self.slider_master.value() / 1000.0
        return self.master_min + t * (self.master_max - self.master_min)

    def set_master_value(self, val: float):
        self._set_slider_from_master(val)
        self.lbl_val.setText(f"{val:.2f}")
        self.wheel_changed.emit()

    def reset_all(self):
        self.wheel.reset_balance()
        self.set_master_value(self.default_master)

    def get_rgb_delta(self) -> Tuple[float, float, float]:
        """Convert normalized (x, y) into (delta_r, delta_g, delta_b)."""
        x = self.wheel.norm_x
        y = self.wheel.norm_y

        # Angles: 0 deg = Red, 120 deg = Green, 240 deg = Blue
        dr = x
        dg = -0.5 * x + 0.866025 * y
        db = -0.5 * x - 0.866025 * y
        return (dr, dg, db)


class LabeledGradeSlider(QtWidgets.QWidget):
    """
    Horizontal Slider with Label, center tick mark, value display, and reset button (↺).
    Matches the top/bottom sliders in reference media_1789022063713.jpg.
    """
    valueChanged = QtCore.pyqtSignal(float)

    def __init__(self, label: str, min_val: float, max_val: float, default_val: float, step_decimals: int = 2, parent=None):
        super().__init__(parent)
        self.label_text = label
        self.min_val = min_val
        self.max_val = max_val
        self.default_val = default_val
        self.step_decimals = step_decimals
        self._steps = 1000

        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self.lbl = QtWidgets.QLabel(self.label_text)
        self.lbl.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 500;")
        self.lbl.setFixedWidth(65)
        layout.addWidget(self.lbl)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, self._steps)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #27272a;
                height: 4px;
                background: #141416;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #d4d4d8;
                border: 1px solid #52525b;
                width: 10px;
                height: 14px;
                margin: -5px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #38bdf8;
            }
        """)
        self._set_slider_val(self.default_val)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider, stretch=1)

        self.lbl_val = QtWidgets.QLabel(f"{self.default_val:.{self.step_decimals}f}")
        self.lbl_val.setStyleSheet("color: #71717a; font-size: 10px; font-family: monospace;")
        self.lbl_val.setFixedWidth(36)
        layout.addWidget(self.lbl_val)

        self.btn_reset = QtWidgets.QPushButton("↺")
        self.btn_reset.setToolTip(f"Reset {self.label_text} to {self.default_val}")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #71717a;
                border: none;
                font-size: 12px;
                padding: 1px 3px;
            }
            QPushButton:hover {
                color: #38bdf8;
            }
        """)
        self.btn_reset.clicked.connect(self.reset)
        layout.addWidget(self.btn_reset)

    def _set_slider_val(self, val: float):
        t = (val - self.min_val) / max(1e-5, (self.max_val - self.min_val))
        s_val = int(max(0.0, min(1.0, t)) * self._steps)
        self.slider.blockSignals(True)
        self.slider.setValue(s_val)
        self.slider.blockSignals(False)

    def _on_slider_changed(self, s_val: int):
        val = self.value()
        self.lbl_val.setText(f"{val:.{self.step_decimals}f}")
        self.valueChanged.emit(val)

    def value(self) -> float:
        t = self.slider.value() / float(self._steps)
        return self.min_val + t * (self.max_val - self.min_val)

    def setValue(self, val: float):
        self._set_slider_val(val)
        self.lbl_val.setText(f"{val:.{self.step_decimals}f}")
        self.valueChanged.emit(val)

    def reset(self):
        self.setValue(self.default_val)


class ColorGradingPanel(QtWidgets.QFrame):
    """
    Complete 3-Way Color Wheels Grading Panel.
    Embeds:
      - Top Sliders: Contrast, Stretch, Warmer, Greener
      - 3 Wheels: Lift, Gamma, Gain
      - Bottom Slider: Saturation
      - Utility Controls: Reset All, Import CDL, Export CDL
    """
    grade_changed = QtCore.pyqtSignal(tuple, tuple, tuple, float)  # slope, offset, power, saturation
    import_cdl_requested = QtCore.pyqtSignal()
    export_cdl_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QFrame#colorGradingPanel {
                background-color: #121215;
                border-left: 1px solid #26262b;
            }
            QLabel {
                color: #d4d4d8;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QPushButton {
                background-color: #202024;
                color: #e4e4e7;
                border: 1px solid #333338;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2a2a30;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.setObjectName("colorGradingPanel")
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Header Title
        title_row = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel("<b>COLOR GRADING</b> — 3-WAY WHEELS")
        title_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #38bdf8; letter-spacing: 1px;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        btn_reset_all = QtWidgets.QPushButton("Reset All")
        btn_reset_all.setToolTip("Reset all color wheels and sliders to neutral")
        btn_reset_all.clicked.connect(self.reset_all)
        title_row.addWidget(btn_reset_all)
        layout.addLayout(title_row)

        # ── Top Sliders: Contrast, Stretch, Warmer, Greener ───────
        top_box = QtWidgets.QFrame()
        top_box.setStyleSheet("background-color: #18181c; border: 1px solid #26262b; border-radius: 6px;")
        top_layout = QtWidgets.QVBoxLayout(top_box)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(4)

        self.slider_contrast = LabeledGradeSlider("Contrast:", min_val=0.5, max_val=2.0, default_val=1.0)
        self.slider_contrast.valueChanged.connect(self._on_params_changed)
        top_layout.addWidget(self.slider_contrast)

        self.slider_stretch = LabeledGradeSlider("Stretch:", min_val=0.2, max_val=3.0, default_val=1.0)
        self.slider_stretch.valueChanged.connect(self._on_params_changed)
        top_layout.addWidget(self.slider_stretch)

        self.slider_warmer = LabeledGradeSlider("Warmer:", min_val=-1.0, max_val=1.0, default_val=0.0)
        self.slider_warmer.valueChanged.connect(self._on_params_changed)
        top_layout.addWidget(self.slider_warmer)

        self.slider_greener = LabeledGradeSlider("Greener:", min_val=-1.0, max_val=1.0, default_val=0.0)
        self.slider_greener.valueChanged.connect(self._on_params_changed)
        top_layout.addWidget(self.slider_greener)

        layout.addWidget(top_box)

        # ── Middle Row: 3 Color Wheels (Lift, Gamma, Gain) ────────
        wheels_row = QtWidgets.QHBoxLayout()
        wheels_row.setSpacing(8)

        # Lift (Offset): default master 0.0, range -0.5 to +0.5
        self.wheel_lift = SingleGradeWheelUnit("Lift", default_master=0.0, master_min=-0.5, master_max=0.5, is_offset=True)
        self.wheel_lift.wheel_changed.connect(self._on_params_changed)
        wheels_row.addWidget(self.wheel_lift)

        # Gamma (Power): default master 1.0, range 0.2 to 2.5
        self.wheel_gamma = SingleGradeWheelUnit("Gamma", default_master=1.0, master_min=0.2, master_max=2.5)
        self.wheel_gamma.wheel_changed.connect(self._on_params_changed)
        wheels_row.addWidget(self.wheel_gamma)

        # Gain (Slope): default master 1.0, range 0.0 to 3.0
        self.wheel_gain = SingleGradeWheelUnit("Gain", default_master=1.0, master_min=0.0, master_max=3.0)
        self.wheel_gain.wheel_changed.connect(self._on_params_changed)
        wheels_row.addWidget(self.wheel_gain)

        layout.addLayout(wheels_row)

        # ── Bottom Section: Saturation Slider ─────────────────────
        bot_box = QtWidgets.QFrame()
        bot_box.setStyleSheet("background-color: #18181c; border: 1px solid #26262b; border-radius: 6px;")
        bot_layout = QtWidgets.QVBoxLayout(bot_box)
        bot_layout.setContentsMargins(10, 8, 10, 8)
        bot_layout.setSpacing(4)

        self.slider_sat = LabeledGradeSlider("Saturation:", min_val=0.0, max_val=3.0, default_val=1.0)
        self.slider_sat.valueChanged.connect(self._on_params_changed)
        bot_layout.addWidget(self.slider_sat)

        layout.addWidget(bot_box)

        # ── Bottom Action Buttons (Import/Export CDL) ─────────────
        io_row = QtWidgets.QHBoxLayout()
        io_row.setSpacing(8)

        btn_import = QtWidgets.QPushButton("Import CDL...")
        btn_import.setToolTip("Import ASC CDL XML file (.cdl, .cc, .xml)")
        btn_import.clicked.connect(self.import_cdl_requested.emit)
        io_row.addWidget(btn_import)

        btn_export = QtWidgets.QPushButton("Export CDL...")
        btn_export.setToolTip("Export current grade as standard ASC CDL XML")
        btn_export.clicked.connect(self.export_cdl_requested.emit)
        io_row.addWidget(btn_export)

        layout.addLayout(io_row)

    def reset_all(self):
        """Reset all grading wheels and sliders to neutral values."""
        self.slider_contrast.reset()
        self.slider_stretch.reset()
        self.slider_warmer.reset()
        self.slider_greener.reset()
        self.wheel_lift.reset_all()
        self.wheel_gamma.reset_all()
        self.wheel_gain.reset_all()
        self.slider_sat.reset()
        self._on_params_changed()

    def get_cdl_parameters(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float], float]:
        """
        Compute effective ASC CDL (Slope, Offset, Power, Saturation)
        from wheels, temperature/tint, contrast, and saturation.
        """
        # 1. Gain -> Slope
        m_gain = self.wheel_gain.get_master_value()
        dr_gain, dg_gain, db_gain = self.wheel_gain.get_rgb_delta()
        slope_r = max(0.0, m_gain * (1.0 + dr_gain * 0.5))
        slope_g = max(0.0, m_gain * (1.0 + dg_gain * 0.5))
        slope_b = max(0.0, m_gain * (1.0 + db_gain * 0.5))

        # Warmer (Temp) & Greener (Tint) adjustment on slope
        warmer = self.slider_warmer.value()
        greener = self.slider_greener.value()
        slope_r *= max(0.0, 1.0 + warmer * 0.3 - greener * 0.1)
        slope_g *= max(0.0, 1.0 + greener * 0.3)
        slope_b *= max(0.0, 1.0 - warmer * 0.3 - greener * 0.1)

        # Contrast & Stretch expansion on slope
        contrast = self.slider_contrast.value()
        stretch = self.slider_stretch.value()
        slope_r *= contrast
        slope_g *= contrast
        slope_b *= contrast

        # 2. Lift -> Offset
        m_lift = self.wheel_lift.get_master_value()
        dr_lift, dg_lift, db_lift = self.wheel_lift.get_rgb_delta()
        offset_r = m_lift + dr_lift * 0.2
        offset_g = m_lift + dg_lift * 0.2
        offset_b = m_lift + db_lift * 0.2

        # Pivot offset adjust for contrast: pivot = 0.18 * stretch
        pivot = 0.18 * stretch
        contrast_offset = pivot * (1.0 - contrast)
        offset_r += contrast_offset
        offset_g += contrast_offset
        offset_b += contrast_offset

        # 3. Gamma -> Power
        m_gamma = self.wheel_gamma.get_master_value()
        dr_gam, dg_gam, db_gam = self.wheel_gamma.get_rgb_delta()
        power_r = max(0.1, m_gamma * (1.0 - dr_gam * 0.4))
        power_g = max(0.1, m_gamma * (1.0 - dg_gam * 0.4))
        power_b = max(0.1, m_gamma * (1.0 - db_gam * 0.4))

        # 4. Saturation
        sat = max(0.0, self.slider_sat.value())

        return (
            (slope_r, slope_g, slope_b),
            (offset_r, offset_g, offset_b),
            (power_r, power_g, power_b),
            sat
        )

    def set_cdl_parameters(self, slope: Tuple[float, float, float], offset: Tuple[float, float, float], power: Tuple[float, float, float], sat: float):
        """Set controls from imported CDL values."""
        avg_slope = (slope[0] + slope[1] + slope[2]) / 3.0
        self.wheel_gain.set_master_value(avg_slope)
        if avg_slope > 1e-4:
            dr = (slope[0] / avg_slope - 1.0) / 0.5
            dg = (slope[1] / avg_slope - 1.0) / 0.5
            self.wheel_gain.wheel.set_balance(dr, dg)

        avg_offset = (offset[0] + offset[1] + offset[2]) / 3.0
        self.wheel_lift.set_master_value(avg_offset)
        dr_l = (offset[0] - avg_offset) / 0.2
        dg_l = (offset[1] - avg_offset) / 0.2
        self.wheel_lift.wheel.set_balance(dr_l, dg_l)

        avg_power = (power[0] + power[1] + power[2]) / 3.0
        self.wheel_gamma.set_master_value(avg_power)
        if avg_power > 1e-4:
            dr_p = -(power[0] / avg_power - 1.0) / 0.4
            dg_p = -(power[1] / avg_power - 1.0) / 0.4
            self.wheel_gamma.wheel.set_balance(dr_p, dg_p)

        self.slider_sat.setValue(sat)
        self._on_params_changed()

    def _on_params_changed(self, *args):
        slope, offset, power, sat = self.get_cdl_parameters()
        self.grade_changed.emit(slope, offset, power, sat)
