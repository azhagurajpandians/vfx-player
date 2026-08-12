"""
RV-style Annotation Toolbar for VFXPlayer.

Uses QPainter-drawn icons instead of unicode characters so they render
perfectly on any Windows DPI setting.
"""

from __future__ import annotations
import math
from PyQt6 import QtWidgets, QtCore, QtGui

# ─────────────────────────────────────────────────────────────────
# Colour palette
# ─────────────────────────────────────────────────────────────────
_BG       = "#1c1c1e"
_BTN      = "#2c2c2e"
_BTN_HVR  = "#3a3a3c"
_BTN_ACT  = "#0a84ff"
_BORDER   = "#3a3a3c"
_TEXT     = "#c8c8cc"
_DIV      = "#38383a"
_RED      = "#ff453a"

_PRESETS = [
    ("#ff3b30", (1.000, 0.231, 0.188, 1.0)),
    ("#ff9f0a", (1.000, 0.624, 0.039, 1.0)),
    ("#ffd60a", (1.000, 0.839, 0.039, 1.0)),
    ("#34c759", (0.204, 0.780, 0.349, 1.0)),
    ("#0a84ff", (0.039, 0.518, 1.000, 1.0)),
    ("#ffffff", (1.000, 1.000, 1.000, 1.0)),
]

# ─────────────────────────────────────────────────────────────────
# Shared stylesheets
# ─────────────────────────────────────────────────────────────────
_TOOLBAR_QSS = f"""
QWidget#AnnotationToolbar {{
    background: {_BG};
    border-top: 1px solid {_DIV};
}}
"""

_ACTION_QSS = f"""
QPushButton {{
    background: {_BTN};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    font-size: 13px;
    font-weight: bold;
    min-width:28px; max-width:28px;
    min-height:26px; max-height:26px;
    padding: 0;
}}
QPushButton:hover   {{ background: {_BTN_HVR}; color:#fff; border-color:#5a5a5e; }}
QPushButton:pressed {{ background:#444446; }}
QPushButton:disabled {{ color:#555558; border-color:{_BTN}; }}
"""

_CLEAR_QSS = f"""
QPushButton {{
    background: {_BTN};
    color: {_RED};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    min-width:52px; min-height:26px; max-height:26px;
    padding: 0 4px;
}}
QPushButton:hover   {{ background:#3a1a1a; border-color:{_RED}; color:#ff6b63; }}
QPushButton:pressed {{ background:#502020; }}
"""

_SPIN_QSS = f"""
QSpinBox {{
    background:{_BTN}; color:{_TEXT}; border:1px solid {_BORDER};
    border-radius:4px; padding:0 2px;
    font-size:11px; font-family:Consolas,monospace;
    min-width:36px; max-width:36px;
    min-height:22px; max-height:22px;
}}
QSpinBox:focus {{ border-color:{_BTN_ACT}; }}
QSpinBox::up-button,QSpinBox::down-button {{
    width:14px; border:none; background:{_BTN_HVR};
}}
"""





def _vsep():
    f = QtWidgets.QFrame()
    f.setFrameShape(QtWidgets.QFrame.Shape.VLine)
    f.setFixedSize(1, 22)
    f.setStyleSheet(f"background:{_DIV}; border:none;")
    return f


# ─────────────────────────────────────────────────────────────────
# Icon painter helpers
# ─────────────────────────────────────────────────────────────────

def _pen_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color, 1.5)
    p.setPen(pen)
    # Diagonal line (pen stroke)
    p.drawLine(2, size - 3, size - 3, 2)
    # Small dot at bottom-left (pen tip)
    p.setBrush(color)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawEllipse(1, size - 4, 3, 3)
    p.end()
    return QtGui.QIcon(pix)


def _line_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setPen(QtGui.QPen(color, 2, QtCore.Qt.PenStyle.SolidLine,
                        QtCore.Qt.PenCapStyle.RoundCap))
    p.drawLine(2, size - 2, size - 2, 2)
    p.end()
    return QtGui.QIcon(pix)


def _arrow_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color, 1.8, QtCore.Qt.PenStyle.SolidLine,
                     QtCore.Qt.PenCapStyle.RoundCap, QtCore.Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    # Shaft
    x1, y1, x2, y2 = 2, size - 2, size - 3, 2
    p.drawLine(x1, y1, x2, y2)
    # Arrowhead
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    hs = 5
    p.setBrush(color)
    pts = QtGui.QPolygon([
        QtCore.QPoint(round(x2), round(y2)),
        QtCore.QPoint(round(x2 - ux * hs + px * hs * 0.4),
                      round(y2 - uy * hs + py * hs * 0.4)),
        QtCore.QPoint(round(x2 - ux * hs - px * hs * 0.4),
                      round(y2 - uy * hs - py * hs * 0.4)),
    ])
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawPolygon(pts)
    p.end()
    return QtGui.QIcon(pix)


def _rect_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setPen(QtGui.QPen(color, 1.8))
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawRect(2, 2, size - 4, size - 4)
    p.end()
    return QtGui.QIcon(pix)


def _ellipse_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setPen(QtGui.QPen(color, 1.8))
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawEllipse(2, 2, size - 4, size - 4)
    p.end()
    return QtGui.QIcon(pix)


def _text_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    font = QtGui.QFont("Segoe UI", int(size * 0.7), QtGui.QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(color)
    p.drawText(pix.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "A")
    p.end()
    return QtGui.QIcon(pix)


def _eraser_icon(color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color, 1.5)
    p.setPen(pen)
    p.setBrush(QtGui.QColor(color.red(), color.green(), color.blue(), 60))
    # Eraser body (tilted rectangle)
    poly = QtGui.QPolygonF([
        QtCore.QPointF(3,   size - 4),
        QtCore.QPointF(size - 4, 3),
        QtCore.QPointF(size - 2, 5),
        QtCore.QPointF(5,   size - 2),
    ])
    p.drawPolygon(poly)
    # Strike through
    p.setPen(QtGui.QPen(color, 1.2))
    p.drawLine(2, size - 2, size - 2, size - 2)
    p.end()
    return QtGui.QIcon(pix)


def _make_icon_pair(fn, size=16):
    """Return (normal_icon, checked_icon) pair for a tool button."""
    normal  = fn(QtGui.QColor(180, 180, 185), size)
    checked = fn(QtGui.QColor(255, 255, 255), size)
    return normal, checked


# ─────────────────────────────────────────────────────────────────
# Icon tool button
# ─────────────────────────────────────────────────────────────────

class IconToolButton(QtWidgets.QPushButton):
    """Checkable QPushButton that swaps icon when checked/unchecked."""

    def __init__(self, icon_normal: QtGui.QIcon, icon_checked: QtGui.QIcon,
                 tooltip: str, parent=None):
        super().__init__(parent)
        self._icon_normal  = icon_normal
        self._icon_checked = icon_checked
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self.setFixedSize(34, 28)
        self.setIconSize(QtCore.QSize(16, 16))
        self.setIcon(icon_normal)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)

    def _apply_style(self, checked: bool):
        bg     = _BTN_ACT if checked else _BTN
        border = _BTN_ACT if checked else _BORDER
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 0;
                min-width:34px; max-width:34px;
                min-height:28px; max-height:28px;
            }}
            QPushButton:hover {{
                background: {'#0060c0' if checked else _BTN_HVR};
                border-color: {'#0a84ff' if checked else '#5a5a5e'};
            }}
        """)

    def setChecked(self, v: bool):
        super().setChecked(v)
        self.setIcon(self._icon_checked if v else self._icon_normal)
        self._apply_style(v)


# ─────────────────────────────────────────────────────────────────
# Color swatch button
# ─────────────────────────────────────────────────────────────────

class ColorSwatch(QtWidgets.QPushButton):
    """Clickable full-colour swatch that opens QColorDialog."""
    color_changed = QtCore.pyqtSignal(tuple)   # (r, g, b, a) floats

    def __init__(self, color: QtGui.QColor = None, parent=None):
        super().__init__(parent)
        self._color = color or QtGui.QColor(255, 60, 48)
        self.setFixedSize(26, 26)
        self.setToolTip("Custom colour")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._repaint()

    def _repaint(self):
        c   = self._color.name()
        lum = (0.299 * self._color.redF() + 0.587 * self._color.greenF()
               + 0.114 * self._color.blueF())
        brd = "#ffffff" if lum < 0.5 else "#000000"
        self.setStyleSheet(f"""
            QPushButton {{
                background:{c}; border:2px solid {brd}; border-radius:4px;
                min-width:26px; max-width:26px;
                min-height:26px; max-height:26px;
            }}
            QPushButton:hover {{ border:2px solid {_BTN_ACT}; }}
        """)

    def _pick(self):
        dlg = QtWidgets.QColorDialog(self._color, self)
        dlg.setOption(
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        if dlg.exec():
            self._color = dlg.selectedColor()
            self._repaint()
            self.color_changed.emit(self._as_tuple())

    def _as_tuple(self):
        return (self._color.redF(), self._color.greenF(),
                self._color.blueF(), self._color.alphaF())

    def get_color_tuple(self): return self._as_tuple()

    def set_color(self, r, g, b, a=1.0):
        self._color = QtGui.QColor.fromRgbF(r, g, b, a)
        self._repaint()


# ─────────────────────────────────────────────────────────────────
# Main toolbar widget
# ─────────────────────────────────────────────────────────────────

_TOOL_DEFS = [
    ("pen",     _pen_icon,     "Freehand pen"),
    ("line",    _line_icon,    "Straight line"),
    ("arrow",   _arrow_icon,   "Arrow"),
    ("rect",    _rect_icon,    "Rectangle"),
    ("ellipse", _ellipse_icon, "Ellipse / oval"),
    ("text",    _text_icon,    "Text"),
    ("eraser",  _eraser_icon,  "Eraser – click a stroke to erase it"),
]


class AnnotationToolbar(QtWidgets.QWidget):
    """
    Professional RV-style horizontal annotation toolbar with painted icons.

    Signals
    -------
    tool_changed(str)
    color_changed(tuple)       – (r, g, b, a) floats 0-1
    width_changed(int)
    undo_requested()
    redo_requested()
    clear_frame_requested()
    clear_all_requested()
    """
    tool_changed            = QtCore.pyqtSignal(str)
    color_changed           = QtCore.pyqtSignal(tuple)
    width_changed           = QtCore.pyqtSignal(int)
    undo_requested          = QtCore.pyqtSignal()
    redo_requested          = QtCore.pyqtSignal()
    clear_frame_requested   = QtCore.pyqtSignal()
    clear_all_requested     = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnnotationToolbar")
        self.setFixedHeight(46)
        self.setStyleSheet(_TOOLBAR_QSS)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

        self._current_tool = "pen"
        self._btns: dict[str, IconToolButton] = {}

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(3)

        # ── Label ────────────────────────────────────────────────
        lbl = QtWidgets.QLabel("Annotate:")
        lbl.setStyleSheet(
            f"color:{_BTN_ACT}; font-size:11px; font-weight:bold;"
            " font-family:'Segoe UI',sans-serif; padding-right:4px;")
        lay.addWidget(lbl)

        # ── Tool buttons (painted icons) ──────────────────────────
        for tid, icon_fn, tip in _TOOL_DEFS:
            n_icon, c_icon = _make_icon_pair(icon_fn, size=16)
            btn = IconToolButton(n_icon, c_icon, tip)
            btn.clicked.connect(lambda _c, t=tid: self._select_tool(t))
            lay.addWidget(btn)
            self._btns[tid] = btn
        self._btns["pen"].setChecked(True)

        lay.addSpacing(4)
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        # ── Preset swatches ───────────────────────────────────────
        for hex_c, rgba in _PRESETS:
            pb = QtWidgets.QPushButton()
            pb.setFixedSize(20, 20)
            pb.setToolTip(hex_c)
            pb.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            pb.setStyleSheet(f"""
                QPushButton {{
                    background:{hex_c}; border:1px solid #1a1a1a;
                    border-radius:3px;
                    min-width:20px; max-width:20px;
                    min-height:20px; max-height:20px;
                }}
                QPushButton:hover {{ border:2px solid #ffffff; }}
            """)
            pb.clicked.connect(lambda _, c=rgba: self._emit_color(c))
            lay.addWidget(pb)

        lay.addSpacing(4)

        # ── Custom colour swatch ──────────────────────────────────
        self.swatch = ColorSwatch(QtGui.QColor(255, 60, 48))
        self.swatch.color_changed.connect(self.color_changed)
        self.swatch.setToolTip("Custom colour picker")
        lay.addWidget(self.swatch)

        lay.addSpacing(4)
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        # ── Width spinner ─────────────────────────────────────────
        w_col = QtWidgets.QVBoxLayout()
        w_col.setContentsMargins(0, 0, 0, 0)
        w_col.setSpacing(0)
        wlbl = QtWidgets.QLabel("Width")
        wlbl.setStyleSheet(f"color:#666; font-size:9px; font-family:'Segoe UI',sans-serif;")
        wlbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        w_col.addWidget(wlbl)
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(3)
        self.width_spin.setStyleSheet(_SPIN_QSS)
        self.width_spin.setToolTip("Stroke width 1–20 px")
        self.width_spin.valueChanged.connect(self.width_changed)
        w_col.addWidget(self.width_spin)
        lay.addLayout(w_col)

        lay.addSpacing(4)
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        # ── Undo / Redo ───────────────────────────────────────────
        self.btn_undo = QtWidgets.QPushButton("↩")
        self.btn_undo.setToolTip("Undo  Ctrl+Z")
        self.btn_undo.setStyleSheet(_ACTION_QSS)
        self.btn_undo.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_undo.clicked.connect(self.undo_requested)
        self.btn_undo.setEnabled(False)
        lay.addWidget(self.btn_undo)

        self.btn_redo = QtWidgets.QPushButton("↪")
        self.btn_redo.setToolTip("Redo  Ctrl+Shift+Z")
        self.btn_redo.setStyleSheet(_ACTION_QSS)
        self.btn_redo.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_redo.clicked.connect(self.redo_requested)
        self.btn_redo.setEnabled(False)
        lay.addWidget(self.btn_redo)

        lay.addSpacing(4)
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        # ── Clear ─────────────────────────────────────────────────
        self.btn_cf = QtWidgets.QPushButton("Clear Frame")
        self.btn_cf.setToolTip("Remove annotations from current frame")
        self.btn_cf.setStyleSheet(_CLEAR_QSS)
        self.btn_cf.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_cf.clicked.connect(self.clear_frame_requested)
        lay.addWidget(self.btn_cf)

        self.btn_ca = QtWidgets.QPushButton("Clear All")
        self.btn_ca.setToolTip("Remove ALL annotations on all frames")
        self.btn_ca.setStyleSheet(_CLEAR_QSS)
        self.btn_ca.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_ca.clicked.connect(self._confirm_clear_all)
        lay.addWidget(self.btn_ca)

        lay.addStretch(1)

    # ── Public API ────────────────────────────────────────────────

    def current_tool(self)  -> str:   return self._current_tool
    def current_color(self) -> tuple: return self.swatch.get_color_tuple()
    def current_width(self) -> int:   return self.width_spin.value()

    def set_undo_enabled(self, v: bool): self.btn_undo.setEnabled(v)
    def set_redo_enabled(self, v: bool): self.btn_redo.setEnabled(v)

    def set_tool(self, tid: str): self._select_tool(tid)

    # ── Internal ──────────────────────────────────────────────────

    def _select_tool(self, tid: str):
        self._current_tool = tid
        for k, b in self._btns.items():
            b.setChecked(k == tid)
        self.tool_changed.emit(tid)

    def _emit_color(self, rgba: tuple):
        r, g, b, a = rgba
        self.swatch.set_color(r, g, b, a)
        self.color_changed.emit(rgba)

    def _confirm_clear_all(self):
        r = QtWidgets.QMessageBox.question(
            self, "Clear All Annotations",
            "Delete ALL annotations on ALL frames?\nThis cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes |
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self.clear_all_requested.emit()
