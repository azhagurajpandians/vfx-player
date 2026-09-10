from __future__ import annotations

from typing import Optional
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets


class ScopeCanvas(QtWidgets.QWidget):
    """QPainter-based high-performance render widget for Histogram and Waveform."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(320, 200)
        self._mode = "histogram"  # "histogram" or "waveform"
        self._channel = "RGB"     # "RGB", "R", "G", "B", "Luma"
        self._hist_r: Optional[np.ndarray] = None
        self._hist_g: Optional[np.ndarray] = None
        self._hist_b: Optional[np.ndarray] = None
        self._hist_luma: Optional[np.ndarray] = None
        self._waveform_points: Optional[tuple] = None  # (xs, ys_r, ys_g, ys_b)

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def set_channel(self, channel: str):
        self._channel = channel
        self.update()

    def update_frame(self, image: Optional[np.ndarray]):
        """Compute histogram and waveform data from an image numpy array."""
        if image is None or image.size == 0:
            self._hist_r = self._hist_g = self._hist_b = self._hist_luma = None
            self._waveform_points = None
            self.update()
            return

        # Ensure float in range [0, 1] or uint8 [0, 255]
        h, w = image.shape[:2]
        
        # Downsample for fast real-time analysis if large
        max_dim = 512
        if max(h, w) > max_dim:
            step = int(np.ceil(max(h, w) / max_dim))
            sub = image[::step, ::step]
        else:
            sub = image

        if np.issubdtype(sub.dtype, np.floating):
            data = np.clip(sub, 0.0, 1.0)
            bins = 256
            val_range = (0.0, 1.0)
        else:
            data = sub.astype(np.float32) / 255.0
            bins = 256
            val_range = (0.0, 1.0)

        # Separate channels
        if data.ndim == 3 and data.shape[2] >= 3:
            r = data[..., 0].ravel()
            g = data[..., 1].ravel()
            b = data[..., 2].ravel()
            luma = (0.2126 * r + 0.7152 * g + 0.0722 * b)
        elif data.ndim == 2:
            r = g = b = luma = data.ravel()
        else:
            r = g = b = luma = data[..., 0].ravel()

        # Compute histograms
        self._hist_r, _ = np.histogram(r, bins=bins, range=val_range)
        self._hist_g, _ = np.histogram(g, bins=bins, range=val_range)
        self._hist_b, _ = np.histogram(b, bins=bins, range=val_range)
        self._hist_luma, _ = np.histogram(luma, bins=bins, range=val_range)

        # Normalize histograms
        max_val = max(
            np.max(self._hist_r),
            np.max(self._hist_g),
            np.max(self._hist_b),
            1
        )
        self._hist_r = self._hist_r / max_val
        self._hist_g = self._hist_g / max_val
        self._hist_b = self._hist_b / max_val
        self._hist_luma = self._hist_luma / max_val

        # Subsample waveform points (columns)
        if self._mode == "waveform" and data.ndim == 3 and data.shape[2] >= 3:
            wf_w = min(128, data.shape[1])
            col_step = max(1, data.shape[1] // wf_w)
            wf_sub = data[:, ::col_step, :3]
            self._waveform_data = wf_sub
        else:
            self._waveform_data = None

        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        # Background
        painter.fillRect(rect, QtGui.QColor(18, 18, 20))

        # Margin
        margin_l, margin_r = 30, 15
        margin_t, margin_b = 15, 25
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        if plot_w <= 10 or plot_h <= 10:
            return

        # Grid and axis lines
        grid_pen = QtGui.QPen(QtGui.QColor(45, 45, 50), 1, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        
        # Horizontal divisions (0%, 25%, 50%, 75%, 100%)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        text_pen = QtGui.QPen(QtGui.QColor(120, 120, 130))

        for frac, label in [(0.0, "0.0"), (0.25, "0.25"), (0.5, "0.5"), (0.75, "0.75"), (1.0, "1.0")]:
            y = margin_t + plot_h - int(frac * plot_h)
            painter.setPen(grid_pen)
            painter.drawLine(margin_l, y, margin_l + plot_w, y)
            painter.setPen(text_pen)
            painter.drawText(2, y + 4, label)

        # Plot boundary
        border_pen = QtGui.QPen(QtGui.QColor(60, 60, 68), 1)
        painter.setPen(border_pen)
        painter.drawRect(margin_l, margin_t, plot_w, plot_h)

        if self._hist_r is None:
            painter.setPen(QtGui.QColor(100, 100, 100))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "No Media Loaded")
            return

        if self._mode == "histogram":
            self._draw_histogram(painter, margin_l, margin_t, plot_w, plot_h)
        else:
            self._draw_waveform(painter, margin_l, margin_t, plot_w, plot_h)

    def _draw_histogram(self, painter: QtGui.QPainter, ml: int, mt: int, pw: int, ph: int):
        num_bins = len(self._hist_r)
        
        channels_to_draw = []
        if self._channel in ("RGB", "R"):
            channels_to_draw.append((self._hist_r, QtGui.QColor(240, 60, 60, 180), QtGui.QColor(240, 60, 60, 50)))
        if self._channel in ("RGB", "G"):
            channels_to_draw.append((self._hist_g, QtGui.QColor(60, 220, 60, 180), QtGui.QColor(60, 220, 60, 50)))
        if self._channel in ("RGB", "B"):
            channels_to_draw.append((self._hist_b, QtGui.QColor(60, 120, 240, 180), QtGui.QColor(60, 120, 240, 50)))
        if self._channel == "Luma":
            channels_to_draw.append((self._hist_luma, QtGui.QColor(220, 220, 220, 220), QtGui.QColor(220, 220, 220, 60)))

        for hist_data, stroke_color, fill_color in channels_to_draw:
            path = QtGui.QPainterPath()
            path.moveTo(ml, mt + ph)
            
            for i in range(num_bins):
                x = ml + int((i / (num_bins - 1)) * pw)
                val = float(hist_data[i])
                y = mt + ph - int(val * ph)
                path.lineTo(x, y)
                
            path.lineTo(ml + pw, mt + ph)
            path.closeSubpath()

            painter.fillPath(path, QtGui.QBrush(fill_color))
            painter.setPen(QtGui.QPen(stroke_color, 1.5))
            painter.drawPath(path)

    def _draw_waveform(self, painter: QtGui.QPainter, ml: int, mt: int, pw: int, ph: int):
        if not hasattr(self, "_waveform_data") or self._waveform_data is None:
            return

        wf = self._waveform_data
        h_wf, w_wf, _ = wf.shape
        if w_wf == 0 or h_wf == 0:
            return

        # Draw fast point clusters per column
        for col_idx in range(w_wf):
            x = ml + int((col_idx / max(1, w_wf - 1)) * pw)
            r_col = wf[:, col_idx, 0]
            g_col = wf[:, col_idx, 1]
            b_col = wf[:, col_idx, 2]

            # Sample 24 points per column
            step = max(1, h_wf // 24)
            for row in range(0, h_wf, step):
                if self._channel in ("RGB", "R"):
                    yr = mt + ph - int(r_col[row] * ph)
                    painter.fillRect(x, yr, 2, 2, QtGui.QColor(255, 50, 50, 90))
                if self._channel in ("RGB", "G"):
                    yg = mt + ph - int(g_col[row] * ph)
                    painter.fillRect(x, yg, 2, 2, QtGui.QColor(50, 255, 50, 90))
                if self._channel in ("RGB", "B"):
                    yb = mt + ph - int(b_col[row] * ph)
                    painter.fillRect(x, yb, 2, 2, QtGui.QColor(50, 100, 255, 90))


class ScopesDialog(QtWidgets.QDialog):
    """Modeless professional Scopes HUD window showing Histogram and Waveform."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Scopes — Histogram / Waveform")
        self.resize(440, 280)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Tool)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar controls
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        lbl_mode = QtWidgets.QLabel("Mode:")
        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Histogram", "Waveform"])
        self.combo_mode.currentTextChanged.connect(self._on_mode_changed)

        lbl_ch = QtWidgets.QLabel("Channel:")
        self.combo_channel = QtWidgets.QComboBox()
        self.combo_channel.addItems(["RGB", "R", "G", "B", "Luma"])
        self.combo_channel.currentTextChanged.connect(self._on_channel_changed)

        top_bar.addWidget(lbl_mode)
        top_bar.addWidget(self.combo_mode)
        top_bar.addSpacing(10)
        top_bar.addWidget(lbl_ch)
        top_bar.addWidget(self.combo_channel)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        self.canvas = ScopeCanvas(self)
        layout.addWidget(self.canvas, stretch=1)

        self.setStyleSheet("""
            QDialog {
                background-color: #141416;
                color: #e0e0e0;
            }
            QLabel {
                color: #aaa;
                font-size: 11px;
            }
            QComboBox {
                background-color: #242428;
                color: #ddd;
                border: 1px solid #3a3a40;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)

    def _on_mode_changed(self, text: str):
        self.canvas.set_mode(text.lower())

    def _on_channel_changed(self, text: str):
        self.canvas.set_channel(text)

    def update_image(self, image: Optional[np.ndarray]):
        if self.isVisible():
            self.canvas.update_frame(image)
