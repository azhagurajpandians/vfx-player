"""Enhanced PyQt6 main window for VFXPlayer with compare & advanced controls."""

import sys, os, json, ctypes, time
import numpy as np
from typing import Optional, Tuple, List, Dict, Any
from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl
from gui.vispy_viewport import VispyViewport
from core.color_manager import ColorManager
from gui.settings_dialog import SettingsDialog
from core.player_core import PlaybackStrategy
from gui.metadata_dialog import MetadataDialog
from gui.export_dialog import ExportDialog
from gui.annotation_toolbar import AnnotationToolbar
from core.annotation_service import AnnotationService
from core.version_detector import VersionDetector, VersionGroup
from gui.scopes_dialog import ScopesDialog
import tempfile, webbrowser
from core.playlist_service import PlaylistService, PlaylistItem
from core.kitsu_service import kitsu_client, KitsuService
from gui.playlist_widget import PlaylistWidget
from gui.kitsu_dialog import KitsuConnectDialog, KitsuPublishDialog
from gui.color_wheels_widget import ColorWheelWidget, ColorGradingPanel
from gui.version_dialog import VersionCompareDialog
from gui.about_dialog import AboutDialog
from gui.shortcuts_dialog import ShortcutsDialog

def set_dark_title_bar(hwnd):
    if sys.platform == 'win32':
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
            )
        except Exception:
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
                value = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(hwnd), DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception:
                pass


class PlayheadSlider(QtWidgets.QSlider):
    """Horizontal slider with playhead line, cached-frame, bookmark, missing, and In/Out indicators."""
    def __init__(self, *args, **kwargs):
        super().__init__(QtCore.Qt.Orientation.Horizontal, *args, **kwargs)
        self.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.setTickInterval(1)
        self.setSingleStep(1)
        self._cached_indices = set()  # Set of cached frame indices
        self._annotated_indices = set()  # Set of annotated frame indices
        self._bookmarks = set()  # Set of bookmarked frame indices
        self._missing_indices = set()  # Set of missing frame indices
        self._in_point = None
        self._out_point = None
        self._show_cached = True  # Whether to show cached frame indicators
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #28282b;
                height: 4px;
                background: #18181a;
                border-radius: 2px;
                margin: 0px 0;
            }
            QSlider::sub-page:horizontal {
                background: #0a84ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #3a3a3c;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #e5e5ea;
                border-color: #0a84ff;
            }
        """)

    def mousePressEvent(self, event: QtGui.QMouseEvent):  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            margin = 5
            track_w = self.width() - (margin * 2)
            rng = self.maximum() - self.minimum()
            if track_w > 0 and rng > 0:
                rel_x = event.pos().x() - margin
                val = self.minimum() + int(round((rel_x / track_w) * rng))
                val = max(self.minimum(), min(self.maximum(), val))
                self.setValue(val)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):  # type: ignore[override]
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            margin = 5
            track_w = self.width() - (margin * 2)
            rng = self.maximum() - self.minimum()
            if track_w > 0 and rng > 0:
                rel_x = event.pos().x() - margin
                val = self.minimum() + int(round((rel_x / track_w) * rng))
                val = max(self.minimum(), min(self.maximum(), val))
                self.setValue(val)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):  # type: ignore[override]
        self.setSliderDown(False)
        self.sliderReleased.emit()
        super().mouseReleaseEvent(event)

    def set_cached_indices(self, indices: set):
        """Update the set of cached frame indices and repaint."""
        if self._cached_indices != indices:
            self._cached_indices = indices
            self.update()

    def set_annotated_indices(self, indices: set):
        """Update the set of annotated frame indices and repaint."""
        if self._annotated_indices != indices:
            self._annotated_indices = indices
            self.update()

    def set_bookmarks(self, bookmarks: set):
        """Update the set of bookmarked frame indices and repaint."""
        if self._bookmarks != bookmarks:
            self._bookmarks = set(bookmarks)
            self.update()

    def set_missing_indices(self, missing: set):
        """Update the set of missing frame indices and repaint."""
        if self._missing_indices != missing:
            self._missing_indices = set(missing)
            self.update()

    def set_in_out(self, in_point: Optional[int], out_point: Optional[int]):
        """Update In and Out loop range and repaint."""
        if self._in_point != in_point or self._out_point != out_point:
            self._in_point = in_point
            self._out_point = out_point
            self.update()

    def set_show_cached(self, show: bool):
        self._show_cached = show
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):  # type: ignore[override]
        super().paintEvent(event)
        if self.maximum() <= self.minimum():
            return
            
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        
        # Calculate track boundaries (handle is 10px wide, so 5px margin on each side)
        margin = 5
        track_w = self.width() - (margin * 2)
        rng = self.maximum() - self.minimum()
        if rng <= 0 or track_w <= 0:
            p.end()
            return

        groove_mid_y = self.height() // 2

        # --- Draw In / Out range shaded loop region & brackets ---
        if self._in_point is not None and self._out_point is not None and self._in_point < self._out_point:
            r_in = max(self.minimum(), min(self.maximum(), self._in_point))
            r_out = max(self.minimum(), min(self.maximum(), self._out_point))
            x_in = margin + int(((r_in - self.minimum()) / rng) * track_w)
            x_out = margin + int(((r_out - self.minimum()) / rng) * track_w)
            
            # Subtle highlight bar between In and Out
            p.fillRect(x_in, groove_mid_y - 6, max(2, x_out - x_in), 12, QtGui.QColor(255, 214, 10, 35))
            
            # In bracket marker: [
            bracket_pen = QtGui.QPen(QtGui.QColor("#ffd60a"), 2)
            p.setPen(bracket_pen)
            p.drawLine(x_in, groove_mid_y - 6, x_in, groove_mid_y + 6)
            p.drawLine(x_in, groove_mid_y - 6, x_in + 3, groove_mid_y - 6)
            p.drawLine(x_in, groove_mid_y + 6, x_in + 3, groove_mid_y + 6)

            # Out bracket marker: ]
            p.drawLine(x_out, groove_mid_y - 6, x_out, groove_mid_y + 6)
            p.drawLine(x_out, groove_mid_y - 6, x_out - 3, groove_mid_y - 6)
            p.drawLine(x_out, groove_mid_y + 6, x_out - 3, groove_mid_y + 6)

        # --- Draw cached frame indicators (green bar at bottom of groove) ---
        if self._show_cached and self._cached_indices:
            cache_pen = QtGui.QPen(QtGui.QColor("#2ecc71"))  # Green
            cache_pen.setWidth(2)
            p.setPen(cache_pen)
            groove_y = groove_mid_y + 3  # Just below groove center
            for idx in self._cached_indices:
                if self.minimum() <= idx <= self.maximum():
                    ratio = (idx - self.minimum()) / rng
                    cx = margin + int(ratio * track_w)
                    p.drawLine(cx, groove_y, cx, groove_y + 3)

        # --- Draw missing frame indicators (red tick marks) ---
        if self._missing_indices:
            miss_pen = QtGui.QPen(QtGui.QColor("#ff453a"))  # Red
            miss_pen.setWidth(2)
            p.setPen(miss_pen)
            for idx in self._missing_indices:
                if self.minimum() <= idx <= self.maximum():
                    ratio = (idx - self.minimum()) / rng
                    cx = margin + int(ratio * track_w)
                    p.drawLine(cx, groove_mid_y - 4, cx, groove_mid_y + 4)

        # --- Draw bookmark indicators (cyan tick marks) ---
        if self._bookmarks:
            bm_pen = QtGui.QPen(QtGui.QColor("#00d2ff"))  # Cyan
            bm_pen.setWidth(2)
            p.setPen(bm_pen)
            for idx in self._bookmarks:
                if self.minimum() <= idx <= self.maximum():
                    ratio = (idx - self.minimum()) / rng
                    cx = margin + int(ratio * track_w)
                    p.drawLine(cx, groove_mid_y + 4, cx, groove_mid_y + 9)
                    
        # --- Draw annotated frame indicators (orange tick marks above groove) ---
        if self._annotated_indices:
            annot_pen = QtGui.QPen(QtGui.QColor("#ff9f0a"))  # Orange
            annot_pen.setWidth(2)
            p.setPen(annot_pen)
            groove_y = groove_mid_y - 3  # Just above groove center
            for idx in self._annotated_indices:
                if self.minimum() <= idx <= self.maximum():
                    ratio = (idx - self.minimum()) / rng
                    cx = margin + int(ratio * track_w)
                    p.drawLine(cx, groove_y - 5, cx, groove_y)
        
        # Draw custom blue tick marks
        interval = self.tickInterval()
        if interval <= 0:
            interval = self.pageStep()
        if interval > 0:
            tick_pen = QtGui.QPen(QtGui.QColor("#4a90e2"))
            tick_pen.setWidth(1)
            p.setPen(tick_pen)
            
            for val in range(self.minimum(), self.maximum() + 1, interval):
                ratio = (val - self.minimum()) / rng
                tx = margin + int(ratio * track_w)
                p.drawLine(tx, self.height() - 4, tx, self.height())

        # Draw the playhead line
        ratio = (self.value() - self.minimum()) / max(1, rng)
        px = margin + int(ratio * track_w)
        playhead_pen = QtGui.QPen(QtGui.QColor("#4a90e2"))
        playhead_pen.setWidth(2)
        p.setPen(playhead_pen)
        p.drawLine(px, 0, px, self.height())
        p.end()


from core.color_manager import ColorManager


if getattr(sys, 'frozen', False):
    _APP_ROOT = os.path.dirname(sys.executable)
else:
    _APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PREFS_PATH = os.path.join(_APP_ROOT, "prefs.json")


from gui.vispy_viewport import VispyViewport

# PlayerViewport class removed, using VispyViewport instead


class FilePropertiesHUD(QtWidgets.QFrame):
    """Semi-transparent overlay for displaying file metadata."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 20, 180);
                border: 1px solid rgba(100, 100, 100, 100);
                border-radius: 8px;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }
            QLabel {
                background: transparent;
                border: none;
                color: #ccc;
            }
            .title {
                color: #4a90e2;
                font-weight: bold;
                font-size: 14px;
            }
            .key {
                color: #888;
                font-weight: bold;
            }
            .value {
                color: #ddd;
            }
        """)
        
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(6)
        
        self.title_label = QtWidgets.QLabel("File Properties")
        self.title_label.setProperty("class", "title")
        self.layout.addWidget(self.title_label)
        
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll_content = QtWidgets.QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QtWidgets.QGridLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll)
        
        self.setMinimumWidth(350)
        self.setMinimumHeight(400)
        self.hide()

    def update_info(self, media_info):
        """Update items in the grid based on MediaInfo."""
        # Clear layout
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not media_info:
            return

        row = 0
        
        # Helper to add rows
        def add_row(key, value):
            nonlocal row
            klbl = QtWidgets.QLabel(f"{key}:")
            klbl.setStyleSheet("color: #888; font-weight: bold;")
            vlbl = QtWidgets.QLabel(str(value))
            vlbl.setStyleSheet("color: #ddd;")
            vlbl.setWordWrap(True)
            self.scroll_layout.addWidget(klbl, row, 0)
            self.scroll_layout.addWidget(vlbl, row, 1)
            row += 1

        # Basic Info
        filename = os.path.basename(media_info.path)
        add_row("File", filename)
        add_row("Type", media_info.type.capitalize())
        add_row("Resolution", f"{media_info.size[0]} x {media_info.size[1]}" if media_info.size[0] > 0 else "Unknown")
        add_row("Frames", media_info.frame_count)
        add_row("FPS", f"{media_info.fps:.3f}")
        
        if media_info.format:
            add_row("Format", media_info.format)
        if media_info.codec:
            add_row("Codec", media_info.codec)
            
        # Path
        add_row("Path", media_info.path)

        # Metadata / Extra Tags
        if media_info.metadata:
            separator = QtWidgets.QFrame()
            separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
            separator.setStyleSheet("background-color: #333;")
            self.scroll_layout.addWidget(separator, row, 0, 1, 2)
            row += 1
            
            # Sort keys for better readability
            for k in sorted(media_info.metadata.keys()):
                # Skip things we already showed or internal info
                if k in ('format_long', 'codec_long'):
                    continue
                v = media_info.metadata[k]
                # Truncate long strings
                if isinstance(v, str) and len(v) > 100:
                    v = v[:97] + "..."
                add_row(k, v)
        
        self.scroll_layout.setColumnStretch(1, 1)
        self.adjustSize()
        # Limit max height
        if self.height() > 500:
            self.setFixedHeight(500)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.adjustSize()




class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.current_index = 0
        self.exposure = 0.0
        self.gamma = 1.0
        self.channel_mode = 'RGB'
        self.alpha_mode = 'RGB'
        self.compare_loaded = False
        self.compare_offset = 0
        self.side_by_side = False
        self.wipe_mode = False
        self.playing = False
        self.loop = True
        self.playback_speed = 1.0
        self._elapsed_timer = None
        self._play_start_index = 0
        self.annotations = {}
        self.setWindowTitle("VFXPlayer")
        self.resize(1280, 800)
        self.setMinimumSize(800, 500)

        # Set Window Icon
        icon_path = os.path.join(_APP_ROOT, "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        elif os.path.exists(os.path.join(_APP_ROOT, "logo.ico")):
            self.setWindowIcon(QtGui.QIcon(os.path.join(_APP_ROOT, "logo.ico")))

        # Apply Apple Pro Dark Studio Theme
        self.setStyleSheet("""
            QMainWindow, QWidget { 
                background-color: #121214; 
                color: #e5e5ea; 
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", Inter, sans-serif; 
            }
            QMenuBar { 
                background-color: #161618; 
                color: #c7c7cc; 
                font-size: 12px; 
                font-weight: 500; 
                border-bottom: 1px solid #28282b; 
                padding: 2px 6px; 
            }
            QMenuBar::item { 
                background: transparent; 
                padding: 4px 10px; 
                border-radius: 5px; 
                margin: 1px; 
            }
            QMenuBar::item:selected { 
                background-color: #28282c; 
                color: #ffffff; 
            }
            QMenuBar::item:pressed { 
                background-color: #0a84ff; 
                color: #ffffff; 
            }
            QMenu { 
                background-color: #1c1c1e; 
                color: #f5f5f7; 
                border: 1px solid #323236; 
                border-radius: 8px; 
                padding: 5px; 
                font-size: 12px; 
            }
            QMenu::item { 
                padding: 6px 24px 6px 10px; 
                border-radius: 5px; 
            }
            QMenu::item:selected { 
                background-color: #0a84ff; 
                color: #ffffff; 
            }
            QMenu::separator { 
                height: 1px; 
                background-color: #2c2c30; 
                margin: 4px 6px; 
            }
            QScrollBar:vertical { 
                background: #121214; 
                width: 10px; 
            }
            QScrollBar::handle:vertical { 
                background: #323236; 
                min-height: 24px; 
                border-radius: 5px; 
            }
            QScrollBar::handle:vertical:hover { 
                background: #48484a; 
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
                height: 0px; 
            }
            QSplitter::handle { 
                background: #242428; 
            }
            QStatusBar { 
                background-color: #121214; 
                border-top: 1px solid #28282b; 
                color: #8e8e93; 
            }
            QPushButton { 
                background-color: #202024; 
                border: 1px solid #323236; 
                border-radius: 6px; 
                padding: 4px 10px; 
                font-size: 12px; 
                font-weight: 500; 
                color: #d1d1d6; 
            }
            QPushButton:hover { 
                background-color: #2c2c30; 
                border-color: #48484a; 
                color: #ffffff; 
            }
            QPushButton:pressed { 
                background-color: #0a84ff; 
                color: #ffffff; 
                border-color: #0a84ff; 
            }
            QLineEdit { 
                background-color: #1a1a1c; 
                border: 1px solid #323236; 
                border-radius: 5px; 
                padding: 3px 6px; 
                color: #f5f5f7; 
                selection-background-color: #0a84ff; 
            }
            QLineEdit:focus { 
                border-color: #0a84ff; 
            }
            QComboBox {
                background-color: #202024;
                color: #e5e5ea;
                border: 1px solid #323236;
                border-radius: 6px;
                padding: 3px 20px 3px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:hover {
                background-color: #2c2c30;
                border-color: #48484a;
                color: #ffffff;
            }
            QComboBox:focus, QComboBox:on {
                border-color: #0a84ff;
                background-color: #2c2c30;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a1a1aa;
                margin-right: 6px;
            }
            QComboBox::down-arrow:hover {
                border-top: 5px solid #0a84ff;
            }
            QComboBox QAbstractItemView {
                background-color: #1c1c1e;
                color: #f5f5f7;
                border: 1px solid #323236;
                border-radius: 6px;
                padding: 4px;
                outline: 0px;
                selection-background-color: #0a84ff;
                selection-color: #ffffff;
            }
            QComboBox QAbstractItemView::item {
                min-height: 24px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #0a84ff;
                color: #ffffff;
            }
            QDoubleSpinBox, QSpinBox { 
                background-color: #1a1a1c; 
                border: 1px solid #323236; 
                border-radius: 5px; 
                padding: 3px 5px; 
                color: #f5f5f7; 
            }
            QDoubleSpinBox:focus, QSpinBox:focus { 
                border-color: #0a84ff; 
            }
            QLabel { color: #98989d; }
        """)

        # Viewports
        try:
            self.viewport = VispyViewport(main_window=self, role='primary', slot_index=0)
            self.viewport_b = VispyViewport(main_window=self, role='secondary', slot_index=1)
            self.viewport_c = VispyViewport(main_window=self, role='viewport_c', slot_index=2)
            self.viewport_d = VispyViewport(main_window=self, role='viewport_d', slot_index=3)
            self.viewport_e = VispyViewport(main_window=self, role='viewport_e', slot_index=4)
            self.viewport_f = VispyViewport(main_window=self, role='viewport_f', slot_index=5)
            
            self.viewports = [self.viewport, self.viewport_b, self.viewport_c, self.viewport_d, self.viewport_e, self.viewport_f]
            
            for vp in self.viewports:
                vp.pixel_probe_hover.connect(self._on_pixel_probe)
                vp.stroke_finished.connect(self._on_stroke_finished)
                vp.single_clicked.connect(self._toggle_play_pause)
                vp.double_clicked.connect(lambda: self._toggle_fullscreen(not self.fullscreen))
                vp.right_clicked.connect(self._show_context_menu)
                if vp != self.viewport:
                    vp.hide()
        except Exception as e:
            raise e

        self.grid_container = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(2)

        # Comparison state
        self.wipe_mode = False
        self.side_by_side = False
        self.grid_mode = 'single'
        self.show_slot_badges = True
        self.fullscreen = False
        self.properties_visible = False
        self.compare_offset = 0
        # Annotation state: frame_index -> list of stroke dicts
        # Stroke dict schema:
        # {'tool': str, 'points': [(x,y)...], 'points2': [(x,y)...]|None,
        #  'color': (r,g,b,a), 'width': int, 'text': str|None}
        self.annotations = {}
        self.bookmarks: set[int] = set()
        self.version_group: Optional[VersionGroup] = None
        self.scopes_dialog: Optional[ScopesDialog] = None
        self._annotation_undo_stack: dict[int, list] = {}  # per-frame undo snapshots
        self._annotation_redo_stack: dict[int, list] = {}  # per-frame redo snapshots
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        
        # We use a QVBoxLayout for the main structure, but the HUD will be inside a container
        self.main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Viewport Area
        self.viewport_container = QtWidgets.QWidget()
        self.viewport_layout = QtWidgets.QVBoxLayout(self.viewport_container)
        self.viewport_layout.setContentsMargins(0, 0, 0, 0)

        self.playlist_service = PlaylistService()
        self._current_kitsu_shot: Optional[PlaylistItem] = None
        self._current_kitsu_versions: List[Dict[str, Any]] = []
        self._current_kitsu_tasks: List[str] = []
        self._active_kitsu_task: Optional[str] = None
        self._active_kitsu_version_num: Optional[int] = None
        self._syncing_task_ui: bool = False
        self._switching_kitsu_version: bool = False
        self._custom_playlist_active: bool = False

        # Main Split / Side layout container
        self.main_split_container = QtWidgets.QWidget()
        self.main_split_layout = QtWidgets.QHBoxLayout(self.main_split_container)
        self.main_split_layout.setContentsMargins(0, 0, 0, 0)
        self.main_split_layout.setSpacing(0)

        # Playlist / Shot Browser Drawer (Left dock)
        self.playlist_widget = PlaylistWidget(self.playlist_service, parent=self)
        self.playlist_widget.hide()
        self.playlist_widget.shot_selected.connect(self._on_playlist_shot_selected)
        self.playlist_widget.load_kitsu_requested.connect(self._on_load_kitsu_playlist)
        self.playlist_widget.publish_kitsu_requested.connect(self._on_publish_kitsu_review)
        self.playlist_widget.version_compare_requested.connect(self._show_version_compare_dialog)
        self.playlist_widget.compare_prev_version_requested.connect(self._version_compare_prev)
        self.playlist_widget.open_kitsu_requested.connect(self._on_kitsu_shot_opened)
        self.playlist_widget.add_media_requested.connect(self._on_playlist_add_files)
        self.playlist_widget.add_folder_requested.connect(self._on_playlist_add_folder)
        self.playlist_widget.files_dropped.connect(self.add_media_paths_to_playlist)
        self.playlist_widget.send_to_slot_requested.connect(self._on_playlist_send_to_slot)
        self.main_split_layout.addWidget(self.playlist_widget)

        # Global Window Shortcuts for PageUp / PageDown playlist navigation
        self._shortcut_page_up = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_PageUp), self)
        self._shortcut_page_up.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self._shortcut_page_up.activated.connect(self.playlist_prev_shot)

        self._shortcut_page_down = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_PageDown), self)
        self._shortcut_page_down.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self._shortcut_page_down.activated.connect(self.playlist_next_shot)

        self.main_split_layout.addWidget(self.grid_container, 1)
        
        # Build Color Grading Panel (Task 2)
        self._build_color_grading_panel()
        self.main_split_layout.addWidget(self.color_grading_panel)

        self.viewport_layout.addWidget(self.main_split_container)
        
        self.main_layout.addWidget(self.viewport_container, 1)

        # Annotation toolbar (hidden until activated)
        self.annotation_toolbar = AnnotationToolbar()
        self.annotation_toolbar.hide()
        self.main_layout.addWidget(self.annotation_toolbar)

        # File Properties HUD (Overlay)
        self.props_hud = FilePropertiesHUD(self.viewport_container)
        self.props_hud.move(20, 20) # Top-leftish


        # HUD Container (Bottom)
        self.hud_container = QtWidgets.QFrame()
        self.hud_container.setFixedHeight(60)
        self.hud_container.setStyleSheet("background-color: #181818; border-top: 1px solid #2a2a2a;")
        self.hud_layout = QtWidgets.QVBoxLayout(self.hud_container)
        self.hud_layout.setContentsMargins(0, 0, 0, 0)
        self.hud_layout.setSpacing(0)
        self.main_layout.addWidget(self.hud_container)

        # Init wipe UI (hidden by default)
        self.side_by_side = False
        self.wipe_mode = False
        self._init_wipe_ui()

        # Load prefs first to get OCIO config path
        self.prefs = {}
        self._load_prefs()
        ocio_config = self.prefs.get('ocio_config')
        if ocio_config:
            if not os.path.isabs(ocio_config):
                resolved = os.path.normpath(os.path.join(_APP_ROOT, ocio_config))
                if os.path.isfile(resolved):
                    ocio_config = resolved
            elif not os.path.isfile(ocio_config):
                rel_cand = os.path.normpath(os.path.join(_APP_ROOT, "configs", "ocio", "config.ocio"))
                if os.path.isfile(rel_cand):
                    ocio_config = rel_cand
                else:
                    ocio_config = None

        # Initialize OCIO
        try:
            self.color_manager = ColorManager(config_path=ocio_config)
        except Exception:
            # Minimal fallback to avoid crash
            class DummyCM:
                def __init__(self, config_path=None):
                    self.config = None
                    self.ocio_enabled = False
                    self.input_cs = None
                    self.output_cs = None
                def rebuild_processor(self): pass
                def process(self, arr, exp, gam): return arr 
            self.color_manager = DummyCM()

        # Color controls state
        self.exposure = 0.0
        self.gamma = 1.0
        self.channel_mode = 'RGB'
        self.alpha_mode = 'RGB'
        self.prefs = {}
        self._load_prefs()
        # Apply prefs to manager
        self.color_manager.ocio_enabled = getattr(self, '_prefs_ocio_enabled', False)
        self.color_manager.input_cs = getattr(self, '_prefs_input_cs', self.color_manager.input_cs)
        self.color_manager.output_cs = getattr(self, '_prefs_output_cs', self.color_manager.output_cs)
        self.color_manager.rebuild_processor()

        # Build menus & HUD
        self._build_menu()
        self._build_hud()
        self._wire_annotation_toolbar()
        


        # 6 Slots player cores (C, D, E, F also initialized to support up to 6 synchronized versions)
        from core.player_core import PlayerCore
        primary_cap = getattr(self.core, 'cache_capacity', 500)
        self.core_b = PlayerCore(cache_capacity=primary_cap, prefetch_enabled=False)
        self.core_c = PlayerCore(cache_capacity=primary_cap, prefetch_enabled=False)
        self.core_d = PlayerCore(cache_capacity=primary_cap, prefetch_enabled=False)
        self.core_e = PlayerCore(cache_capacity=primary_cap, prefetch_enabled=False)
        self.core_f = PlayerCore(cache_capacity=primary_cap, prefetch_enabled=False)
        
        self.cores = [self.core, self.core_b, self.core_c, self.core_d, self.core_e, self.core_f]
        
        # Initial OCIO sync to background loaders
        self._sync_ocio_to_loader()
        self.compare_loaded = False

        # Playback state
        self.timer = QtCore.QTimer(self)
        try:
            self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        except Exception:
            pass
        self.timer.timeout.connect(self._advance_frame)
        self.playing = False
        self.play_direction = 1
        self.current_index = 0
        self.loop = True
        self.playback_speed = 1.0
        self._elapsed_timer = None
        self._play_start_index = 0
        self._force_fit_next_frame = False

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self._setup_apple_status_bar()
        self._status_base = "Ready"
        self._update_status(self._status_base)
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status_metrics)
        self.status_timer.start(500)

        # Pending frame poller
        self._pending_frame_timer = QtCore.QTimer(self)
        self._pending_frame_timer.setInterval(16)
        self._pending_frame_timer.timeout.connect(self._check_pending_frame)
        self._target_frame_index = -1

        # Audio engine (video files only)
        self._audio_player = None
        self._audio_output = None
        self._audio_muted = False
        self._audio_volume = 1.0
        self._has_audio = False
        self._audio_seek_grace_until = 0.0
        try:
            self._audio_player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(self._audio_volume)
        except Exception:
            self._audio_player = None
            self._audio_output = None

        # Auto-hide UI (Cinema Mode) setup
        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)
        self.viewport_container.setMouseTracking(True)
        self._ui_visible = True
        self._media_loaded = False
        self._ui_autohide_timer = QtCore.QTimer(self)
        self._ui_autohide_timer.setSingleShot(True)
        self._ui_autohide_timer.setInterval(2500)
        self._ui_autohide_timer.timeout.connect(self._hide_ui_controls)

        self.installEventFilter(self)
        self.central_widget.installEventFilter(self)
        self.viewport_container.installEventFilter(self)
        if hasattr(self, 'viewport'):
            self.viewport.installEventFilter(self)
        if hasattr(self, 'viewport_b'):
            self.viewport_b.installEventFilter(self)

        self._set_grid_layout('single')

    def _setup_apple_status_bar(self):
        """Construct an Apple-engineered modular pro status bar with badges."""
        self.status.setSizeGripEnabled(False)
        self.status.setStyleSheet("""
            QStatusBar {
                background-color: #121214;
                border-top: 1px solid #28282b;
                color: #8e8e93;
                min-height: 28px;
                max-height: 28px;
                padding: 0 8px;
            }
            QStatusBar::item {
                border: none;
            }
        """)

        badge_style = """
            QLabel {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 5px;
                color: #d1d1d6;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Inter, sans-serif;
            }
        """
        mono_badge_style = """
            QLabel {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 5px;
                color: #d1d1d6;
                padding: 2px 8px;
                font-family: "SF Mono", Consolas, "Cascadia Code", monospace;
            }
        """
        self._badge_style = badge_style
        self._mono_badge_style = mono_badge_style

        # --- Left Section: Media Specs & Status ---
        self.status_left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QHBoxLayout(self.status_left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.status_state_badge = QtWidgets.QLabel("● READY")
        self.status_state_badge.setStyleSheet(badge_style + "QLabel { color: #8e8e93; font-weight: 600; }")

        self.status_res_badge = QtWidgets.QLabel("No Media")
        self.status_res_badge.setStyleSheet(mono_badge_style)
        self.status_res_badge.setToolTip("Media Resolution")

        self.status_frames_badge = QtWidgets.QLabel("0 Frames")
        self.status_frames_badge.setStyleSheet(mono_badge_style)
        self.status_frames_badge.setToolTip("Total Frames in Sequence")

        self.status_fps_badge = QtWidgets.QLabel("24.00 fps")
        self.status_fps_badge.setStyleSheet(mono_badge_style)
        self.status_fps_badge.setToolTip("Playback Frame Rate")

        left_layout.addWidget(self.status_state_badge)
        left_layout.addWidget(self.status_res_badge)
        left_layout.addWidget(self.status_frames_badge)
        left_layout.addWidget(self.status_fps_badge)

        self.status.addWidget(self.status_left_widget)

        # --- Center Section: Live Pixel Probe ---
        self.lbl_probe = QtWidgets.QLabel("")
        self.lbl_probe.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_probe.setStyleSheet("""
            QLabel {
                color: #a1a1aa;
                font-family: "SF Mono", Consolas, "Cascadia Code", monospace;
                font-size: 11px;
                font-weight: 500;
                padding: 0 10px;
            }
        """)
        self.status.addWidget(self.lbl_probe, 1)

        # --- Right Section: Cache Meter & Timecode ---
        self.status_right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QHBoxLayout(self.status_right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.status_cache_badge = QtWidgets.QLabel("Cache: 0/0 (0%)")
        self.status_cache_badge.setStyleSheet(mono_badge_style)
        self.status_cache_badge.setToolTip("RAM Cache Usage & Total Memory")

        self.status_timecode_badge = QtWidgets.QLabel("00:00:00:00")
        self.status_timecode_badge.setStyleSheet(mono_badge_style + "QLabel { color: #0a84ff; font-weight: 600; }")
        self.status_timecode_badge.setToolTip("SMPTE Timecode (HH:MM:SS:FF)")

        right_layout.addWidget(self.status_cache_badge)
        right_layout.addWidget(self.status_timecode_badge)

        self.status.addPermanentWidget(self.status_right_widget)

    def _build_hud(self):
        """Construct the bottom Heads-Up Display with Apple Pro segmented controls."""
        # --- ROW 1: Timeline Slider ---
        self.slider_container = QtWidgets.QWidget()
        self.slider_container.setFixedHeight(24)
        self.slider_container.setStyleSheet("background-color: #121214; border-bottom: 1px solid #28282b;")
        slider_layout = QtWidgets.QHBoxLayout(self.slider_container)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        
        self.frame_slider = PlayheadSlider()
        self.frame_slider.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.frame_slider.valueChanged.connect(self.seek)
        self.frame_slider.sliderReleased.connect(self._on_scrub_finished)
        
        slider_layout.addWidget(self.frame_slider)
        self.hud_layout.addWidget(self.slider_container)
        
        # --- ROW 2: Apple Pro Transport Controls ---
        self.controls_container = QtWidgets.QWidget()
        self.controls_container.setFixedHeight(40)
        self.controls_container.setStyleSheet("background-color: #161618; border-top: 1px solid #28282b;")
        controls_layout = QtWidgets.QHBoxLayout(self.controls_container)
        controls_layout.setContentsMargins(12, 4, 12, 4)
        controls_layout.setSpacing(10)

        # 1. Range Pill (In / Out)
        range_pill = QtWidgets.QWidget()
        range_pill.setStyleSheet("""
            QWidget {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 6px;
            }
        """)
        range_layout = QtWidgets.QHBoxLayout(range_pill)
        range_layout.setContentsMargins(6, 2, 6, 2)
        range_layout.setSpacing(5)

        lbl_in = QtWidgets.QLabel("In:")
        lbl_in.setStyleSheet("color: #8e8e93; font-size: 11px; font-weight: 600; border: none; background: transparent;")
        self.range_start_edit = QtWidgets.QLineEdit("0")
        self.range_start_edit.setMinimumWidth(48)
        self.range_start_edit.setMaximumWidth(70)
        self.range_start_edit.setFixedHeight(22)
        self.range_start_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.range_start_edit.setStyleSheet("""
            QLineEdit {
                background-color: #141416;
                color: #f5f5f7;
                border: 1px solid #38383c;
                border-radius: 4px;
                padding: 1px 4px;
                font-family: "SF Mono", Consolas, monospace;
                font-size: 11px;
                font-weight: 600;
            }
            QLineEdit:focus { border-color: #0a84ff; }
        """)
        self.range_start_edit.editingFinished.connect(self._update_range)

        lbl_out = QtWidgets.QLabel("Out:")
        lbl_out.setStyleSheet("color: #8e8e93; font-size: 11px; font-weight: 600; border: none; background: transparent;")
        self.range_end_edit = QtWidgets.QLineEdit("100")
        self.range_end_edit.setMinimumWidth(48)
        self.range_end_edit.setMaximumWidth(70)
        self.range_end_edit.setFixedHeight(22)
        self.range_end_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.range_end_edit.setStyleSheet("""
            QLineEdit {
                background-color: #141416;
                color: #f5f5f7;
                border: 1px solid #38383c;
                border-radius: 4px;
                padding: 1px 4px;
                font-family: "SF Mono", Consolas, monospace;
                font-size: 11px;
                font-weight: 600;
            }
            QLineEdit:focus { border-color: #0a84ff; }
        """)
        self.range_end_edit.editingFinished.connect(self._update_range)

        range_layout.addWidget(lbl_in)
        range_layout.addWidget(self.range_start_edit)
        range_layout.addWidget(lbl_out)
        range_layout.addWidget(self.range_end_edit)
        controls_layout.addWidget(range_pill)

        controls_layout.addStretch(1) # Left spacer

        # 2. Segmented Transport Controls Pill
        transport_pill = QtWidgets.QWidget()
        transport_pill.setStyleSheet("""
            QWidget {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 8px;
            }
        """)
        transport_layout = QtWidgets.QHBoxLayout(transport_pill)
        transport_layout.setContentsMargins(3, 2, 3, 2)
        transport_layout.setSpacing(2)

        transport_btn_style = """
            QPushButton {
                background-color: transparent;
                color: #d1d1d6;
                border: none;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 500;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #38383c;
                color: #0a84ff;
            }
        """

        self.btn_first = QtWidgets.QPushButton("⏮")
        self.btn_first.setFixedSize(30, 26)
        self.btn_first.setStyleSheet(transport_btn_style)
        self.btn_first.setToolTip("Go to First Frame (Home)")
        self.btn_first.clicked.connect(self._go_to_start)
        transport_layout.addWidget(self.btn_first)

        self.btn_prev = QtWidgets.QPushButton("◀")
        self.btn_prev.setFixedSize(30, 26)
        self.btn_prev.setStyleSheet(transport_btn_style)
        self.btn_prev.setToolTip("Previous Frame (Left Arrow)")
        self.btn_prev.clicked.connect(lambda: self.seek(self.current_index - 1))
        transport_layout.addWidget(self.btn_prev)

        self.btn_play = QtWidgets.QPushButton("▶")
        self.btn_play.setFixedSize(34, 26)
        self.btn_play.setCheckable(True)
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_play.setStyleSheet(transport_btn_style + """
            QPushButton:checked {
                color: #30d158;
                font-weight: bold;
            }
        """)
        self.btn_play.clicked.connect(self._toggle_play_button)
        transport_layout.addWidget(self.btn_play)

        self.btn_next = QtWidgets.QPushButton("▶")
        self.btn_next.setFixedSize(30, 26)
        self.btn_next.setStyleSheet(transport_btn_style)
        self.btn_next.setToolTip("Next Frame (Right Arrow)")
        self.btn_next.clicked.connect(lambda: self.seek(self.current_index + 1))
        transport_layout.addWidget(self.btn_next)

        self.btn_last = QtWidgets.QPushButton("⏭")
        self.btn_last.setFixedSize(30, 26)
        self.btn_last.setStyleSheet(transport_btn_style)
        self.btn_last.setToolTip("Go to Last Frame (End)")
        self.btn_last.clicked.connect(self._go_to_end)
        transport_layout.addWidget(self.btn_last)

        controls_layout.addWidget(transport_pill)

        # Current Frame Pill with Total Frame indicator
        frame_pill = QtWidgets.QWidget()
        frame_pill.setStyleSheet("""
            QWidget {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 6px;
            }
        """)
        frame_layout = QtWidgets.QHBoxLayout(frame_pill)
        frame_layout.setContentsMargins(6, 2, 6, 2)
        frame_layout.setSpacing(4)

        self.curr_frame_edit = QtWidgets.QLineEdit("0")
        self.curr_frame_edit.setMinimumWidth(52)
        self.curr_frame_edit.setMaximumWidth(70)
        self.curr_frame_edit.setFixedHeight(22)
        self.curr_frame_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.curr_frame_edit.setStyleSheet("""
            QLineEdit {
                background-color: #141416;
                color: #ffffff;
                font-weight: 700;
                border: 1px solid #38383c;
                border-radius: 4px;
                padding: 1px 4px;
                font-size: 12px;
                font-family: "SF Mono", Consolas, monospace;
            }
            QLineEdit:focus { border-color: #0a84ff; }
        """)
        self.curr_frame_edit.returnPressed.connect(self._on_frame_input)

        self.lbl_total_frames_inline = QtWidgets.QLabel("/ 0")
        self.lbl_total_frames_inline.setStyleSheet("""
            color: #8e8e93;
            font-size: 11px;
            font-weight: 500;
            border: none;
            background: transparent;
            font-family: "SF Mono", Consolas, monospace;
            padding-right: 2px;
        """)
        frame_layout.addWidget(self.curr_frame_edit)
        frame_layout.addWidget(self.lbl_total_frames_inline)
        controls_layout.addWidget(frame_pill)

        # Annotate Button
        self.btn_annotate = QtWidgets.QPushButton("✏ Annotate")
        self.btn_annotate.setCheckable(True)
        self.btn_annotate.setFixedSize(94, 28)
        self.btn_annotate.setToolTip("Toggle Annotation Mode [Shortcut: N or Shift+A]")
        self.btn_annotate.setStyleSheet("""
            QPushButton {
                background-color: #1e1e22;
                color: #d1d1d6;
                font-size: 11px;
                border: 1px solid #2c2c30;
                border-radius: 6px;
                font-weight: 600;
                padding: 0 8px;
            }
            QPushButton:checked {
                color: #ffffff;
                background-color: #0a84ff;
                border-color: #0a84ff;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
        """)
        self.btn_annotate.clicked.connect(self._toggle_annotate_mode)
        controls_layout.addWidget(self.btn_annotate)

        # Grade Button (Near Annotate)
        self.btn_grade = QtWidgets.QPushButton("🎨 Grade")
        self.btn_grade.setCheckable(True)
        self.btn_grade.setFixedSize(82, 28)
        self.btn_grade.setToolTip("Toggle ASC CDL Color Grading Panel [Ctrl+G]")
        self.btn_grade.setStyleSheet("""
            QPushButton {
                background-color: #1e1e22;
                color: #d1d1d6;
                font-size: 11px;
                border: 1px solid #2c2c30;
                border-radius: 6px;
                font-weight: 600;
                padding: 0 8px;
            }
            QPushButton:checked {
                color: #ffffff;
                background-color: #0a84ff;
                border-color: #0a84ff;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
        """)
        self.btn_grade.clicked.connect(lambda: self._toggle_grade_panel())
        controls_layout.addWidget(self.btn_grade)

        # False Color Button (Near Annotate)
        self.btn_false_color = QtWidgets.QPushButton("🌈 False Color")
        self.btn_false_color.setCheckable(True)
        self.btn_false_color.setFixedSize(104, 28)
        self.btn_false_color.setToolTip("Toggle 10-Zone False Color Exposure Heatmap [Ctrl+Alt+F]")
        self.btn_false_color.setStyleSheet("""
            QPushButton {
                background-color: #1e1e22;
                color: #d1d1d6;
                font-size: 11px;
                border: 1px solid #2c2c30;
                border-radius: 6px;
                font-weight: 600;
                padding: 0 8px;
            }
            QPushButton:checked {
                color: #ffffff;
                background-color: #ff9500;
                border-color: #ff9500;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
        """)
        self.btn_false_color.clicked.connect(lambda: self._toggle_false_color(self.btn_false_color.isChecked()))
        controls_layout.addWidget(self.btn_false_color)

        # Task & Version Selector Pill (Kitsu / Shot Versions & Tasks Switcher)
        self.task_version_pill = QtWidgets.QWidget()
        self.task_version_pill.setStyleSheet("""
            QWidget {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 6px;
            }
        """)
        tv_layout = QtWidgets.QHBoxLayout(self.task_version_pill)
        tv_layout.setContentsMargins(5, 2, 5, 2)
        tv_layout.setSpacing(4)

        lbl_task_icon = QtWidgets.QLabel("🗂")
        lbl_task_icon.setStyleSheet("border: none; background: transparent; font-size: 11px;")

        self.combo_task = QtWidgets.QComboBox()
        self.combo_task.setToolTip("Active Pipeline Task (Edit, Lighting, Compositing...) [Ctrl+Alt+Left/Right]")
        self.combo_task.setStyleSheet("""
            QComboBox {
                background-color: #141416;
                color: #38bdf8;
                border: 1px solid #38383c;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                font-weight: 600;
                min-width: 68px;
            }
            QComboBox:hover { border-color: #0a84ff; }
            QComboBox::drop-down { border: none; width: 14px; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1e;
                color: #f5f5f7;
                selection-background-color: #0a84ff;
                selection-color: #ffffff;
                border: 1px solid #38383c;
            }
        """)
        self.combo_task.currentTextChanged.connect(self._on_task_combo_changed)

        self.combo_version = QtWidgets.QComboBox()
        self.combo_version.setToolTip("Active Version for selected task [Ctrl+Up/Down]")
        self.combo_version.setStyleSheet("""
            QComboBox {
                background-color: #141416;
                color: #30d158;
                border: 1px solid #38383c;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                font-weight: 600;
                min-width: 68px;
            }
            QComboBox:hover { border-color: #30d158; }
            QComboBox::drop-down { border: none; width: 14px; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1e;
                color: #f5f5f7;
                selection-background-color: #16a34a;
                selection-color: #ffffff;
                border: 1px solid #38383c;
            }
        """)
        self.combo_version.currentIndexChanged.connect(self._on_version_combo_changed)

        self.combo_task.setFixedHeight(24)
        self.combo_version.setFixedHeight(24)

        self.btn_quick_compare = QtWidgets.QPushButton("⇄ Wipe")
        self.btn_quick_compare.setFixedHeight(24)
        self.btn_quick_compare.setMinimumWidth(62)
        self.btn_quick_compare.setToolTip("Compare with Previous Version in Wipe Mode [Ctrl+Alt+C]")
        self.btn_quick_compare.setStyleSheet("""
            QPushButton {
                background-color: #141416;
                color: #e4e4e7;
                border: 1px solid #38383c;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
                border-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0369a1;
            }
        """)
        self.btn_quick_compare.clicked.connect(lambda: self._version_compare_prev())

        tv_layout.addWidget(lbl_task_icon)
        tv_layout.addWidget(self.combo_task)
        tv_layout.addWidget(self.combo_version)
        tv_layout.addWidget(self.btn_quick_compare)

        controls_layout.addWidget(self.task_version_pill)

        controls_layout.addStretch(1) # Right spacer

        # 3. Channel indicator
        self.lbl_channel = QtWidgets.QLabel("RGB")
        self.lbl_channel.setToolTip("Current Channel (Hotkeys: R, G, B, A, C)")
        self.lbl_channel.setStyleSheet("""
            QLabel {
                color: #0a84ff;
                background-color: rgba(10, 132, 255, 0.12);
                border: 1px solid rgba(10, 132, 255, 0.3);
                border-radius: 5px;
                font-weight: 700;
                font-size: 11px;
                padding: 3px 8px;
            }
        """)
        controls_layout.addWidget(self.lbl_channel)

        # FPS Pill
        fps_pill = QtWidgets.QWidget()
        fps_pill.setStyleSheet("""
            QWidget {
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 6px;
            }
        """)
        fps_layout = QtWidgets.QHBoxLayout(fps_pill)
        fps_layout.setContentsMargins(6, 2, 6, 2)
        fps_layout.setSpacing(5)

        lbl_fps_tag = QtWidgets.QLabel("FPS:")
        lbl_fps_tag.setStyleSheet("color: #8e8e93; font-size: 11px; font-weight: 600; border: none; background: transparent;")
        self.fps_edit = QtWidgets.QLineEdit("24.00")
        self.fps_edit.setMinimumWidth(58)
        self.fps_edit.setMaximumWidth(70)
        self.fps_edit.setFixedHeight(22)
        self.fps_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.fps_edit.setStyleSheet("""
            QLineEdit {
                background-color: #141416;
                color: #f5f5f7;
                border: 1px solid #38383c;
                border-radius: 4px;
                padding: 1px 4px;
                font-family: "SF Mono", Consolas, monospace;
                font-size: 11px;
                font-weight: 600;
            }
            QLineEdit:focus { border-color: #0a84ff; }
        """)
        self.fps_edit.editingFinished.connect(self._update_timer_interval)

        fps_layout.addWidget(lbl_fps_tag)
        fps_layout.addWidget(self.fps_edit)
        controls_layout.addWidget(fps_pill)

        # Loop Toggle Pill
        self.loop_btn = QtWidgets.QPushButton("Loop")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        self.loop_btn.setFixedSize(62, 26)
        self.loop_btn.setToolTip("Loop Playback (L)")
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e1e22;
                color: #8e8e93;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #2c2c30;
                border-radius: 6px;
                padding: 2px 4px;
                text-align: center;
            }
            QPushButton:checked {
                color: #0a84ff;
                background-color: rgba(10, 132, 255, 0.12);
                border-color: rgba(10, 132, 255, 0.35);
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
        """)
        self.loop_btn.toggled.connect(self._toggle_loop)
        controls_layout.addWidget(self.loop_btn)

        # Speed Dropdown Pill
        self.speed_btn = QtWidgets.QPushButton("1.0x")
        self.speed_btn.setFixedSize(70, 26)
        self.speed_btn.setToolTip("Playback Speed. Click to select.")
        self.speed_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e1e22;
                color: #d1d1d6;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #2c2c30;
                border-radius: 6px;
                font-family: "SF Mono", Consolas, monospace;
                padding: 2px 14px 2px 6px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
                border-color: #38383c;
            }
            QPushButton::menu-indicator {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                right: 4px;
                width: 8px;
            }
        """)
        speed_menu = QtWidgets.QMenu(self)
        speed_menu.setStyleSheet("""
            QMenu { background: #1c1c1e; color: #f5f5f7; border: 1px solid #323236; border-radius: 6px; padding: 4px; }
            QMenu::item:selected { background: #0a84ff; }
        """)
        self.speed_speeds = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0]
        for s in self.speed_speeds:
            act = speed_menu.addAction(f"{s}x")
            act.triggered.connect(lambda checked, val=s: self._on_speed_changed(val))
        self.speed_btn.setMenu(speed_menu)
        controls_layout.addWidget(self.speed_btn)

        # Audio Mute & Volume
        self.btn_mute = QtWidgets.QPushButton("🔊")
        self.btn_mute.setFixedSize(32, 26)
        self.btn_mute.setCheckable(True)
        self.btn_mute.setChecked(False)
        self.btn_mute.setToolTip("Mute / Unmute audio (M)")
        self.btn_mute.setStyleSheet("""
            QPushButton {
                background-color: #1e1e22;
                color: #d1d1d6;
                font-size: 13px;
                border: 1px solid #2c2c30;
                border-radius: 6px;
                padding: 0px;
                text-align: center;
            }
            QPushButton:checked { color: #ff9f0a; border-color: #ff9f0a; background-color: rgba(255, 159, 10, 0.12); }
            QPushButton:hover { background-color: #2c2c30; color: #ffffff; }
        """)
        self.btn_mute.clicked.connect(self._toggle_mute)
        controls_layout.addWidget(self.btn_mute)

        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(70)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #2c2c30;
                height: 3px;
                background: #1e1e22;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #38383c;
                width: 10px;
                height: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover { background: #0a84ff; }
            QSlider::sub-page:horizontal { background: #0a84ff; border-radius: 1px; }
        """)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        controls_layout.addWidget(self.volume_slider)

        self.hud_layout.addWidget(self.controls_container)



        # OCIO controls are now in the top bar (see _build_menu)


    # Legacy toolbar and duplicate control methods removed.


    def _init_wipe_ui(self):
        """Create wipe slider row and add to main layout (hidden initially)."""
        self.wipe_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.wipe_slider.setRange(0, 1000)
        self.wipe_slider.setValue(500)
        self.wipe_slider.valueChanged.connect(self._update_wipe)
        self.wipe_label = QtWidgets.QLabel("Wipe")
        self.wipe_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.wipe_label.setStyleSheet("background: #111; color: #aaa;")
        wipe_container = QtWidgets.QHBoxLayout()
        wipe_container.setContentsMargins(4, 0, 4, 0)
        wipe_container.addWidget(self.wipe_label)
        wipe_container.addWidget(self.wipe_slider, 1)
        self._wipe_row = QtWidgets.QWidget()
        self._wipe_row.setLayout(wipe_container)
        self._wipe_row.setFixedHeight(40) # Fix height to prevent expansion
        # Add to the viewport layout (above/below the splitter)
        # self.viewport_layout is the QVBoxLayout holding the splitter
        # We probably want it below the splitter or above. 
        # Actually, standard wipe UI usually overlays or sits near controls. 
        # Let's put it in the main_layout, just above HUD? 
        # Or keep it in viewport container.
        self.viewport_layout.addWidget(self._wipe_row)
        self._wipe_row.hide()

    # ---------- UI Construction ----------
    # Legacy UI construction methods removed

    def _build_menu(self):
        # Style Menu Bar and Dropdown Menus
        self.menuBar().setStyleSheet("""
            QMenuBar {
                background-color: #141416;
                color: #c8c8cc;
                font-size: 12px;
                font-weight: 600;
                font-family: 'Segoe UI', sans-serif;
                border-bottom: 1px solid #2a2a2e;
                padding: 1px 4px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 4px;
                margin: 2px 1px;
            }
            QMenuBar::item:selected {
                background-color: #2c2c30;
                color: #ffffff;
            }
            QMenuBar::item:pressed {
                background-color: #0a84ff;
                color: #ffffff;
            }
            QMenu {
                background-color: #1c1c1e;
                color: #e0e0e4;
                border: 1px solid #38383a;
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            QMenu::item {
                padding: 5px 24px 5px 10px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0a84ff;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #38383a;
                margin: 4px 6px;
            }
        """)

        # File Menu
        file_menu = self.menuBar().addMenu("File")

        self.viewer_container = QtWidgets.QWidget()
        self.viewer_container.setStyleSheet("background: transparent;")
        vc_layout = QtWidgets.QHBoxLayout(self.viewer_container)
        vc_layout.setContentsMargins(10, 0, 5, 0)
        vc_layout.setSpacing(6)

        # Dropdown Combobox QSS
        header_combo_style = """
            QComboBox {
                background-color: #242427;
                color: #e0e0e5;
                border: 1px solid #3c3c40;
                border-radius: 4px;
                padding: 2px 20px 2px 8px;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 600;
                min-height: 20px;
                max-height: 20px;
            }
            QComboBox:hover {
                background-color: #2c2c30;
                border-color: #0a84ff;
                color: #ffffff;
            }
            QComboBox:focus, QComboBox:on {
                border-color: #0a84ff;
                background-color: #2c2c30;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a0a0a5;
                margin-right: 6px;
            }
            QComboBox::down-arrow:hover {
                border-top: 5px solid #0a84ff;
            }
            QComboBox QAbstractItemView {
                background-color: #1c1c1e;
                color: #e0e0e5;
                border: 1px solid #3c3c40;
                border-radius: 6px;
                padding: 4px;
                outline: 0px;
                selection-background-color: #0a84ff;
                selection-color: #ffffff;
            }
            QComboBox QAbstractItemView::item {
                min-height: 24px;
                padding: 3px 10px;
                border-radius: 3px;
                white-space: nowrap;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2c2c30;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #0a84ff;
                color: #ffffff;
            }
            QComboBox QAbstractItemView QScrollBar:vertical {
                background: #1c1c1e;
                width: 8px;
                margin: 2px 0px 2px 0px;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView QScrollBar::handle:vertical {
                background: #3c3c40;
                min-height: 20px;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {
                background: #505055;
            }
            QComboBox QAbstractItemView QScrollBar::add-line:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """

        header_reset_btn_style = """
            QPushButton {
                background: #242427;
                color: #a0a0a5;
                border: 1px solid #3c3c40;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
                min-width: 18px; max-width: 18px;
                min-height: 18px; max-height: 18px;
                padding: 0;
            }
            QPushButton:hover {
                background: #2c2c30;
                color: #ffffff;
                border-color: #0a84ff;
            }
            QPushButton:pressed {
                background: #0a84ff;
                color: #ffffff;
            }
        """

        header_slider_style = """
            QSlider::groove:horizontal {
                border: 1px solid #333336;
                height: 4px;
                background: #18181a;
                margin: 2px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #c8c8cc;
                border: 1px solid #5a5a5e;
                width: 10px;
                height: 12px;
                margin: -4px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
                border-color: #0a84ff;
            }
        """

        ocio_btn_style = """
            QPushButton {
                background-color: #242427;
                color: #a0a0a5;
                border: 1px solid #3c3c40;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                min-height: 20px; max-height: 20px;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                color: #ffffff;
                border-color: #5a5a60;
            }
            QPushButton:checked {
                background-color: #0a84ff;
                border-color: #0a84ff;
                color: #ffffff;
            }
        """

        # --- GPU GAIN / GAMMA SLIDERS ---
        # Exposure (Gain)
        self.exp_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.exp_slider.setRange(-8000, 8000)
        self.exp_slider.setValue(int(self.exposure * 1000))
        self.exp_slider.setFixedWidth(75)
        self.exp_slider.setToolTip("Exposure (f-stops). Click 'Ev' to reset.")
        self.exp_slider.setStyleSheet(header_slider_style)

        self.lbl_exp_val = QtWidgets.QLabel(f"{self.exposure:+.2f}")
        self.lbl_exp_val.setFixedWidth(35)
        self.lbl_exp_val.setStyleSheet("color: #0a84ff; font-family: Consolas, monospace; font-size: 11px; font-weight: bold;")

        self.exp_slider.valueChanged.connect(self._on_exposure_changed)

        exp_box = QtWidgets.QHBoxLayout()
        exp_box.setSpacing(2)
        btn_e = QtWidgets.QPushButton("Ev")
        btn_e.setToolTip("Reset Exposure to +0.00")
        btn_e.setStyleSheet(header_reset_btn_style)
        btn_e.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        btn_e.clicked.connect(self._reset_exposure)
        exp_box.addWidget(btn_e)
        exp_box.addWidget(self.exp_slider)
        exp_box.addWidget(self.lbl_exp_val)
        vc_layout.addLayout(exp_box)

        # Gamma
        self.gam_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.gam_slider.setRange(100, 4000)
        self.gam_slider.setValue(int(self.gamma * 1000))
        self.gam_slider.setFixedWidth(75)
        self.gam_slider.setToolTip("Gamma. Click 'γ' to reset.")
        self.gam_slider.setStyleSheet(header_slider_style)

        self.lbl_gam_val = QtWidgets.QLabel(f"{self.gamma:.2f}")
        self.lbl_gam_val.setFixedWidth(30)
        self.lbl_gam_val.setStyleSheet("color: #0a84ff; font-family: Consolas, monospace; font-size: 11px; font-weight: bold;")

        self.gam_slider.valueChanged.connect(self._on_gamma_changed)

        gam_box = QtWidgets.QHBoxLayout()
        gam_box.setSpacing(2)
        btn_g = QtWidgets.QPushButton("γ")
        btn_g.setToolTip("Reset Gamma to 1.00")
        btn_g.setStyleSheet(header_reset_btn_style)
        btn_g.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        btn_g.clicked.connect(self._reset_gamma)
        gam_box.addWidget(btn_g)
        gam_box.addWidget(self.gam_slider)
        gam_box.addWidget(self.lbl_gam_val)
        vc_layout.addLayout(gam_box)

        vc_layout.addSpacing(4)

        lbl = QtWidgets.QLabel("V:")
        lbl.setStyleSheet("color: #0a84ff; font-weight: bold; font-size: 11px;")
        vc_layout.addWidget(lbl)

        self.viewer_combo = QtWidgets.QComboBox()
        self.viewer_combo.setMinimumWidth(115)
        self.viewer_combo.setMaximumWidth(160)
        self.viewer_combo.setStyleSheet(header_combo_style)
        self._populate_combo_with_auto_width(
            self.viewer_combo,
            self.color_manager.view_choices,
            self.color_manager.output_cs if self.color_manager.output_cs in self.color_manager.view_choices else None,
            min_popup_width=240,
            tooltip_prefix="Viewer ColorSpace: "
        )
        self.viewer_combo.currentTextChanged.connect(self._on_viewer_changed)
        vc_layout.addWidget(self.viewer_combo)

        open_action = QtGui.QAction("Open Media...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        open_comp_action = QtGui.QAction("Open Compare Media...", self)
        open_comp_action.setShortcut("Ctrl+Shift+O")
        open_comp_action.triggered.connect(self._open_file_compare)
        file_menu.addAction(open_comp_action)

        export_action = QtGui.QAction("Export / Convert Media...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._open_export_dialog)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        save_frame_action = QtGui.QAction("Save Frame...", self)
        save_frame_action.setShortcut("Ctrl+Shift+S")
        save_frame_action.setToolTip("Save current frame as image (without annotations)")
        save_frame_action.triggered.connect(self._save_current_frame)
        file_menu.addAction(save_frame_action)

        save_frame_annot_action = QtGui.QAction("Save Frame with Annotations...", self)
        save_frame_annot_action.setToolTip("Save current frame with annotations baked in")
        save_frame_annot_action.triggered.connect(self._save_frame_with_annotations)
        file_menu.addAction(save_frame_annot_action)

        export_annot_all_action = QtGui.QAction("Export All Annotated Frames...", self)
        export_annot_all_action.setShortcut("Ctrl+Shift+E")
        export_annot_all_action.setToolTip("Export images of all frames containing annotations")
        export_annot_all_action.triggered.connect(self._export_all_annotated_frames)
        file_menu.addAction(export_annot_all_action)

        contact_sheet_action = QtGui.QAction("Generate Review Contact Sheet...", self)
        contact_sheet_action.setToolTip("Generate HTML review contact sheet of annotated frames")
        contact_sheet_action.triggered.connect(self._export_contact_sheet)
        file_menu.addAction(contact_sheet_action)

        file_menu.addSeparator()

        save_annot_action = QtGui.QAction("Save Annotations...", self)
        save_annot_action.setToolTip("Save all annotations to a JSON file")
        save_annot_action.triggered.connect(self._save_annotations_to_file)
        file_menu.addAction(save_annot_action)

        load_annot_action = QtGui.QAction("Load Annotations...", self)
        load_annot_action.setToolTip("Load annotations from a JSON file")
        load_annot_action.triggered.connect(self._load_annotations_from_file)
        file_menu.addAction(load_annot_action)

        save_sidecar_action = QtGui.QAction("Save Review Sidecar (.review.json)", self)
        save_sidecar_action.setToolTip("Save annotations, bookmarks, and In/Out points to .review.json sidecar")
        save_sidecar_action.setShortcut("Ctrl+S")
        save_sidecar_action.triggered.connect(self._save_review_sidecar)
        file_menu.addAction(save_sidecar_action)

        load_sidecar_action = QtGui.QAction("Load Review Sidecar...", self)
        load_sidecar_action.setToolTip("Load review sidecar containing annotations and bookmarks")
        load_sidecar_action.triggered.connect(self._load_review_sidecar)
        file_menu.addAction(load_sidecar_action)

        file_menu.addSeparator()

        load_ocio_action = QtGui.QAction("Load OCIO Config...", self)
        load_ocio_action.triggered.connect(self._load_ocio_config_dialog)
        file_menu.addAction(load_ocio_action)

        settings_action = QtGui.QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View Menu
        view_menu = self.menuBar().addMenu("View")

        self.side_action = QtGui.QAction("Side-by-Side", self)
        self.side_action.setCheckable(True)
        self.side_action.setShortcut("S")
        self.side_action.triggered.connect(lambda: self._set_compare_mode('side'))
        view_menu.addAction(self.side_action)

        self.wipe_action = QtGui.QAction("Wipe", self)
        self.wipe_action.setCheckable(True)
        self.wipe_action.setShortcut("W")
        self.wipe_action.triggered.connect(lambda: self._set_compare_mode('wipe'))
        view_menu.addAction(self.wipe_action)

        view_menu.addSeparator()

        fit_action = QtGui.QAction("Fit to Window", self)
        fit_action.setShortcut("F")
        fit_action.triggered.connect(self.viewport.fit_to_window)
        view_menu.addAction(fit_action)

        metadata_action = QtGui.QAction("Show Metadata Panel...", self)
        metadata_action.setShortcut("Ctrl+I")
        metadata_action.triggered.connect(self._open_metadata_dialog)
        view_menu.addAction(metadata_action)

        scopes_action = QtGui.QAction("Scopes (Histogram / Waveform)...", self)
        scopes_action.setShortcut("Ctrl+H")
        scopes_action.setToolTip("Open real-time image histogram and RGB waveform analysis window")
        scopes_action.triggered.connect(self._toggle_scopes)
        view_menu.addAction(scopes_action)

        view_menu.addSeparator()

        self.minimal_action = QtGui.QAction("Minimal View (Borderless)", self)
        self.minimal_action.setCheckable(True)
        self.minimal_action.setChecked(getattr(self, 'cinema_mode_enabled', True))
        self.minimal_action.setShortcut("Ctrl+1")
        self.minimal_action.triggered.connect(lambda: self._set_view_preset('minimal'))
        view_menu.addAction(self.minimal_action)

        self.normal_action = QtGui.QAction("Normal View", self)
        self.normal_action.setCheckable(True)
        self.normal_action.setChecked(not getattr(self, 'cinema_mode_enabled', True))
        self.normal_action.setShortcut("Ctrl+2")
        self.normal_action.triggered.connect(lambda: self._set_view_preset('normal'))
        view_menu.addAction(self.normal_action)

        self.annot_view_action = QtGui.QAction("Annotation Mode", self)
        self.annot_view_action.setCheckable(True)
        self.annot_view_action.setShortcut("N")
        self.annot_view_action.setToolTip("Toggle Annotation toolbar and drawing mode (N or Alt+A)")
        self.annot_view_action.triggered.connect(self._toggle_annotate_mode)
        view_menu.addAction(self.annot_view_action)

        fs_action = QtGui.QAction("Fullscreen", self)
        fs_action.setCheckable(True)
        fs_action.setShortcut("F11")
        fs_action.triggered.connect(lambda: self._toggle_fullscreen(fs_action.isChecked()))
        view_menu.addAction(fs_action)

        guides_menu = view_menu.addMenu("Safe Guides")
        
        self.guides_toggle_action = QtGui.QAction("Show Guides", self)
        self.guides_toggle_action.setCheckable(True)
        self.guides_toggle_action.setShortcut("Ctrl+Shift+G")
        self.guides_toggle_action.triggered.connect(self._toggle_safe_guides)
        guides_menu.addAction(self.guides_toggle_action)
        
        guides_menu.addSeparator()
        
        self.guide_center_action = QtGui.QAction("Center Crosshair", self)
        self.guide_center_action.setCheckable(True)
        self.guide_center_action.setChecked(True)
        self.guide_center_action.triggered.connect(self._update_guides_config)
        guides_menu.addAction(self.guide_center_action)

        self.guide_thirds_action = QtGui.QAction("Rule of Thirds", self)
        self.guide_thirds_action.setCheckable(True)
        self.guide_thirds_action.setChecked(True)
        self.guide_thirds_action.triggered.connect(self._update_guides_config)
        guides_menu.addAction(self.guide_thirds_action)

        self.guide_action_action = QtGui.QAction("Action Safe (90%)", self)
        self.guide_action_action.setCheckable(True)
        self.guide_action_action.setChecked(True)
        self.guide_action_action.triggered.connect(self._update_guides_config)
        guides_menu.addAction(self.guide_action_action)

        self.guide_title_action = QtGui.QAction("Title Safe (80%)", self)
        self.guide_title_action.setCheckable(True)
        self.guide_title_action.setChecked(True)
        self.guide_title_action.triggered.connect(self._update_guides_config)
        guides_menu.addAction(self.guide_title_action)

        alpha_menu = view_menu.addMenu("Alpha Presentation")
        self._alpha_actions = {}
        alpha_group = QtGui.QActionGroup(self)
        for mode_name, label in [
            ('RGB', 'RGB (Ignore Alpha)'),
            ('Checkerboard', 'Checkerboard Background (VFX)'),
            ('Alpha', 'Alpha Grayscale (Matte)'),
            ('Black', 'Black Background'),
            ('White', 'White Background'),
        ]:
            act = QtGui.QAction(label, self)
            act.setCheckable(True)
            if mode_name == getattr(self, 'alpha_mode', 'RGB'):
                act.setChecked(True)
            act.triggered.connect(lambda checked, m=mode_name: self._set_alpha_mode(m))
            alpha_group.addAction(act)
            alpha_menu.addAction(act)
            self._alpha_actions[mode_name] = act

        view_menu.addSeparator()

        self.false_color_action = QtGui.QAction("False Color Exposure Scale", self)
        self.false_color_action.setCheckable(True)
        self.false_color_action.setShortcut("Ctrl+Alt+F")
        self.false_color_action.setStatusTip("Toggle 10-zone false color exposure & clipping heatmap")
        self.false_color_action.triggered.connect(self._toggle_false_color)
        view_menu.addAction(self.false_color_action)

        view_menu.addSeparator()

        # Grade Menu
        grade_menu = self.menuBar().addMenu("Grade")

        self.grade_panel_action = QtGui.QAction("Toggle Grading Panel", self)
        self.grade_panel_action.setCheckable(True)
        self.grade_panel_action.setShortcut("Ctrl+G")
        self.grade_panel_action.triggered.connect(self._toggle_grade_panel)
        grade_menu.addAction(self.grade_panel_action)

        grade_menu.addSeparator()

        import_cdl_action = QtGui.QAction("Import CDL XML...", self)
        import_cdl_action.triggered.connect(self._import_cdl)
        grade_menu.addAction(import_cdl_action)

        export_cdl_action = QtGui.QAction("Export CDL XML...", self)
        export_cdl_action.triggered.connect(self._export_cdl)
        grade_menu.addAction(export_cdl_action)

        grade_menu.addSeparator()

        reset_grade_action = QtGui.QAction("Reset All Grades", self)
        reset_grade_action.triggered.connect(self._reset_all_cdl)
        grade_menu.addAction(reset_grade_action)

        # Layout Menu
        layout_menu = self.menuBar().addMenu("Layout")

        single_view_act = QtGui.QAction("1-Up (Single View)", self)
        single_view_act.setShortcut("Ctrl+Alt+1")
        single_view_act.triggered.connect(lambda: self._set_grid_layout('single'))
        layout_menu.addAction(single_view_act)

        side_view_act = QtGui.QAction("2-Up (Side-by-Side)", self)
        side_view_act.setShortcut("Ctrl+Alt+2")
        side_view_act.triggered.connect(lambda: self._set_grid_layout('side'))
        layout_menu.addAction(side_view_act)

        grid4_view_act = QtGui.QAction("4-Up (2x2 Grid)", self)
        grid4_view_act.setShortcut("Ctrl+Alt+4")
        grid4_view_act.triggered.connect(lambda: self._set_grid_layout('grid4'))
        layout_menu.addAction(grid4_view_act)

        grid6_view_act = QtGui.QAction("6-Up (2x3 Grid)", self)
        grid6_view_act.setShortcut("Ctrl+Alt+6")
        grid6_view_act.triggered.connect(lambda: self._set_grid_layout('grid6'))
        layout_menu.addAction(grid6_view_act)

        layout_menu.addSeparator()

        load_slots_menu = layout_menu.addMenu("Load Media into Slot")
        
        # Use simple separate callbacks to prevent late-binding closure bugs
        load_slots_menu.addAction("Load into Slot 1 (Primary)...").triggered.connect(lambda: self._load_media_slot(0))
        load_slots_menu.addAction("Load into Slot 2 (Secondary)...").triggered.connect(lambda: self._load_media_slot(1))
        load_slots_menu.addAction("Load into Slot 3...").triggered.connect(lambda: self._load_media_slot(2))
        load_slots_menu.addAction("Load into Slot 4...").triggered.connect(lambda: self._load_media_slot(3))
        load_slots_menu.addAction("Load into Slot 5...").triggered.connect(lambda: self._load_media_slot(4))
        load_slots_menu.addAction("Load into Slot 6...").triggered.connect(lambda: self._load_media_slot(5))

        layout_menu.addSeparator()

        self.show_slot_badges_action = QtGui.QAction("Show Slot Badges in Grid", self)
        self.show_slot_badges_action.setCheckable(True)
        self.show_slot_badges_action.setChecked(getattr(self, 'show_slot_badges', True))
        self.show_slot_badges_action.setShortcuts([
            QtGui.QKeySequence("Ctrl+Alt+B"),
            QtGui.QKeySequence("Alt+B"),
        ])
        self.show_slot_badges_action.setToolTip("Toggle slot name badges in 2-up, 4-up, and 6-up layouts (Ctrl+Alt+B or Alt+B)")
        self.show_slot_badges_action.triggered.connect(self._toggle_slot_badges)
        layout_menu.addAction(self.show_slot_badges_action)

        # Annotate Menu
        annotate_menu = self.menuBar().addMenu("Annotate")

        self.annot_menu_action = QtGui.QAction("Toggle Annotation Mode", self)
        self.annot_menu_action.setCheckable(True)
        self.annot_menu_action.setShortcut("Shift+A")
        self.annot_menu_action.setToolTip("Toggle Annotation toolbar and drawing mode (N or Shift+A)")
        self.annot_menu_action.triggered.connect(self._toggle_annotate_mode)
        annotate_menu.addAction(self.annot_menu_action)

        annotate_menu.addSeparator()

        undo_annot_act = QtGui.QAction("Undo Stroke", self)
        undo_annot_act.setShortcut("Ctrl+Z")
        undo_annot_act.triggered.connect(self._annotation_undo)
        annotate_menu.addAction(undo_annot_act)

        redo_annot_act = QtGui.QAction("Redo Stroke", self)
        redo_annot_act.setShortcut("Ctrl+Shift+Z")
        redo_annot_act.triggered.connect(self._annotation_redo)
        annotate_menu.addAction(redo_annot_act)

        annotate_menu.addSeparator()

        clear_frame_act = QtGui.QAction("Clear Frame Annotations", self)
        clear_frame_act.triggered.connect(self._clear_annotations)
        annotate_menu.addAction(clear_frame_act)

        clear_all_act = QtGui.QAction("Clear All Annotations", self)
        clear_all_act.triggered.connect(self._clear_all_annotations)
        annotate_menu.addAction(clear_all_act)

        annotate_menu.addSeparator()

        save_annot_act = QtGui.QAction("Save Annotations to JSON...", self)
        save_annot_act.triggered.connect(self._save_annotations_to_file)
        annotate_menu.addAction(save_annot_act)

        load_annot_act = QtGui.QAction("Load Annotations from JSON...", self)
        load_annot_act.triggered.connect(self._load_annotations_from_file)
        annotate_menu.addAction(load_annot_act)

        save_sidecar_act = QtGui.QAction("Save Review Sidecar (.review.json)", self)
        save_sidecar_act.setToolTip("Save annotations, bookmarks, and In/Out points to .review.json sidecar")
        save_sidecar_act.triggered.connect(self._save_review_sidecar)
        annotate_menu.addAction(save_sidecar_act)

        load_sidecar_act = QtGui.QAction("Load Review Sidecar...", self)
        load_sidecar_act.setToolTip("Load annotations and bookmarks from .review.json sidecar")
        load_sidecar_act.triggered.connect(self._load_review_sidecar)
        annotate_menu.addAction(load_sidecar_act)

        annotate_menu.addSeparator()

        export_annot_all_act = QtGui.QAction("Export All Annotated Frames...", self)
        export_annot_all_act.setShortcut("Ctrl+Shift+E")
        export_annot_all_act.setToolTip("Export images of all frames containing annotations")
        export_annot_all_act.triggered.connect(self._export_all_annotated_frames)
        annotate_menu.addAction(export_annot_all_act)

        contact_sheet_annot_act = QtGui.QAction("Generate Review Contact Sheet...", self)
        contact_sheet_annot_act.setToolTip("Generate HTML review contact sheet of annotated frames")
        contact_sheet_annot_act.triggered.connect(self._export_contact_sheet)
        annotate_menu.addAction(contact_sheet_annot_act)

        strategy_menu = view_menu.addMenu("Playback Strategy")
        self.strategy_group = QtGui.QActionGroup(self)

        strategies = [
            ("Performance (Full Cache)", PlaybackStrategy.PERFORMANCE),
            ("Progressive (Sequential)", PlaybackStrategy.PROGRESSIVE),
            ("Stream Only (No RAM Cache)", PlaybackStrategy.STREAM),
            ("Read-behind Buffer", PlaybackStrategy.READ_BEHIND)
        ]

        for label, strat in strategies:
            act = QtGui.QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self.core.strategy == strat)
            act.triggered.connect(lambda checked, s=strat: self._set_playback_strategy(s))
            strategy_menu.addAction(act)
            self.strategy_group.addAction(act)

        # Playback Menu
        play_menu = self.menuBar().addMenu("Playback")

        play_action = QtGui.QAction("Play / Pause (Forward)", self)
        play_action.setShortcut("Space")
        play_action.triggered.connect(lambda: self.pause() if (self.playing and getattr(self, 'play_direction', 1) == 1) else self.play(direction=1))
        play_menu.addAction(play_action)

        play_rev_action = QtGui.QAction("Play Reverse", self)
        play_rev_action.setShortcut("Shift+Space")
        play_rev_action.setToolTip("Play backwards in reverse (Shift+Space / J)")
        play_rev_action.triggered.connect(self.play_reverse)
        play_menu.addAction(play_rev_action)

        stop_action = QtGui.QAction("Stop", self)
        stop_action.triggered.connect(self.stop)
        play_menu.addAction(stop_action)

        refresh_cache_action = QtGui.QAction("Refresh Timeline Cache", self)
        refresh_cache_action.setShortcut("C")
        refresh_cache_action.setToolTip("Flush and reload timeline frame cache (C)")
        refresh_cache_action.triggered.connect(self.refresh_timeline_cache)
        play_menu.addAction(refresh_cache_action)

        play_menu.addSeparator()

        in_action = QtGui.QAction("Set In Point", self)
        in_action.setShortcut("I")
        in_action.setToolTip("Set playback In point at current frame (I)")
        in_action.triggered.connect(self._set_in_point)
        play_menu.addAction(in_action)

        out_action = QtGui.QAction("Set Out Point", self)
        out_action.setShortcut("O")
        out_action.setToolTip("Set playback Out point at current frame (O)")
        out_action.triggered.connect(self._set_out_point)
        play_menu.addAction(out_action)

        clear_in_out_action = QtGui.QAction("Clear In/Out Points", self)
        clear_in_out_action.setShortcut("X")
        clear_in_out_action.setToolTip("Reset In/Out range to full clip (X)")
        clear_in_out_action.triggered.connect(self._clear_in_out_range)
        play_menu.addAction(clear_in_out_action)

        play_menu.addSeparator()

        bookmark_action = QtGui.QAction("Toggle Bookmark", self)
        bookmark_action.setShortcut("B")
        bookmark_action.setToolTip("Toggle bookmark marker at current frame (B)")
        bookmark_action.triggered.connect(self._toggle_bookmark)
        play_menu.addAction(bookmark_action)

        next_bm_action = QtGui.QAction("Next Bookmark / Annotation", self)
        next_bm_action.setShortcut("Shift+Right")
        next_bm_action.triggered.connect(self._jump_to_next_annotated_frame)
        play_menu.addAction(next_bm_action)

        prev_bm_action = QtGui.QAction("Previous Bookmark / Annotation", self)
        prev_bm_action.setShortcut("Shift+Left")
        prev_bm_action.triggered.connect(self._jump_to_prev_annotated_frame)
        play_menu.addAction(prev_bm_action)

        clear_bms_action = QtGui.QAction("Clear All Bookmarks", self)
        clear_bms_action.triggered.connect(self._clear_all_bookmarks)
        play_menu.addAction(clear_bms_action)

        play_menu.addSeparator()

        act_pan_info = QtGui.QAction("Pan Viewport (Middle Click Scrubs)", self)
        act_pan_info.setToolTip("Left-click drag pans the viewport. Middle-click drag scrubs the timeline (DJV style).")
        act_pan_info.triggered.connect(lambda: self.statusBar().showMessage("Left-click drag: Pan viewport | Middle-click drag: Scrub timeline", 4000))
        play_menu.addAction(act_pan_info)

        # Versions Menu
        versions_menu = self.menuBar().addMenu("Versions")

        next_ver_act = QtGui.QAction("Next Version", self)
        next_ver_act.setShortcut("Ctrl+Up")
        next_ver_act.setToolTip("Switch to next detected shot version (Ctrl+Up)")
        next_ver_act.triggered.connect(self._version_up)
        versions_menu.addAction(next_ver_act)

        prev_ver_act = QtGui.QAction("Previous Version", self)
        prev_ver_act.setShortcut("Ctrl+Down")
        prev_ver_act.setToolTip("Switch to previous detected shot version (Ctrl+Down)")
        prev_ver_act.triggered.connect(self._version_down)
        versions_menu.addAction(prev_ver_act)

        latest_ver_act = QtGui.QAction("Latest Version", self)
        latest_ver_act.setShortcut("Ctrl+Shift+Up")
        latest_ver_act.setToolTip("Switch directly to latest shot version (Ctrl+Shift+Up)")
        latest_ver_act.triggered.connect(self._version_latest)
        versions_menu.addAction(latest_ver_act)

        versions_menu.addSeparator()

        next_task_act = QtGui.QAction("Next Task (Edit → Lighting → Comp...)", self)
        next_task_act.setShortcut("Ctrl+Alt+Right")
        next_task_act.setToolTip("Cycle forward to next pipeline task render (Ctrl+Alt+Right)")
        next_task_act.triggered.connect(self._task_next)
        versions_menu.addAction(next_task_act)

        prev_task_act = QtGui.QAction("Previous Task (Comp → Lighting → Edit...)", self)
        prev_task_act.setShortcut("Ctrl+Alt+Left")
        prev_task_act.setToolTip("Cycle backward to previous pipeline task render (Ctrl+Alt+Left)")
        prev_task_act.triggered.connect(self._task_prev)
        versions_menu.addAction(prev_task_act)

        versions_menu.addSeparator()

        compare_ver_act = QtGui.QAction("Compare with Previous Version (Wipe)", self)
        compare_ver_act.setShortcut("Ctrl+Alt+C")
        compare_ver_act.setToolTip("Load previous version into B track and enable Wipe (Ctrl+Alt+C)")
        compare_ver_act.triggered.connect(lambda: self._version_compare_prev())
        versions_menu.addAction(compare_ver_act)

        versions_tasks_act = QtGui.QAction("Versions & Tasks for this Shot...", self)
        versions_tasks_act.setShortcut("Ctrl+Alt+V")
        versions_tasks_act.setToolTip("Inspect and compare all task versions (Edit, Comp, Lighting, Anim) in Wipe or Side-by-Side (Ctrl+Alt+V)")
        versions_tasks_act.triggered.connect(lambda: self._show_version_compare_dialog())
        versions_menu.addAction(versions_tasks_act)

        versions_menu.addSeparator()
        self.switch_task_ver_menu = versions_menu.addMenu("Switch Task / Version")

        # Studio Menu (Kitsu & Multi-Shot Review)
        studio_menu = self.menuBar().addMenu("Studio")

        toggle_playlist_act = QtGui.QAction("Toggle Playlist Panel", self)
        toggle_playlist_act.setShortcut("Ctrl+L")
        toggle_playlist_act.setToolTip("Show / Hide Shot Playlist Browser (Ctrl+L)")
        toggle_playlist_act.triggered.connect(self._toggle_playlist_panel)
        studio_menu.addAction(toggle_playlist_act)

        studio_menu.addSeparator()

        load_kitsu_act = QtGui.QAction("Load Playlist from Kitsu...", self)
        load_kitsu_act.setToolTip("Connect to Kitsu and load review playlist")
        load_kitsu_act.triggered.connect(self._on_load_kitsu_playlist)
        studio_menu.addAction(load_kitsu_act)

        open_kitsu_act = QtGui.QAction("Open Current Shot in Kitsu", self)
        open_kitsu_act.setShortcut("Ctrl+K")
        open_kitsu_act.setToolTip("Open current shot / task page in Kitsu web browser (Ctrl+K)")
        open_kitsu_act.triggered.connect(self._open_current_shot_in_kitsu)
        studio_menu.addAction(open_kitsu_act)

        publish_kitsu_act = QtGui.QAction("Publish Review Note to Kitsu...", self)
        publish_kitsu_act.setShortcut("Ctrl+Alt+P")
        publish_kitsu_act.setToolTip("Submit supervisor review comment, status update & annotated snapshot to Kitsu (Ctrl+Alt+P)")
        publish_kitsu_act.triggered.connect(self._on_publish_kitsu_review)
        studio_menu.addAction(publish_kitsu_act)

        studio_menu.addSeparator()

        kitsu_config_act = QtGui.QAction("Configure Kitsu Connection...", self)
        kitsu_config_act.setToolTip("Set Kitsu host URL and credentials")
        kitsu_config_act.triggered.connect(self._on_configure_kitsu)
        studio_menu.addAction(kitsu_config_act)

        # Cache management actions
        self.kitsu_clear_exit_act = QtGui.QAction("Clear Kitsu Cache on Exit", self)
        self.kitsu_clear_exit_act.setCheckable(True)
        self.kitsu_clear_exit_act.setChecked(bool(self.prefs.get("clear_kitsu_cache_on_exit", False)))
        self.kitsu_clear_exit_act.toggled.connect(self._on_toggle_clear_kitsu_cache_exit)
        studio_menu.addAction(self.kitsu_clear_exit_act)

        kitsu_clear_now_act = QtGui.QAction("Clear Kitsu Cache Now...", self)
        kitsu_clear_now_act.setToolTip("Free local storage by deleting all downloaded preview media and thumbnails")
        kitsu_clear_now_act.triggered.connect(self._on_clear_kitsu_cache_now)
        studio_menu.addAction(kitsu_clear_now_act)

        # Help Menu (Nuke style)
        help_menu = self.menuBar().addMenu("Help")

        shortcuts_action = QtGui.QAction("Keyboard Shortcuts...", self)
        shortcuts_action.setShortcut("F1")
        shortcuts_action.setToolTip("View full keyboard shortcuts & hotkey reference guide (F1)")
        shortcuts_action.triggered.connect(self._show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        docs_action = QtGui.QAction("Documentation / README...", self)
        docs_action.setToolTip("Open documentation & user guide")
        docs_action.triggered.connect(self._open_docs)
        help_menu.addAction(docs_action)

        github_action = QtGui.QAction("Visit GitHub Repository...", self)
        github_action.setToolTip("Open GitHub repository in browser")
        github_action.triggered.connect(self._open_github_repo)
        help_menu.addAction(github_action)

        help_menu.addSeparator()

        about_action = QtGui.QAction("About VFX Review Player...", self)
        about_action.setToolTip("About VFX Review Player version, author, and credits")
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

        # Add OCIO controls + Viewer Dropdown to Menu Bar (Corner Widget)
        if self.color_manager.config:
            # OCIO toggle button
            self.ocio_btn = QtWidgets.QPushButton("OCIO On" if self.color_manager.ocio_enabled else "OCIO Off")
            self.ocio_btn.setObjectName("OCIOToggleBtn")
            self.ocio_btn.setCheckable(True)
            self.ocio_btn.setChecked(self.color_manager.ocio_enabled)
            self.ocio_btn.setStyleSheet(ocio_btn_style)
            self.ocio_btn.toggled.connect(self._toggle_ocio_enabled)
            vc_layout.addWidget(self.ocio_btn)

            # Input colorspace
            in_lbl = QtWidgets.QLabel("In:")
            in_lbl.setStyleSheet("color: #0a84ff; font-weight: bold; font-size: 11px;")
            vc_layout.addWidget(in_lbl)
            self.ocio_input_combo = QtWidgets.QComboBox()
            self.ocio_input_combo.setMinimumWidth(115)
            self.ocio_input_combo.setMaximumWidth(160)
            self.ocio_input_combo.setStyleSheet(header_combo_style)
            self._populate_combo_with_auto_width(
                self.ocio_input_combo,
                self.color_manager.input_choices,
                self.color_manager.input_cs,
                min_popup_width=280,
                tooltip_prefix="Input Transform: "
            )
            self.ocio_input_combo.currentTextChanged.connect(self._on_ocio_changed)
            vc_layout.addWidget(self.ocio_input_combo)

            # Output colorspace
            out_lbl = QtWidgets.QLabel("Out:")
            out_lbl.setStyleSheet("color: #0a84ff; font-weight: bold; font-size: 11px;")
            vc_layout.addWidget(out_lbl)
            self.ocio_output_combo = QtWidgets.QComboBox()
            self.ocio_output_combo.setMinimumWidth(115)
            self.ocio_output_combo.setMaximumWidth(160)
            self.ocio_output_combo.setStyleSheet(header_combo_style)
            self._populate_combo_with_auto_width(
                self.ocio_output_combo,
                self.color_manager.output_choices,
                self.color_manager.output_cs,
                min_popup_width=280,
                tooltip_prefix="Output Transform: "
            )
            self.ocio_output_combo.currentTextChanged.connect(self._on_ocio_changed)
            vc_layout.addWidget(self.ocio_output_combo)

        self.menuBar().setCornerWidget(self.viewer_container, QtCore.Qt.Corner.TopRightCorner)

    def _populate_combo_with_auto_width(self, combo: QtWidgets.QComboBox, items: list, current_value: str = None, min_popup_width: int = 240, tooltip_prefix: str = ""):
        """Populate combo box, set per-item tooltips, and automatically resize popup dropdown to fit full text without cropping."""
        combo.blockSignals(True)
        combo.clear()
        if items:
            combo.addItems(items)
            fm = combo.fontMetrics()
            max_w = 0
            for idx, item in enumerate(items):
                text_str = str(item)
                combo.setItemData(idx, text_str, QtCore.Qt.ItemDataRole.ToolTipRole)
                w = fm.horizontalAdvance(text_str) if hasattr(fm, 'horizontalAdvance') else fm.width(text_str)
                if w > max_w:
                    max_w = w
            # Add padding for vertical scrollbar (~20px) + item horizontal padding (20px) + frame borders (16px)
            needed_w = max(min_popup_width, max_w + 56)
            combo.view().setMinimumWidth(needed_w)
            combo.view().setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
            if current_value and current_value in items:
                combo.setCurrentText(current_value)
            elif items:
                combo.setCurrentIndex(0)
        combo.blockSignals(False)
        curr = combo.currentText()
        combo.setToolTip(f"{tooltip_prefix}{curr}" if curr else "")

    def _load_ocio_config_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open OCIO Config", "", "OCIO Files (*.ocio);;All Files (*.*)")
        if path:
            try:
                os.environ['OCIO'] = path
                self.color_manager = ColorManager(config_path=path) # Reload
                self._update_ocio_ui()
                self._show_frame(self.current_index)
                cfg_val = path
                try:
                    rel = os.path.relpath(path, _APP_ROOT)
                    if not rel.startswith('..'):
                        cfg_val = rel.replace('\\', '/')
                except Exception:
                    pass
                self.prefs['ocio_config'] = cfg_val
                self._save_prefs()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load config: {e}")

    def _update_ocio_ui(self):
        if not self.color_manager.config: return
        # Update combo boxes if they exist
        if hasattr(self, 'ocio_input_combo'):
            self._populate_combo_with_auto_width(
                self.ocio_input_combo,
                self.color_manager.input_choices,
                self.color_manager.input_cs,
                min_popup_width=280,
                tooltip_prefix="Input Transform: "
            )
                
        if hasattr(self, 'ocio_output_combo'):
            self._populate_combo_with_auto_width(
                self.ocio_output_combo,
                self.color_manager.output_choices,
                self.color_manager.output_cs,
                min_popup_width=280,
                tooltip_prefix="Output Transform: "
            )
            
        if hasattr(self, 'viewer_combo'):
            self._populate_combo_with_auto_width(
                self.viewer_combo,
                self.color_manager.view_choices,
                self.color_manager.output_cs,
                min_popup_width=240,
                tooltip_prefix="Viewer ColorSpace: "
            )
                
        if hasattr(self, 'ocio_btn'):
            self.ocio_btn.setChecked(self.color_manager.ocio_enabled)


    def _on_viewer_changed(self, text):
        if not text: return
        if hasattr(self, 'viewer_combo'):
            self.viewer_combo.setToolTip(f"Viewer ColorSpace: {text}")
        if text != self.color_manager.output_cs:
            self.color_manager.output_cs = text
            self.color_manager.rebuild_processor()
            self._sync_ocio_to_loader()  # Re-process cached frames
            if self.core.frame_count():
                self._show_frame(self.current_index)
            self._save_prefs()
            
            if hasattr(self, 'ocio_output_combo'):
                idx = self.ocio_output_combo.findText(text)
                if idx >= 0:
                    self.ocio_output_combo.blockSignals(True)
                    self.ocio_output_combo.setCurrentIndex(idx)
                    self.ocio_output_combo.setToolTip(f"Output Transform: {text}")
                    self.ocio_output_combo.blockSignals(False)

    def _on_ocio_changed(self, *_):
        if not self.color_manager.config: return
        
        in_cs = self.ocio_input_combo.currentText()
        out_cs = self.ocio_output_combo.currentText()
        
        if in_cs:
            self.ocio_input_combo.setToolTip(f"Input Transform: {in_cs}")
        if out_cs:
            self.ocio_output_combo.setToolTip(f"Output Transform: {out_cs}")
        
        if in_cs and in_cs != self.color_manager.input_cs:
            self.color_manager.input_cs = in_cs
            
        if out_cs and out_cs != self.color_manager.output_cs:
            self.color_manager.output_cs = out_cs
            if hasattr(self, 'viewer_combo'):
                idx = self.viewer_combo.findText(out_cs)
                if idx >= 0:
                    self.viewer_combo.blockSignals(True)
                    self.viewer_combo.setCurrentIndex(idx)
                    self.viewer_combo.setToolTip(f"Viewer ColorSpace: {out_cs}")
                    self.viewer_combo.blockSignals(False)
            
        self.color_manager.rebuild_processor()
        self._sync_ocio_to_loader()  # Re-process cached frames
        self._save_prefs()
        
        if self.core.frame_count():
            self._show_frame(self.current_index)

    def _toggle_ocio_enabled(self, enabled: bool):
        self.color_manager.ocio_enabled = enabled
        self.ocio_btn.setText("OCIO On" if enabled else "OCIO Off")
        self.color_manager.rebuild_processor()
        self._sync_ocio_to_loader()  # Re-process cached frames
        if self.core.frame_count():
            self._show_frame(self.current_index)
        self._save_prefs()

    def _sync_ocio_to_loader(self):
        """Sync OCIO params to background loader threads and clear cache."""
        enabled = self.color_manager.ocio_enabled
        input_cs = self.color_manager.input_cs or ""
        output_cs = self.color_manager.get_resolved_output_cs()
        config_path = self.color_manager.config_path or ""
        
        # Update all slot loaders
        cores = getattr(self, 'cores', []) or [self.core]
        if hasattr(self, 'core_b') and self.core_b not in cores:
            cores.append(self.core_b)
            
        for c in cores:
            c.loader.set_ocio_params(enabled, input_cs, output_cs, config_path)
            if hasattr(c, 'color_pipeline'):
                c.color_pipeline.set_ocio_params(enabled, input_cs, output_cs, config_path)
            with c.cache_lock:
                c.cache.clear()
                c.loader.clear_pending()

    def _on_exposure_changed(self, val: int):
        self.exposure = float(val / 1000.0)
        if hasattr(self, 'lbl_exp_val'):
            self.lbl_exp_val.setText(f"{self.exposure:+.2f}")
        if hasattr(self, 'core') and hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.set_grade_params(exposure=self.exposure)
            
        # Refresh current frame with new exposure (no cache clear!)
        if self.core.frame_count():
            self._show_frame(self.current_index)
        
        self._save_prefs()

    def _on_gamma_changed(self, val: int):
        self.gamma = float(val / 1000.0)
        if hasattr(self, 'lbl_gam_val'):
            self.lbl_gam_val.setText(f"{self.gamma:.2f}")
        if hasattr(self, 'core') and hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.set_grade_params(gamma=self.gamma)
            
        # Refresh current frame with new gamma (no cache clear!)
        if self.core.frame_count():
            self._show_frame(self.current_index)
            
        self._save_prefs()

    def _reset_exposure(self):
        self.exp_slider.setValue(0)

    def _reset_gamma(self):
        self.gam_slider.setValue(1000)

    def _set_channel(self, mode: str):
        if self.channel_mode == mode and mode != 'RGB':
            self.channel_mode = 'RGB' # Toggle back to RGB
        else:
            self.channel_mode = mode
            
        if hasattr(self, 'lbl_channel'):
            self.lbl_channel.setText(self.channel_mode)
            if self.channel_mode == 'RGB':
                self.lbl_channel.setStyleSheet("color: #4a90e2; font-weight: bold; font-size: 14px; padding-right: 10px;")
            else:
                self.lbl_channel.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 14px; padding-right: 10px;")
            
        if hasattr(self, 'viewport'):
            self.viewport.set_channel_mode(self.channel_mode)
        if hasattr(self, 'viewports'):
            for vp in self.viewports:
                vp.set_channel_mode(self.channel_mode)
        if hasattr(self, 'core') and hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.set_channel_mode(self.channel_mode)

        if self.core.frame_count():
            self._show_frame(self.current_index)

    def _set_alpha_mode(self, mode: str):
        """Set alpha presentation mode ('RGB', 'Checkerboard', 'Alpha', 'Black', 'White')."""
        self.alpha_mode = mode
        if hasattr(self, 'viewport'):
            self.viewport.set_alpha_mode(mode)
        if hasattr(self, 'viewports'):
            for vp in self.viewports:
                vp.set_alpha_mode(mode)
        if hasattr(self, 'core') and hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.set_alpha_mode(mode)
        if hasattr(self, '_alpha_actions'):
            act = self._alpha_actions.get(mode)
            if act and not act.isChecked():
                act.setChecked(True)
        if hasattr(self, 'lbl_channel'):
            if mode != 'RGB':
                self.lbl_channel.setText(f"{self.channel_mode} | {mode[:5]}")
            else:
                self.lbl_channel.setText(self.channel_mode)
        if self.core.frame_count():
            self._show_frame(self.current_index)

    def _cycle_alpha_mode(self):
        """Cycle through Alpha display modes (Shift+A)."""
        modes = ['RGB', 'Checkerboard', 'Alpha', 'Black', 'White']
        curr = getattr(self, 'alpha_mode', 'RGB')
        next_idx = (modes.index(curr) + 1) % len(modes) if curr in modes else 0
        self._set_alpha_mode(modes[next_idx])

    def _on_pixel_probe(self, x: float, y: float):
        if not hasattr(self, 'lbl_probe') or not hasattr(self, 'core') or self.core.frame_count() == 0:
            return
        if not self.lbl_probe.isVisible():
            return
            
        frame_raw = self.core.get_frame(self.current_index)
        if frame_raw is None:
            return
            
        ix, iy = int(x), int(y)
        h, w = frame_raw.shape[:2]
        
        if 0 <= ix < w and 0 <= iy < h:
            pixel = frame_raw[iy, ix]
            if frame_raw.shape[2] >= 4:
                r, g, b, a = pixel[:4]
                text = f"X:{ix:<4} Y:{iy:<4} R:{r: .3f} G:{g: .3f} B:{b: .3f} A:{a: .3f}"
            elif frame_raw.shape[2] >= 3:
                r, g, b = pixel[:3]
                text = f"X:{ix:<4} Y:{iy:<4} R:{r: .3f} G:{g: .3f} B:{b: .3f}"
            else:
                val = pixel[0]
                text = f"X:{ix:<4} Y:{iy:<4} V:{val: .3f}"
            self.lbl_probe.setText(text)
        else:
            self.lbl_probe.setText("")

    # ─────────────────────────────────────────────────────────────────────
    # Annotation / Drawing methods
    # ─────────────────────────────────────────────────────────────────────

    def _wire_annotation_toolbar(self):
        """Connect AnnotationToolbar signals to main window actions."""
        tb = self.annotation_toolbar
        tb.tool_changed.connect(self._on_annotation_tool_changed)
        tb.color_changed.connect(self._on_annotation_color_changed)
        tb.width_changed.connect(self._on_annotation_width_changed)
        tb.undo_requested.connect(self._annotation_undo)
        tb.redo_requested.connect(self._annotation_redo)
        tb.clear_frame_requested.connect(self._clear_annotations)
        tb.clear_all_requested.connect(self._clear_all_annotations)

        self.viewport.stroke_finished.connect(self._on_stroke_finished)
        if hasattr(self, 'viewport_b'):
            self.viewport_b.stroke_finished.connect(self._on_stroke_finished)

    def _toggle_annotate_mode(self, enabled: bool | None = None):
        """Show/hide the annotation toolbar and enable/disable drawing on viewports."""
        if enabled is None or not isinstance(enabled, bool):
            enabled = not getattr(self.viewport, 'is_drawing', False)

        if hasattr(self, 'btn_annotate'):
            self.btn_annotate.setChecked(enabled)
        if hasattr(self, 'annot_view_action'):
            self.annot_view_action.setChecked(enabled)
        if hasattr(self, 'annot_menu_action'):
            self.annot_menu_action.setChecked(enabled)

        self.viewport.is_drawing = enabled
        if hasattr(self, 'viewport_b'):
            self.viewport_b.is_drawing = enabled

        if enabled:
            self.annotation_toolbar.show()
            self.annotation_toolbar.raise_()
            # Push current tool/color/width to viewports
            self._on_annotation_tool_changed(self.annotation_toolbar.current_tool())
            self._on_annotation_color_changed(self.annotation_toolbar.current_color())
            self._on_annotation_width_changed(self.annotation_toolbar.current_width())
            # Refresh annotation display
            self._refresh_annotation_display()
        else:
            self.annotation_toolbar.hide()
            # Clear visual overlays when exiting annotation mode
            self.viewport.set_annotations([])
            if hasattr(self, 'viewport_b'):
                self.viewport_b.set_annotations([])

        # Update undo/redo button states
        self._update_annotation_undo_redo_ui()

    def _on_annotation_tool_changed(self, tool: str):
        if hasattr(self, 'viewport'):
            self.viewport.finish_text_input()
            self.viewport.draw_tool = tool
        if hasattr(self, 'viewport_b'):
            self.viewport_b.finish_text_input()
            self.viewport_b.draw_tool = tool

    def _on_annotation_color_changed(self, color: tuple):
        self.viewport.draw_color = color
        self.viewport_b.draw_color = color

    def _on_annotation_width_changed(self, width: int):
        self.viewport.draw_width = width
        self.viewport_b.draw_width = width

    def _on_stroke_finished(self, stroke: dict):
        """Receive a finished stroke dict from the viewport and record it."""
        tool = stroke.get('tool', 'pen')

        if tool == 'eraser':
            self._erase_stroke_near(stroke)
            return

        idx = self.current_index

        # Push current state to undo stack before modifying
        current = list(self.annotations.get(idx, []))
        self._annotation_undo_stack.setdefault(idx, []).append(current)
        # Clear redo stack on new action
        self._annotation_redo_stack[idx] = []

        if idx not in self.annotations:
            self.annotations[idx] = []
        self.annotations[idx].append(stroke)

        self._update_annotation_undo_redo_ui()
        self._auto_save_sidecar()

    def _erase_stroke_near(self, eraser_stroke: dict):
        """Remove the topmost stroke that is close to the eraser position."""
        idx = self.current_index
        strokes = self.annotations.get(idx, [])
        if not strokes:
            return

        pts = eraser_stroke.get('points', [])
        if not pts:
            return
        ex, ey = pts[0]
        width = eraser_stroke.get('width', 3)
        thresh_sq = (max(width * 4.0, 35.0)) ** 2

        def _point_to_segment_dist_sq(px, py, x0, y0, x1, y1):
            dx, dy = x1 - x0, y1 - y0
            l2 = dx*dx + dy*dy
            if l2 == 0:
                return (px - x0)**2 + (py - y0)**2
            t = max(0.0, min(1.0, ((px - x0)*dx + (py - y0)*dy) / l2))
            return (px - (x0 + t*dx))**2 + (py - (y0 + t*dy))**2

        # Find topmost (last) stroke within threshold
        for i in range(len(strokes) - 1, -1, -1):
            s = strokes[i]
            tool = s.get('tool', 'pen')
            s_pts = s.get('points', [])
            s_pts2 = s.get('points2')
            hit = False

            if tool == 'text':
                if s_pts:
                    tx, ty = s_pts[0]
                    txt_len = len(s.get('text', ''))
                    text_thresh_sq = (max(width * 4.0, 40.0 + txt_len * 12.0)) ** 2
                    if (ex - tx)**2 + (ey - ty)**2 <= text_thresh_sq:
                        hit = True
            else:
                for pts_list in (s_pts, s_pts2):
                    if not pts_list or len(pts_list) < 2:
                        continue
                    for k in range(len(pts_list) - 1):
                        x0, y0 = pts_list[k][:2]
                        x1, y1 = pts_list[k+1][:2]
                        if _point_to_segment_dist_sq(ex, ey, x0, y0, x1, y1) <= thresh_sq:
                            hit = True
                            break
                    if hit:
                        break

            if hit:
                # Save undo snapshot
                current = list(strokes)
                self._annotation_undo_stack.setdefault(idx, []).append(current)
                self._annotation_redo_stack[idx] = []
                # Remove stroke
                self.annotations[idx].pop(i)
                self._refresh_annotation_display()
                self._update_annotation_undo_redo_ui()
                self._auto_save_sidecar()
                return

    def _annotation_undo(self):
        """Undo the last annotation action on the current frame."""
        idx = self.current_index
        stack = self._annotation_undo_stack.get(idx, [])
        if not stack:
            return
        # Save current state to redo
        self._annotation_redo_stack.setdefault(idx, []).append(
            list(self.annotations.get(idx, []))
        )
        # Restore
        prev = stack.pop()
        self.annotations[idx] = prev
        self._refresh_annotation_display()
        self._update_annotation_undo_redo_ui()
        self._auto_save_sidecar()

    def _annotation_redo(self):
        """Redo the last undone annotation action on the current frame."""
        idx = self.current_index
        stack = self._annotation_redo_stack.get(idx, [])
        if not stack:
            return
        # Save current state to undo
        self._annotation_undo_stack.setdefault(idx, []).append(
            list(self.annotations.get(idx, []))
        )
        nxt = stack.pop()
        self.annotations[idx] = nxt
        self._refresh_annotation_display()
        self._update_annotation_undo_redo_ui()
        self._auto_save_sidecar()

    def _update_annotation_undo_redo_ui(self):
        """Sync undo/redo button enabled state in the toolbar."""
        if not hasattr(self, 'annotation_toolbar'):
            return
        idx = self.current_index
        has_undo = bool(self._annotation_undo_stack.get(idx))
        has_redo = bool(self._annotation_redo_stack.get(idx))
        self.annotation_toolbar.set_undo_enabled(has_undo)
        self.annotation_toolbar.set_redo_enabled(has_redo)
        self._update_timeline_annotation_markers()

    def _update_timeline_annotation_markers(self):
        self._update_timeline_markers()

    def _update_timeline_markers(self):
        """Authoritative updater for all markers on the timeline playhead slider."""
        if hasattr(self, 'frame_slider'):
            active_indices = {k for k, v in self.annotations.items() if v}
            self.frame_slider.set_annotated_indices(active_indices)
            self.frame_slider.set_bookmarks(self.bookmarks)
            cnt = self.core.frame_count()
            r_in = getattr(self, 'range_in', 0)
            r_out = getattr(self, 'range_out', max(0, cnt - 1))
            self.frame_slider.set_in_out(r_in, r_out)
            if self.core.media and getattr(self.core.media, 'missing_frames', None):
                self.frame_slider.set_missing_indices(set(self.core.media.missing_frames))

    def _set_in_point(self):
        """Set In point at current playhead position."""
        self.range_in = self.current_index
        cnt = self.core.frame_count()
        if getattr(self, 'range_out', 0) < self.range_in:
            self.range_out = max(self.range_in, max(0, cnt - 1))
        if hasattr(self, 'range_start_edit'):
            self.range_start_edit.setText(str(self.range_in))
        if hasattr(self, 'range_end_edit'):
            self.range_end_edit.setText(str(self.range_out))
        self._update_timeline_markers()
        self._update_status(f"In point set to frame {self.range_in}")
        self._auto_save_sidecar()

    def _set_out_point(self):
        """Set Out point at current playhead position."""
        self.range_out = self.current_index
        if getattr(self, 'range_in', 0) > self.range_out:
            self.range_in = min(self.range_out, 0)
        if hasattr(self, 'range_start_edit'):
            self.range_start_edit.setText(str(self.range_in))
        if hasattr(self, 'range_end_edit'):
            self.range_end_edit.setText(str(self.range_out))
        self._update_timeline_markers()
        self._update_status(f"Out point set to frame {self.range_out}")
        self._auto_save_sidecar()

    def _clear_in_out_range(self):
        """Reset In and Out points to encompass the entire media clip."""
        cnt = self.core.frame_count()
        self.range_in = 0
        self.range_out = max(0, cnt - 1)
        if hasattr(self, 'range_start_edit'):
            self.range_start_edit.setText(str(self.range_in))
        if hasattr(self, 'range_end_edit'):
            self.range_end_edit.setText(str(self.range_out))
        self._update_timeline_markers()
        self._update_status("In/Out playback range reset to full clip")
        self._auto_save_sidecar()

    def _toggle_bookmark(self):
        """Toggle a bookmark marker at the current playhead frame."""
        idx = self.current_index
        if idx in self.bookmarks:
            self.bookmarks.remove(idx)
            self._update_status(f"Bookmark removed from frame {idx}")
        else:
            self.bookmarks.add(idx)
            self._update_status(f"Bookmark added at frame {idx}")
        self._update_timeline_markers()
        self._auto_save_sidecar()

    def _clear_all_bookmarks(self):
        """Clear all bookmarks across all frames."""
        self.bookmarks.clear()
        self._update_timeline_markers()
        self._update_status("All bookmarks cleared")
        self._auto_save_sidecar()

    def _auto_save_sidecar(self):
        """Automatically write review sidecar (.review.json) in background if media is loaded."""
        if not self.core.media or not self.core.media.path:
            return
        try:
            AnnotationService.save_sidecar(
                self.core.media.path,
                self.annotations,
                bookmarks=self.bookmarks,
                in_point=getattr(self, 'range_in', None),
                out_point=getattr(self, 'range_out', None),
            )
        except Exception:
            pass

    def _save_review_sidecar(self):
        """Explicitly save review sidecar file."""
        if not self.core.media or not self.core.media.path:
            QtWidgets.QMessageBox.warning(self, "No Media", "Please load media first.")
            return
        try:
            saved_p = AnnotationService.save_sidecar(
                self.core.media.path,
                self.annotations,
                bookmarks=self.bookmarks,
                in_point=getattr(self, 'range_in', None),
                out_point=getattr(self, 'range_out', None),
            )
            self._update_status(f"Review sidecar saved: {os.path.basename(saved_p)}")
            QtWidgets.QMessageBox.information(
                self, "Sidecar Saved",
                f"Review sidecar saved successfully:\n{saved_p}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save Error", str(e))

    def _load_review_sidecar(self):
        """Prompt to load a review sidecar (.review.json)."""
        if not self.core.media:
            QtWidgets.QMessageBox.warning(self, "No Media", "Please load media first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Review Sidecar", "", "Review Files (*.review.json *.json);;All Files (*)"
        )
        if not path:
            return
        try:
            data = AnnotationService.load_sidecar(self.core.media.path, source_path=path)
            if data:
                self.annotations = data.get("annotations", {})
                self.bookmarks = set(data.get("bookmarks", []))
                cnt = self.core.frame_count()
                if data.get("in_point") is not None:
                    self.range_in = max(0, min(cnt - 1, data["in_point"]))
                if data.get("out_point") is not None:
                    self.range_out = max(self.range_in, min(cnt - 1, data["out_point"]))
                if hasattr(self, 'range_start_edit'):
                    self.range_start_edit.setText(str(self.range_in))
                if hasattr(self, 'range_end_edit'):
                    self.range_end_edit.setText(str(self.range_out))
                self._annotation_undo_stack.clear()
                self._annotation_redo_stack.clear()
                self._refresh_annotation_display()
                self._update_timeline_markers()
                self._update_annotation_undo_redo_ui()
                self._update_status(f"Review sidecar loaded: {os.path.basename(path)}")
            else:
                QtWidgets.QMessageBox.warning(self, "Load Error", "Could not parse review sidecar data.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))

    def _update_version_ui(self):
        """Update window title and status bar with detected shot version information."""
        if not self.version_group or not self.version_group.versions:
            return
        cur_v = self.version_group.current_version
        total_v = len(self.version_group.versions)
        shot = self.version_group.shot_name
        self.setWindowTitle(f"VFX Player — {shot} (v{cur_v:03d} | {cur_v}/{total_v})")
        if hasattr(self, '_status_base'):
            self._status_base = f"Loaded: {self.version_group.current_path} [v{cur_v:03d} of {total_v}]"
            self._update_status(self._status_base)

    def _sync_versions_and_tasks(self, path: Optional[str] = None):
        """
        Synchronize both local disk version groups and Kitsu tasks & versions.
        Updates the HUD Task/Version selector and the Versions menu.
        """
        if getattr(self, '_syncing_task_ui', False):
            return
        self._syncing_task_ui = True
        try:
            target_path = path or (self.core.media.path if self.core.media else "")
            target_item = getattr(self, '_current_kitsu_shot', None)
            shot_name = (target_item.shot_name if target_item else None) or (os.path.basename(self.core.media.path) if self.core.media and self.core.media.path else "")

            # 1. Local disk version detection
            if target_path and os.path.exists(target_path):
                try:
                    self.version_group = VersionDetector.find_versions(target_path)
                    self._update_version_ui()
                except Exception:
                    self.version_group = None
            else:
                self.version_group = None

            # 2. Kitsu tasks & versions query
            self._current_kitsu_versions = []
            self._current_kitsu_tasks = []

            shot_id = getattr(target_item, 'kitsu_shot_id', None) if target_item else None
            if not shot_id and shot_name and kitsu_client.is_authenticated():
                try:
                    s_data = kitsu_client.get_shot_by_name(shot_name)
                    if s_data and s_data.get("id"):
                        shot_id = s_data["id"]
                        if target_item:
                            target_item.kitsu_shot_id = shot_id
                except Exception:
                    pass

            if shot_id and kitsu_client.is_authenticated():
                try:
                    k_vers = kitsu_client.get_shot_versions_and_tasks(shot_id)
                    if k_vers:
                        self._current_kitsu_versions = k_vers
                        seen = set()
                        for v in k_vers:
                            t = v.get("task_name", "")
                            if t and t not in seen:
                                seen.add(t)
                                self._current_kitsu_tasks.append(t)
                except Exception as e:
                    print(f"[Kitsu] Failed to query shot versions: {e}")

            # 3. Update HUD controls
            if hasattr(self, 'combo_task') and hasattr(self, 'combo_version'):
                self.combo_task.blockSignals(True)
                self.combo_version.blockSignals(True)
                self.combo_task.clear()
                self.combo_version.clear()

                if self._current_kitsu_tasks:
                    for t in self._current_kitsu_tasks:
                        self.combo_task.addItem(t)

                    cur_task = getattr(target_item, 'task_name', None) or getattr(target_item, 'task', None)
                    if not cur_task or cur_task not in self._current_kitsu_tasks:
                        cur_task = self._current_kitsu_tasks[0]
                    self._active_kitsu_task = cur_task

                    idx = self.combo_task.findText(cur_task)
                    if idx >= 0:
                        self.combo_task.setCurrentIndex(idx)

                    self._populate_version_combo_for_task(cur_task)
                    self.task_version_pill.show()
                elif self.version_group and self.version_group.versions:
                    self.combo_task.addItem("Local")
                    self._active_kitsu_task = "Local"
                    for vi in self.version_group.versions:
                        lbl = f"{vi.version_string}" + (" (Latest)" if vi.version_number == self.version_group.latest_version.version_number else "")
                        self.combo_version.addItem(lbl, vi.file_path)
                    cur_idx = max(0, self.version_group.current_version - 1)
                    if cur_idx < self.combo_version.count():
                        self.combo_version.setCurrentIndex(cur_idx)
                    self.task_version_pill.show()
                else:
                    self.combo_task.addItem("No Tasks")
                    self.combo_version.addItem("v001")
                    self.task_version_pill.show()

                self.combo_task.blockSignals(False)
                self.combo_version.blockSignals(False)

            # 4. Update MenuBar dynamic submenu
            self._update_task_version_menu()

        finally:
            self._syncing_task_ui = False

    def _populate_version_combo_for_task(self, task_name: str):
        """Fill combo_version with versions belonging to task_name and select the current one."""
        if not hasattr(self, 'combo_version'):
            return
        self.combo_version.blockSignals(True)
        self.combo_version.clear()

        task_vers = [v for v in self._current_kitsu_versions if v.get("task_name") == task_name]
        cur_p_id = getattr(getattr(self, '_current_kitsu_shot', None), 'kitsu_preview_id', None)

        selected_idx = -1
        for idx, v in enumerate(task_vers):
            self.combo_version.addItem(v.get("version_label", f"v{v.get('version_num', 1):03d}"), v)
            if cur_p_id and v.get("preview_file_id") == cur_p_id:
                selected_idx = idx

        if selected_idx == -1 and task_vers:
            selected_idx = len(task_vers) - 1

        if 0 <= selected_idx < self.combo_version.count():
            self.combo_version.setCurrentIndex(selected_idx)
            v_data = self.combo_version.itemData(selected_idx)
            if isinstance(v_data, dict):
                self._active_kitsu_version_num = v_data.get("version_num")

        self.combo_version.blockSignals(False)

    def _on_task_combo_changed(self, task_name: str):
        """User changed task dropdown in HUD."""
        if getattr(self, '_syncing_task_ui', False) or not task_name or task_name in ("No Tasks", "Local"):
            return
        self._active_kitsu_task = task_name
        self._populate_version_combo_for_task(task_name)
        v_data = self.combo_version.currentData()
        if v_data and isinstance(v_data, dict) and v_data.get("preview_file_id"):
            self._load_kitsu_version(v_data)

    def _on_version_combo_changed(self, idx: int):
        """User changed version dropdown in HUD."""
        if getattr(self, '_syncing_task_ui', False) or idx < 0:
            return
        v_data = self.combo_version.itemData(idx)
        if isinstance(v_data, str) and os.path.exists(v_data):
            self.load_media(v_data)
        elif isinstance(v_data, dict) and v_data.get("preview_file_id"):
            self._load_kitsu_version(v_data)

    def _update_task_version_menu(self):
        """Update the 'Switch Task / Version' dynamic menu."""
        if not hasattr(self, 'switch_task_ver_menu'):
            return
        self.switch_task_ver_menu.clear()

        if self._current_kitsu_tasks and self._current_kitsu_versions:
            for t_name in self._current_kitsu_tasks:
                sub_menu = self.switch_task_ver_menu.addMenu(f"Task: {t_name}")
                t_vers = [v for v in self._current_kitsu_versions if v.get("task_name") == t_name]
                for v in t_vers:
                    v_label = v.get("version_label", f"v{v.get('version_num', 1):03d}")
                    is_cur = (t_name == self._active_kitsu_task and v.get("version_num") == self._active_kitsu_version_num)
                    act_text = f"✓ {v_label}" if is_cur else v_label
                    act = sub_menu.addAction(act_text)
                    if v.get("preview_file_id"):
                        act.triggered.connect(lambda checked=False, vd=v: self._load_kitsu_version(vd))
                    else:
                        act.setEnabled(False)
        elif self.version_group and self.version_group.versions:
            for vi in self.version_group.versions:
                is_cur = (vi.version_number == self.version_group.current_version)
                act_text = f"✓ {vi.version_string}" if is_cur else vi.version_string
                act = self.switch_task_ver_menu.addAction(act_text)
                act.triggered.connect(lambda checked=False, fp=vi.file_path: self.load_media(fp))
        else:
            act = self.switch_task_ver_menu.addAction("No additional versions available")
            act.setEnabled(False)

    def _load_kitsu_version(self, v_data: Dict[str, Any], into_track_b: bool = False, compare_mode: Optional[str] = None):
        """Download (or use cached) Kitsu preview media and load into Track A or Track B."""
        if not v_data:
            return
        p_id = v_data.get("preview_file_id")
        m_path = v_data.get("media_path")
        label = v_data.get("version_label", "Selected Version")

        load_path = None
        if p_id:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage(f"Downloading {label} from Kitsu...", 5000)
            try:
                load_path = kitsu_client.download_preview_file(preview_file_id=p_id)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
        elif m_path and os.path.exists(m_path):
            load_path = m_path

        if not load_path or not os.path.exists(load_path):
            QtWidgets.QMessageBox.warning(self, "Load Error", f"Could not load media file for {label}.")
            return

        if into_track_b:
            self.core_b.load(load_path)
            self.compare_loaded = True
            mode = compare_mode or "wipe"
            self._set_compare_mode(mode)
            self._update_status(f"Comparing with {label} ({mode.upper()} mode)")
        else:
            self._active_kitsu_task = v_data.get("task_name")
            self._active_kitsu_version_num = v_data.get("version_num")
            orig_shot = getattr(self, '_current_kitsu_shot', None)
            if orig_shot:
                orig_shot.kitsu_preview_id = p_id
                orig_shot.task_name = v_data.get("task_name", "")
                orig_shot.version = f"v{v_data.get('version_num', 1):03d}"
                orig_shot.preview_cache_path = load_path
                # Only update media_path if shot didn't have one or was a remote URL
                if not orig_shot.media_path or orig_shot.media_path.startswith("http") or "vfxplayer_kitsu_cache" in orig_shot.media_path:
                    orig_shot.media_path = load_path

            self._switching_kitsu_version = True
            self._loading_from_playlist = True
            try:
                self.load_media(load_path)
            finally:
                self._switching_kitsu_version = False
                self._loading_from_playlist = False

            if orig_shot:
                self._current_kitsu_shot = orig_shot

            if hasattr(self, 'playlist_widget'):
                self.playlist_widget.refresh()
                if hasattr(self, 'playlist_service'):
                    self.playlist_widget.set_current_index(self.playlist_service.current_index)

            shot_label = getattr(orig_shot, 'shot_name', None) or getattr(orig_shot, 'name', None)
            if shot_label:
                t_name = v_data.get("task_name", "")
                v_lbl = v_data.get("version_label", f"v{v_data.get('version_num', 1):03d}")
                self.setWindowTitle(f"VFX Player — {shot_label} [{t_name} {v_lbl}]")

            self._update_status(f"Loaded {label}")

    def _task_next(self):
        """Switch to next task in pipeline (e.g. Edit -> Lighting -> Compositing)."""
        if not self._current_kitsu_tasks or len(self._current_kitsu_tasks) <= 1:
            self._update_status("No other tasks available for this shot")
            return
        cur_task = self._active_kitsu_task or self._current_kitsu_tasks[0]
        try:
            cur_idx = self._current_kitsu_tasks.index(cur_task)
            nxt_idx = (cur_idx + 1) % len(self._current_kitsu_tasks)
        except ValueError:
            nxt_idx = 0
        nxt_task = self._current_kitsu_tasks[nxt_idx]
        self.combo_task.setCurrentText(nxt_task)
        self._update_status(f"Switched task to: {nxt_task}")

    def _task_prev(self):
        """Switch to previous task in pipeline (e.g. Compositing -> Lighting -> Edit)."""
        if not self._current_kitsu_tasks or len(self._current_kitsu_tasks) <= 1:
            self._update_status("No other tasks available for this shot")
            return
        cur_task = self._active_kitsu_task or self._current_kitsu_tasks[0]
        try:
            cur_idx = self._current_kitsu_tasks.index(cur_task)
            prv_idx = (cur_idx - 1) % len(self._current_kitsu_tasks)
        except ValueError:
            prv_idx = 0
        prv_task = self._current_kitsu_tasks[prv_idx]
        self.combo_task.setCurrentText(prv_task)
        self._update_status(f"Switched task to: {prv_task}")

    def _version_up(self):
        """Switch to next detected version (supports both local disk and Kitsu tasks)."""
        if self.version_group:
            nxt = self.version_group.get_next_version()
            if nxt:
                self.load_media(nxt.file_path)
                self._update_status(f"Switched to version: {nxt.version_string}")
            else:
                self._update_status("Already at latest version")
            return

        if self._current_kitsu_versions:
            task_name = self._active_kitsu_task or (self._current_kitsu_tasks[0] if self._current_kitsu_tasks else "")
            task_vers = [v for v in self._current_kitsu_versions if (not task_name or v.get("task_name") == task_name) and v.get("preview_file_id")]
            cur_v_num = self._active_kitsu_version_num or 1
            nxt_vers = [v for v in task_vers if v.get("version_num", 0) > cur_v_num]
            if nxt_vers:
                nxt_v = min(nxt_vers, key=lambda v: v.get("version_num", 9999))
                self._load_kitsu_version(nxt_v)
                self._update_status(f"Switched to version: {nxt_v.get('version_label')}")
            else:
                self._update_status(f"Already at latest version for {task_name or 'current task'}")
            return

        self._update_status("No version group detected")

    def _version_down(self):
        """Switch to previous detected version (supports both local disk and Kitsu tasks)."""
        if self.version_group:
            prv = self.version_group.get_prev_version()
            if prv:
                self.load_media(prv.file_path)
                self._update_status(f"Switched to version: {prv.version_string}")
            else:
                self._update_status("Already at earliest version")
            return

        if self._current_kitsu_versions:
            task_name = self._active_kitsu_task or (self._current_kitsu_tasks[0] if self._current_kitsu_tasks else "")
            task_vers = [v for v in self._current_kitsu_versions if (not task_name or v.get("task_name") == task_name) and v.get("preview_file_id")]
            cur_v_num = self._active_kitsu_version_num or (len(task_vers) if task_vers else 1)
            prv_vers = [v for v in task_vers if v.get("version_num", 0) < cur_v_num]
            if prv_vers:
                prv_v = max(prv_vers, key=lambda v: v.get("version_num", 0))
                self._load_kitsu_version(prv_v)
                self._update_status(f"Switched to version: {prv_v.get('version_label')}")
            else:
                self._update_status(f"Already at earliest version for {task_name or 'current task'}")
            return

        self._update_status("No version group detected")

    def _version_latest(self):
        """Switch directly to latest version (supports both local disk and Kitsu tasks)."""
        if self.version_group:
            latest = self.version_group.latest_version
            if latest and latest.file_path != self.version_group.current_path:
                self.load_media(latest.file_path)
                self._update_status(f"Switched to latest version: {latest.version_string}")
            else:
                self._update_status("Already at latest version")
            return

        if self._current_kitsu_versions:
            task_name = self._active_kitsu_task or (self._current_kitsu_tasks[0] if self._current_kitsu_tasks else "")
            task_vers = [v for v in self._current_kitsu_versions if (not task_name or v.get("task_name") == task_name) and v.get("preview_file_id")]
            if task_vers:
                latest_v = max(task_vers, key=lambda v: v.get("version_num", 0))
                if latest_v.get("version_num") != self._active_kitsu_version_num:
                    self._load_kitsu_version(latest_v)
                    self._update_status(f"Switched to latest version: {latest_v.get('version_label')}")
                else:
                    self._update_status("Already at latest version")
            return

        self._update_status("No version group detected")

    def _version_compare_prev(self, item=None):
        """
        Load previous version into Secondary Track (B) and activate Wipe comparison.
        Seamlessly supports both local disk versions and Kitsu tasks & versions.
        """
        target_path = None
        ver_label = "previous version"

        # 1. Check local file version detection first
        if item and getattr(item, 'media_path', None):
            vg = VersionDetector.find_versions(item.media_path)
            if vg:
                prv = vg.get_prev_version()
                if prv:
                    target_path = prv.file_path
                    ver_label = prv.version_string
        elif self.version_group:
            prv = self.version_group.get_prev_version()
            if prv:
                target_path = prv.file_path
                ver_label = prv.version_string

        # 2. If not found locally, query Kitsu versions for this shot
        if not target_path:
            k_item = item or getattr(self, '_current_kitsu_shot', None)
            shot_name = getattr(k_item, 'shot_name', None) or getattr(k_item, 'shot', None) or (os.path.basename(self.core.media.path) if self.core.media and self.core.media.path else "Current Shot")

            kitsu_vers = list(self._current_kitsu_versions)
            if not kitsu_vers and kitsu_client.is_authenticated():
                shot_id = getattr(k_item, 'kitsu_shot_id', None)
                if not shot_id and shot_name:
                    try:
                        s_data = kitsu_client.get_shot_by_name(shot_name)
                        if s_data:
                            shot_id = s_data.get("id")
                    except Exception:
                        pass
                if shot_id:
                    try:
                        kitsu_vers = kitsu_client.get_shot_versions_and_tasks(shot_id)
                        self._current_kitsu_versions = kitsu_vers
                    except Exception as e:
                        print(f"[Kitsu] Version compare query warning: {e}")

            if kitsu_vers:
                valid_vers = [v for v in kitsu_vers if v.get("preview_file_id")]
                if valid_vers:
                    cur_p_id = getattr(k_item, 'kitsu_preview_id', None)
                    active_task = self._active_kitsu_task or (k_item.task_name if k_item else "") or (valid_vers[0].get("task_name") if valid_vers else "")
                    cur_v_num = self._active_kitsu_version_num

                    target_v = None

                    # A. Try to find earlier version in the same task
                    task_vers = [v for v in valid_vers if v.get("task_name") == active_task]
                    if task_vers:
                        if cur_v_num and cur_v_num > 1:
                            earlier = [v for v in task_vers if v.get("version_num", 0) < cur_v_num]
                            if earlier:
                                target_v = max(earlier, key=lambda v: v.get("version_num", 0))
                        elif len(task_vers) >= 2:
                            target_v = task_vers[-2]

                    # B. If current task has only 1 version, compare with another task (e.g. Lighting, Edit, Plate)
                    if not target_v:
                        other_tasks = [v for v in valid_vers if v.get("task_name") != active_task and v.get("preview_file_id") != cur_p_id]
                        if other_tasks:
                            target_v = other_tasks[-1]

                    # C. Fallback: pick any different preview among available
                    if not target_v and len(valid_vers) >= 2:
                        candidates = [v for v in valid_vers if v.get("preview_file_id") != cur_p_id]
                        if candidates:
                            target_v = candidates[-1]

                    if target_v and target_v.get("preview_file_id"):
                        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
                        self.statusBar().showMessage(f"Downloading {target_v.get('version_label')} for comparison...", 5000)
                        try:
                            target_path = kitsu_client.download_preview_file(preview_file_id=target_v["preview_file_id"])
                            ver_label = target_v.get("version_label", "Kitsu preview")
                        finally:
                            QtWidgets.QApplication.restoreOverrideCursor()

        if not target_path or not os.path.exists(target_path):
            QtWidgets.QMessageBox.information(
                self, "Versions",
                "No previous version or comparison render was found for this shot.\n\n"
                "Tip: Press Ctrl+Alt+V to inspect all task renders and versions available in Kitsu."
            )
            return

        try:
            self.core_b.load(target_path)
            self.compare_loaded = True
            self._set_compare_mode('wipe')
            self._update_status(f"Comparing current version with {ver_label} (WIPE mode)")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Compare Error", f"Could not load previous version: {e}")

    def _show_version_compare_dialog(self, item=None):
        """Display all versions across tasks (Edit, Comp, Lighting, Anim, etc.) for a shot."""
        target_item = item or getattr(self, '_current_kitsu_shot', None)
        shot_name = (target_item.shot_name if target_item else None) or (os.path.basename(self.core.media.path) if self.core.media and self.core.media.path else "Current Shot")
        versions: List[Dict[str, Any]] = []

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            # 1. Query Kitsu versions & tasks if authenticated
            shot_id = getattr(target_item, 'kitsu_shot_id', None) if target_item else None
            if not shot_id and kitsu_client.is_authenticated():
                try:
                    s_data = kitsu_client.get_shot_by_name(shot_name)
                    if s_data:
                        shot_id = s_data.get("id")
                except Exception:
                    pass

            if shot_id and kitsu_client.is_authenticated():
                kitsu_vers = kitsu_client.get_shot_versions_and_tasks(shot_id)
                if kitsu_vers:
                    versions.extend(kitsu_vers)

            # 2. Query local disk versions via VersionDetector
            media_p = getattr(target_item, 'media_path', None) or (self.core.media.path if self.core.media else None)
            if media_p and os.path.exists(media_p):
                vg = VersionDetector.find_versions(media_p)
                if vg and vg.versions:
                    for vi in vg.versions:
                        if not any(v.get("media_path") == vi.file_path for v in versions):
                            versions.append({
                                "task_name": getattr(target_item, 'task_name', 'Local') or 'Local',
                                "version_num": vi.version_number,
                                "version_label": f"{vi.version_string} (Local)",
                                "media_path": vi.file_path,
                                "author": "Local Disk",
                                "created_at": "",
                                "comment": os.path.basename(vi.file_path),
                                "status": "Local",
                            })
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        if not versions:
            QtWidgets.QMessageBox.information(
                self, "No Versions Found",
                f"No additional versions or task renders were found for '{shot_name}'."
            )
            return

        dlg = VersionCompareDialog(shot_name=shot_name, versions=versions, parent=self)
        if dlg.exec() and dlg.selected_action:
            v_data, mode = dlg.selected_action
            load_path = None
            if v_data.get("preview_file_id"):
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
                self.statusBar().showMessage(f"Downloading {v_data.get('version_label')}...", 4000)
                try:
                    load_path = kitsu_client.download_preview_file(preview_file_id=v_data["preview_file_id"])
                finally:
                    QtWidgets.QApplication.restoreOverrideCursor()
            elif v_data.get("media_path"):
                load_path = v_data["media_path"]

            if not load_path or not os.path.exists(load_path):
                QtWidgets.QMessageBox.warning(self, "Load Error", "Could not load selected version media file.")
                return

            label = v_data.get("version_label", "Selected version")
            if mode == "play":
                self.load_media(load_path)
                self.statusBar().showMessage(f"Loaded {label} into Main Player", 3000)
            elif mode in ("wipe", "side-by-side", "split"):
                self.core_b.load(load_path)
                self.compare_loaded = True
                self._set_compare_mode(mode)
                self.statusBar().showMessage(f"Comparing with {label} ({mode.upper()} mode)", 4000)

    def _toggle_scopes(self):
        """Show or hide the real-time image scopes dialog."""
        if self.scopes_dialog is None:
            self.scopes_dialog = ScopesDialog(self)
        if self.scopes_dialog.isVisible():
            self.scopes_dialog.hide()
        else:
            self.scopes_dialog.show()
            self.scopes_dialog.raise_()
            self.scopes_dialog.activateWindow()
            frame = self.core.get_frame(self.current_index)
            if frame is not None:
                self.scopes_dialog.update_image(frame)

    def _toggle_properties_hud(self):
        """Toggle file properties HUD visibility."""
        self.properties_visible = not self.properties_visible
        if self.properties_visible:
            if self.core.media:
                self.props_hud.update_info(self.core.media)
            self.props_hud.show()
            self.props_hud.raise_()
        else:
            self.props_hud.hide()

    def _refresh_annotation_display(self):
        """Redraw current frame annotations in the viewports."""
        strokes = self.annotations.get(self.current_index, [])
        self.viewport.set_annotations(strokes)
        if self.side_by_side and hasattr(self, 'viewport_b'):
            self.viewport_b.set_annotations(strokes)

    def _clear_annotations(self):
        """Clear annotations for the current frame (used by toolbar Clear Frame)."""
        idx = self.current_index
        if idx in self.annotations:
            # Save to undo before clearing
            self._annotation_undo_stack.setdefault(idx, []).append(
                list(self.annotations[idx])
            )
            self._annotation_redo_stack[idx] = []
            del self.annotations[idx]
            self.viewport.set_annotations([])
            if self.side_by_side and hasattr(self, 'viewport_b'):
                self.viewport_b.set_annotations([])
            self._update_annotation_undo_redo_ui()
            self._auto_save_sidecar()

    def _clear_all_annotations(self):
        """Clear annotations on ALL frames."""
        self.annotations.clear()
        self._annotation_undo_stack.clear()
        self._annotation_redo_stack.clear()
        self.viewport.set_annotations([])
        if hasattr(self, 'viewport_b'):
            self.viewport_b.set_annotations([])
        self._update_annotation_undo_redo_ui()
        self._auto_save_sidecar()

    # ─────────────────────────────────────────────────────────────────────
    # File menu: Save Frame / Annotations
    # ─────────────────────────────────────────────────────────────────────

    def _save_current_frame(self):
        """Save the current frame as PNG/JPG/EXR (without annotations)."""
        if not self.core.frame_count():
            QtWidgets.QMessageBox.warning(self, "No Media", "No media loaded.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Frame", "",
            "PNG Image (*.png);;JPEG Image (*.jpg);;OpenEXR (*.exr);;All Files (*)"
        )
        if not path:
            return
        self._do_save_frame(path, with_annotations=False)

    def _save_frame_with_annotations(self):
        """Save the current frame with annotations baked in."""
        if not self.core.frame_count():
            QtWidgets.QMessageBox.warning(self, "No Media", "No media loaded.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Frame with Annotations", "",
            "PNG Image (*.png);;JPEG Image (*.jpg);;All Files (*)"
        )
        if not path:
            return
        self._do_save_frame(path, with_annotations=True)

    def _export_all_annotated_frames(self):
        """Export all frames that contain annotations to a chosen directory as PNG images."""
        if not self.core.frame_count():
            QtWidgets.QMessageBox.warning(self, "No Media", "No media loaded.")
            return

        annotated_indices = sorted([idx for idx, strokes in self.annotations.items() if strokes])
        if not annotated_indices:
            QtWidgets.QMessageBox.information(
                self, "No Annotated Frames",
                "There are no annotated frames in the current clip to export.\n"
                "Draw annotations on frames before exporting."
            )
            return

        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, f"Select Folder to Export {len(annotated_indices)} Annotated Frame(s)"
        )
        if not folder:
            return

        base_name = "frame"
        if self.core.media and self.core.media.path:
            base_name = os.path.splitext(os.path.basename(self.core.media.path))[0]

        progress = QtWidgets.QProgressDialog(
            f"Exporting {len(annotated_indices)} annotated frame(s)...", "Cancel", 0, len(annotated_indices), self
        )
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        orig_idx = self.current_index
        was_playing = self.playing
        if was_playing:
            self.pause()

        saved_files = []
        try:
            for i, frame_idx in enumerate(annotated_indices):
                if progress.wasCanceled():
                    break
                progress.setValue(i)
                progress.setLabelText(f"Exporting annotated frame {frame_idx + 1} of {self.core.frame_count()} ({i + 1}/{len(annotated_indices)})...")
                QtWidgets.QApplication.processEvents()

                self.seek(frame_idx)
                QtWidgets.QApplication.processEvents()

                arr = self.viewport.get_frame_with_annotations()
                if arr is not None:
                    h, w = arr.shape[:2]
                    c = arr.shape[2] if len(arr.shape) > 2 else 3
                    fmt = QtGui.QImage.Format.Format_RGB888 if c == 3 else QtGui.QImage.Format.Format_RGBA8888
                    image = QtGui.QImage(arr.tobytes(), w, h, w * c, fmt)
                    filename = f"{base_name}_frame_{frame_idx + 1:04d}_annotated.png"
                    out_path = os.path.join(folder, filename)
                    if image.save(out_path):
                        saved_files.append(out_path)
            
            progress.setValue(len(annotated_indices))
        finally:
            self.seek(orig_idx)
            if was_playing:
                self.play()

        if saved_files:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle("Export Complete")
            msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            msg_box.setText(f"Successfully exported {len(saved_files)} annotated frame(s) to:\n{folder}")
            open_btn = msg_box.addButton("Open Folder", QtWidgets.QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton(QtWidgets.QMessageBox.StandardButton.Ok)
            msg_box.exec()
            if msg_box.clickedButton() == open_btn:
                try:
                    os.startfile(folder)
                except Exception as e:
                    print(f"Could not open directory: {e}")

    def _do_save_frame(self, path: str, with_annotations: bool = False):
        """Internal: save current frame to disk, optionally with annotations baked."""
        import traceback
        try:
            ext = os.path.splitext(path)[1].lower()

            if with_annotations:
                # Use VisPy canvas.render() to capture the GPU scene
                arr = self.viewport.get_frame_with_annotations()
                if arr is None:
                    QtWidgets.QMessageBox.critical(self, "Save Failed", "Could not capture viewport.")
                    return
                # arr is uint8 RGB/RGBA numpy array
                h, w = arr.shape[:2]
                c = arr.shape[2] if len(arr.shape) > 2 else 3
                fmt = QtGui.QImage.Format.Format_RGB888 if c == 3 else QtGui.QImage.Format.Format_RGBA8888
                image = QtGui.QImage(arr.tobytes(), w, h, w * c, fmt)
                if not image.save(path):
                    QtWidgets.QMessageBox.critical(self, "Save Failed", f"Could not save: {path}")
                    return
            else:
                frame_raw = self.core.get_frame(self.current_index)
                if frame_raw is None:
                    QtWidgets.QMessageBox.critical(self, "Save Failed", "Frame not available.")
                    return

                if ext == '.exr':
                    try:
                        import imageio
                        imageio.imwrite(path, frame_raw)
                    except Exception as e:
                        QtWidgets.QMessageBox.critical(self, "Save Failed", f"EXR save error: {e}")
                        return
                else:
                    # Convert float32 to uint8 if needed
                    if frame_raw.dtype == np.float32:
                        arr = np.clip(frame_raw * 255, 0, 255).astype(np.uint8)
                    else:
                        arr = frame_raw.astype(np.uint8)

                    if arr.shape[2] == 3:
                        h, w = arr.shape[:2]
                        image = QtGui.QImage(arr.data, w, h, w * 3, QtGui.QImage.Format.Format_RGB888)
                    else:
                        h, w = arr.shape[:2]
                        image = QtGui.QImage(arr.data, w, h, w * 4, QtGui.QImage.Format.Format_RGBA8888)

                    if not image.save(path):
                        QtWidgets.QMessageBox.critical(self, "Save Failed", f"Could not save: {path}")
                        return

            self._update_status(f"Saved: {os.path.basename(path)}")
        except Exception:
            QtWidgets.QMessageBox.critical(self, "Save Error", traceback.format_exc())

    def _save_annotations_to_file(self):
        """Serialise self.annotations to a JSON file."""
        if not self.annotations:
            QtWidgets.QMessageBox.information(self, "No Annotations", "There are no annotations to save.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Annotations", "", "Annotation Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            # Convert int keys to strings for JSON
            data = {str(k): v for k, v in self.annotations.items()}
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            self._update_status(f"Annotations saved: {os.path.basename(path)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save Error", str(e))

    def _load_annotations_from_file(self):
        """Load annotations from a JSON file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Annotations", "", "Annotation Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Restore int keys
            self.annotations = {int(k): v for k, v in data.items()}
            self._annotation_undo_stack.clear()
            self._annotation_redo_stack.clear()
            self._refresh_annotation_display()
            self._update_annotation_undo_redo_ui()
            self._update_status(f"Annotations loaded: {os.path.basename(path)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))

    # Reset methods redefined above

    def _toggle_play_pause(self):
        """Single click on viewport: toggle play/pause."""
        if self.playing:
            self.pause()
        else:
            self.play()

    def _toggle_play_button(self):
        """Handle Play/Pause from the HUD button."""
        if self.btn_play.isChecked():
             self.play()
             self.btn_play.setText("||")
        else:
             self.pause()
             self.btn_play.setText("▶")

    def _toggle_loop(self, checked):
        self.loop = checked
        if self._audio_player and hasattr(self._audio_player, 'setLoops'):
            try:
                self._audio_player.setLoops(QMediaPlayer.Loops.Infinite if checked else 1)
            except Exception:
                pass
        
    def _go_to_start(self):
        self.seek(0)
        
    def _go_to_end(self):
        self.seek(max(0, self.core.frame_count() - 1))

    def _on_frame_input(self):
        """User typed a frame number in the box."""
        try:
            val = int(self.curr_frame_edit.text())
            # Clamp? Maybe not, or clamp to available range
            # But frame input usually expects 0-based index or 1-based?
            # Let's assume 0-based index for now matching the slider.
            self.seek(val)
        except ValueError:
            self._update_curr_frame_text()

    def _update_range(self):
        """Called when start/end range texts are edited."""
        cnt = self.core.frame_count()
        if cnt == 0: return
        
        try:
            r_in = int(self.range_start_edit.text())
            r_out = int(self.range_end_edit.text())
        except ValueError:
            # Revert to current
            self.range_start_edit.setText(str(getattr(self, 'range_in', 0)))
            self.range_end_edit.setText(str(getattr(self, 'range_out', cnt-1)))
            return
            
        # Clamp
        r_in = max(0, min(cnt-1, r_in))
        r_out = max(r_in, min(cnt-1, r_out))
        
        self.range_in = r_in
        self.range_out = r_out
        
        self.range_start_edit.setText(str(self.range_in))
        self.range_end_edit.setText(str(self.range_out))
        
        # If playhead outside, move it?
        if self.current_index < r_in:
            self.seek(r_in)
        elif self.current_index > r_out:
            self.seek(r_out)

    # Reset methods redefined above



    def _on_compare_offset_changed(self, val: int):
        self.compare_offset = int(val)
        # Refresh current composite if compare is active
        if self.compare_loaded and self.core.frame_count():
            if self.side_by_side:
                self._show_frame(self.current_index)
            elif self.wipe_mode:
                self._update_wipe()
        self._save_prefs()

    # ---------- Preferences ----------
    def _load_prefs(self):
        try:
            if not os.path.exists(_PREFS_PATH):
                return
            with open(_PREFS_PATH, 'r', encoding='utf-8') as f:
                self.prefs = json.load(f)
            
            self._prefs_input_cs = self.prefs.get('ocio_input')
            self._prefs_output_cs = self.prefs.get('ocio_output') or 'Output - Rec.709'
            self._prefs_ocio_enabled = bool(self.prefs.get('ocio_enabled', False))
            
            # Application state from prefs
            self.exposure = float(self.prefs.get('exposure', 0.0))
            self.gamma = float(self.prefs.get('gamma', 1.0))
            self.compare_offset = int(self.prefs.get('compare_offset', 0))

            # Audio state from prefs
            self._audio_volume = float(self.prefs.get('audio_volume', 1.0))
            self._audio_muted = bool(self.prefs.get('audio_muted', False))
            if hasattr(self, '_audio_output') and self._audio_output:
                self._audio_output.setVolume(self._audio_volume)
                self._audio_output.setMuted(self._audio_muted)
            if hasattr(self, 'volume_slider'):
                self.volume_slider.blockSignals(True)
                self.volume_slider.setValue(int(self._audio_volume * 100))
                self.volume_slider.blockSignals(False)
            if hasattr(self, 'btn_mute'):
                self.btn_mute.blockSignals(True)
                self.btn_mute.setChecked(self._audio_muted)
                self.btn_mute.setText("\U0001F507" if self._audio_muted else "\U0001F50A")
                self.btn_mute.blockSignals(False)

            # Loader Strategy
            strat_val = self.prefs.get('playback_strategy', 'performance')
            try:
                self.core.set_strategy(PlaybackStrategy(strat_val))
            except Exception:
                self.core.set_strategy(PlaybackStrategy.PERFORMANCE)

            # Cache settings
            if 'cache_gb' in self.prefs:
                self.core.set_cache_gb(float(self.prefs['cache_gb']))
            
            self.core.cache_enabled = self.prefs.get('cache_enabled', True)
            self.core.prefetch_enabled = self.prefs.get('preload_cache', True)
            
            if hasattr(self, 'frame_slider'):
                self.frame_slider.set_show_cached(self.prefs.get('show_cached_timeline', True))
            
            self.cinema_mode_enabled = bool(self.prefs.get('cinema_mode_enabled', False))
            self.show_slot_badges = bool(self.prefs.get('show_slot_badges', True))
            if hasattr(self, 'show_slot_badges_action'):
                self.show_slot_badges_action.setChecked(self.show_slot_badges)

            # Kitsu credentials & host restore
            try:
                _qsettings = QtCore.QSettings("VFXPlayer", "Kitsu")
                k_host = self.prefs.get('kitsu_host') or _qsettings.value("host", "")
                k_token = self.prefs.get('kitsu_token') or _qsettings.value("token", "")
                if k_host:
                    kitsu_client.host_url = str(k_host)
                if k_token:
                    kitsu_client.auth_token = str(k_token)
            except Exception:
                pass
                
        except Exception:
            self.prefs = {}

    def _save_prefs(self):
        if not hasattr(self, '_save_prefs_timer'):
            self._save_prefs_timer = QtCore.QTimer(self)
            self._save_prefs_timer.setSingleShot(True)
            self._save_prefs_timer.setInterval(400)
            self._save_prefs_timer.timeout.connect(self._do_save_prefs)
        self._save_prefs_timer.start()

    def _do_save_prefs(self):
        try:
            # Update prefs with current runtime state
            self.prefs['ocio_input'] = self.color_manager.input_cs
            self.prefs['ocio_output'] = self.color_manager.output_cs
            self.prefs['ocio_enabled'] = self.color_manager.ocio_enabled
            self.prefs['exposure'] = self.exposure
            self.prefs['gamma'] = self.gamma
            self.prefs['compare_offset'] = getattr(self, 'compare_offset', 0)
            self.prefs['playback_strategy'] = self.core.strategy.value
            self.prefs['cache_gb'] = self.core.cache_gb
            self.prefs['cache_enabled'] = self.core.cache_enabled
            self.prefs['preload_cache'] = self.core.prefetch_enabled
            self.prefs['show_cached_timeline'] = self.prefs.get('show_cached_timeline', True)
            self.prefs['audio_volume'] = getattr(self, '_audio_volume', 1.0)
            self.prefs['audio_muted'] = getattr(self, '_audio_muted', False)
            self.prefs['cinema_mode_enabled'] = getattr(self, 'cinema_mode_enabled', False)
            self.prefs['show_slot_badges'] = getattr(self, 'show_slot_badges', True)

            # Preserve and save portable relative OCIO config path
            cfg_p = getattr(self.color_manager, 'config_path', None) or self.prefs.get('ocio_config', "")
            if cfg_p and os.path.isabs(cfg_p):
                try:
                    rel = os.path.relpath(cfg_p, _APP_ROOT)
                    if not rel.startswith('..'):
                        cfg_p = rel.replace('\\', '/')
                except Exception:
                    pass
            self.prefs['ocio_config'] = cfg_p or "configs/ocio/config.ocio"

            with open(_PREFS_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.prefs, f, indent=2)
        except Exception:
            pass

    def _open_settings_dialog(self):
        # Ensure prefs are up to date with current UI state before opening
        self.prefs['exposure'] = self.exposure
        self.prefs['gamma'] = self.gamma
        
        dlg = SettingsDialog(self, self.prefs, self.color_manager)
        if dlg.exec():
            new_prefs = dlg.get_prefs()
            self.prefs.update(new_prefs)
            
            # Apply immediate changes
            # 1. Cache GB budget
            cache_gb = self.prefs.get('cache_gb', 4.0)
            self.core.set_cache_gb(cache_gb)
            if hasattr(self, 'core_b') and self.core_b:
                self.core_b.set_cache_gb(cache_gb)
            
            # 2. Cache enabled/disabled
            self.core.cache_enabled = self.prefs.get('cache_enabled', True)
            if hasattr(self, 'core_b') and self.core_b:
                self.core_b.cache_enabled = self.core.cache_enabled
            
            # 3. Prefetch toggle
            self.core.prefetch_enabled = self.prefs.get('preload_cache', True)
            if hasattr(self, 'core_b') and self.core_b:
                self.core_b.prefetch_enabled = self.core.prefetch_enabled
                
            # 4. Playback Strategy
            strat_val = self.prefs.get('playback_strategy', 'performance')
            try:
                self._set_playback_strategy(PlaybackStrategy(strat_val))
            except Exception:
                pass
            
            # 5. OCIO Config path override
            new_ocio = self.prefs.get('ocio_config', "")
            if new_ocio and new_ocio != getattr(self, '_last_applied_ocio', ""):
                # Placeholder for actual OCIO config application logic
                pass # This line is added to ensure syntactical correctness
            
            # 6. Show cached in timeline
            self.frame_slider.set_show_cached(self.prefs.get('show_cached_timeline', True))
            
            # 7. Defaults (applied on next load)
            
            self._save_prefs()

    def _open_export_dialog(self):
        if not self.core.media:
            QtWidgets.QMessageBox.warning(self, "No Media", "Please load a sequence or video first.")
            return
        dlg = ExportDialog(self, self.core)
        dlg.exec()

    def _open_metadata_dialog(self):
        if not self.core.media:
            QtWidgets.QMessageBox.warning(self, "No Media", "Please load a sequence or video first.")
            return
            
        if not hasattr(self, 'metadata_dialog') or not self.metadata_dialog:
            self.metadata_dialog = MetadataDialog(self, self.core)
            
        self.metadata_dialog.update_metadata(self.current_index)
        self.metadata_dialog.show()
        self.metadata_dialog.raise_()
        self.metadata_dialog.activateWindow()

    # ---------- Help & Reference Dialogs ----------
    def _show_shortcuts_dialog(self):
        """Open the Nuke-style Keyboard Shortcuts & Hotkey Reference dialog."""
        dlg = ShortcutsDialog(self)
        dlg.exec()

    def _show_about_dialog(self):
        """Open the About VFX Review Player dialog."""
        dlg = AboutDialog(self)
        dlg.exec()

    def _open_docs(self):
        """Open documentation or README in default application / browser."""
        readme_path = os.path.join(_APP_ROOT, "README.md")
        if os.path.exists(readme_path):
            try:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(readme_path))
                return
            except Exception:
                pass
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/azhagurajpandians/vfx-player#readme"))

    def _open_github_repo(self):
        """Open official GitHub repository."""
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/azhagurajpandians/vfx-player"))

    # ---------- Core Actions ----------
    def load_media(self, path: str):
        # Reset Gain/Gamma to defaults on each new load
        self._reset_exposure()
        self._reset_gamma()
        
        try:
            self.core.load(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))
            return
        # Update playback model based on media type
        if self.core.media and self.core.media.type == 'video':
            # Use source FPS for accurate realtime playback; lock FPS edit (informational)
            fps = self.core.media_fps() or 24.0
            self.fps_edit.setText(f"{fps:.2f}")
            self.fps_edit.setDisabled(True)
            # Videos use source FPS; prefetch stays enabled to allow read-ahead/pruning
            self.core.prefetch_enabled = True
            
        # Apply OCIO Defaults based on type
        ext = os.path.splitext(path)[1].lower()
        def_key = None
        if ext in ('.exr', '.sxr', '.dpx', '.cin', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.tga', '.bmp', '.webp'): # Image sequences
            def_key = 'exr'
        elif ext in ('.mov', '.mp4', '.avi', '.mkv', '.webm', '.m4v', '.flv', '.ts'): # Videos
            def_key = 'mov'
            
        if def_key and 'defaults' in self.prefs and def_key in self.prefs['defaults']:
            defs = self.prefs['defaults'][def_key]
            cin = defs.get('input')
            cout = defs.get('output')
            changed = False
            if cin and cin in self.color_manager.input_choices:
                self.color_manager.input_cs = cin
                changed = True
            if cout and cout in self.color_manager.output_choices:
                self.color_manager.output_cs = cout
                changed = True
                
            if changed:
                self.color_manager.rebuild_processor()
                self._update_ocio_ui()
                if hasattr(self, 'viewer_combo') and self.color_manager.output_cs:
                     idx = self.viewer_combo.findText(self.color_manager.output_cs)
                     if idx >= 0:
                         self.viewer_combo.blockSignals(True)
                         self.viewer_combo.setCurrentIndex(idx)
                         self.viewer_combo.blockSignals(False)

        # Apply cache settings immediately based on prefs
        self.core.set_cache_gb(self.prefs.get('cache_gb', 4.0))

        # Sync OCIO params to background loader
        self._sync_ocio_to_loader()
        
        self.current_index = 0
        cnt = self.core.frame_count()
        self.frame_slider.setMaximum(max(0, cnt - 1))
        self._configure_frame_slider_ticks()
        
        # Init Range
        self.range_in = 0
        self.range_out = max(0, cnt - 1)
        if hasattr(self, 'range_start_edit'):
            self.range_start_edit.setText(str(self.range_in))
        if hasattr(self, 'range_end_edit'):
            self.range_end_edit.setText(str(self.range_out))

        # Version Detection
        try:
            self.version_group = VersionDetector.find_versions(path)
            self._update_version_ui()
        except Exception:
            self.version_group = None

        # Auto-load Persistent Annotations & Bookmarks (.review.json sidecar)
        try:
            sidecar = AnnotationService.load_sidecar(path)
            if sidecar:
                self.annotations = sidecar.get("annotations", {})
                self.bookmarks = set(sidecar.get("bookmarks", []))
                if sidecar.get("in_point") is not None:
                    self.range_in = max(0, min(cnt - 1, sidecar["in_point"]))
                if sidecar.get("out_point") is not None:
                    self.range_out = max(self.range_in, min(cnt - 1, sidecar["out_point"]))
                if hasattr(self, 'range_start_edit'):
                    self.range_start_edit.setText(str(self.range_in))
                if hasattr(self, 'range_end_edit'):
                    self.range_end_edit.setText(str(self.range_out))
                self._refresh_annotation_display()
            else:
                self.annotations = {}
                self.bookmarks = set()
                self._refresh_annotation_display()
        except Exception:
            self.annotations = {}
            self.bookmarks = set()

        self._update_timeline_markers()
        
        # Reset viewport state to force auto-fit when frame loads
        self.viewport._last_shape = None
        self._show_frame(0)
        
        self._status_base = f"Loaded: {path}"
        if self.version_group and len(self.version_group.versions) > 1:
            self._status_base += f" (v{self.version_group.current_version:03d}, {len(self.version_group.versions)} versions detected)"
        self._update_status(self._status_base)
        self._update_timer_interval()

        # Update HUD if visible or load it for later
        if self.core.media:
            self.props_hud.update_info(self.core.media)

        # Update Kitsu shot context if not already assigned by playlist or switching versions
        if getattr(self, '_switching_kitsu_version', False):
            pass
        elif not getattr(self, '_current_kitsu_shot', None) or (self._current_kitsu_shot.media_path != path and not getattr(self._current_kitsu_shot, 'kitsu_shot_id', None)):
            p_ctx = kitsu_client.parse_shot_context(path)
            self._current_kitsu_shot = PlaylistItem(
                media_path=path,
                sequence_name=p_ctx.get('sequence'),
                shot_name=p_ctx.get('shot'),
                task_name=p_ctx.get('task'),
                version=p_ctx.get('version'),
                frame_count=cnt,
                fps=self.core.media_fps() or 24.0
            )
        elif self._current_kitsu_shot and self._current_kitsu_shot.media_path != path:
            if not getattr(self._current_kitsu_shot, 'kitsu_shot_id', None) and "vfxplayer_kitsu_cache" not in path:
                self._current_kitsu_shot.media_path = path

        # Synchronize Tasks and Versions (Local Disk + Kitsu) - only when opening new shot, not when switching version
        if not getattr(self, '_switching_kitsu_version', False):
            self._sync_versions_and_tasks(path)

        # Keep playlist in sync: Auto-scan sibling clips in folder so PageUp/PageDown works by default
        if hasattr(self, 'playlist_service') and hasattr(self, 'playlist_widget'):
            if getattr(self, '_switching_kitsu_version', False) or getattr(self, '_loading_from_playlist', False):
                pass
            elif getattr(self, '_custom_playlist_active', False):
                existing_idx = -1
                for i, it in enumerate(self.playlist_service.items):
                    if it.media_path == path or getattr(it, 'preview_cache_path', None) == path:
                        existing_idx = i
                        break
                if existing_idx >= 0:
                    self.playlist_widget.set_current_index(existing_idx)
            else:
                self._auto_populate_folder_playlist(path)

        # Audio: attach source for video files
        self._audio_attach(path)

        # Ensure playhead starts at 0 for new media and auto-play
        self.current_index = 0
        self._play_start_index = 0
        if self._elapsed_timer is not None:
            self._elapsed_timer.restart()
        self.seek(0)
        self.play(force_restart=True)

        # Mark media loaded and apply view mode (Normal view by default)
        self._media_loaded = True
        if getattr(self, 'cinema_mode_enabled', False):
            self._set_frameless(True)
            self._hide_ui_controls()
        else:
            self._set_frameless(False)
            self._show_ui_controls()

    def _auto_populate_folder_playlist(self, current_path: str):
        """
        Auto-populates the playlist with sibling videos and image sequences in the same folder,
        ensuring PageUp/PageDown works seamlessly out of the box for any opened file.
        """
        if getattr(self, '_loading_from_playlist', False) or getattr(self, '_switching_kitsu_version', False):
            for i, it in enumerate(self.playlist_service.items):
                if it.media_path == current_path or getattr(it, 'preview_cache_path', None) == current_path:
                    self.playlist_widget.set_current_index(i)
                    break
            return

        is_url = current_path.startswith("http://") or current_path.startswith("https://")
        if is_url or not os.path.exists(current_path):
            return

        import re
        from core.player_core import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, detect_image_sequence

        abs_path = os.path.abspath(current_path)

        # Never auto-populate from Kitsu temporary cache directory
        if "vfxplayer_kitsu_cache" in abs_path or abs_path.startswith(tempfile.gettempdir()):
            return

        # Never overwrite an active custom or Kitsu review playlist
        if getattr(self, '_custom_playlist_active', False) or any(getattr(it, 'kitsu_shot_id', None) for it in self.playlist_service.items):
            return

        folder = os.path.dirname(abs_path)
        if not os.path.isdir(folder):
            return

        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            return

        items: List[PlaylistItem] = []
        processed_bases = set()
        current_idx = 0

        for f in entries:
            full_p = os.path.join(folder, f)
            if not os.path.isfile(full_p):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                ctx = kitsu_client.parse_shot_context(full_p)
                shot_name = ctx.get("shot") or os.path.splitext(f)[0]
                item = PlaylistItem(
                    media_path=full_p,
                    name=f,
                    sequence=ctx.get("sequence", ""),
                    shot=shot_name,
                    task=ctx.get("task", ""),
                    version=ctx.get("version", "")
                )
                items.append(item)
            elif ext in IMAGE_EXTENSIONS:
                base = os.path.splitext(f)[0]
                base_key = re.sub(r'\d+$', '', base)
                if base_key in processed_bases:
                    continue
                processed_bases.add(base_key)

                seq = detect_image_sequence(full_p)
                first_f = seq[0] if seq else full_p
                ctx = kitsu_client.parse_shot_context(first_f)
                shot_name = ctx.get("shot") or re.sub(r'[._-]\d+$', '', os.path.splitext(os.path.basename(first_f))[0])
                item = PlaylistItem(
                    media_path=first_f,
                    name=shot_name,
                    sequence=ctx.get("sequence", ""),
                    shot=shot_name,
                    task=ctx.get("task", ""),
                    version=ctx.get("version", ""),
                    frame_count=len(seq) if seq else 1
                )
                items.append(item)

        if items:
            cur_base = re.sub(r'\d+$', '', os.path.splitext(os.path.basename(abs_path))[0])
            for idx, it in enumerate(items):
                it_base = re.sub(r'\d+$', '', os.path.splitext(os.path.basename(it.media_path))[0])
                if it.media_path == abs_path or it_base == cur_base:
                    current_idx = idx
                    break

            self.playlist_service.items = items
            self.playlist_service.active_index = current_idx
            self.playlist_widget.refresh()
            self.playlist_widget.set_current_index(current_idx)

    def _set_frameless(self, frameless: bool):
        if getattr(self, '_is_frameless', False) == frameless or getattr(self, 'fullscreen', False):
            return
        self._is_frameless = frameless
        pos = self.pos()
        size = self.size()
        was_max = self.isMaximized()
        
        if frameless:
            # Set exact Window + FramelessWindowHint to strip OS title bar & window frame completely
            self.setWindowFlags(QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.FramelessWindowHint)
        else:
            self.setWindowFlags(QtCore.Qt.WindowType.Window)
            
        if was_max:
            self.showMaximized()
        else:
            self.move(pos)
            self.resize(size)
            self.show()
        set_dark_title_bar(self.winId())

    def _toggle_cinema_mode(self, enabled: bool = None):
        if enabled is None:
            enabled = not getattr(self, 'cinema_mode_enabled', True)
        self._set_view_preset('minimal' if enabled else 'normal')

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        # In Minimal View, keep GUI hidden (no mouse-over unhide)
        return super().eventFilter(watched, event)

    def _set_view_preset(self, preset: str):
        if preset == 'minimal':
            self.cinema_mode_enabled = True
            self._set_frameless(True)
            self._hide_ui_controls()
        elif preset == 'normal':
            self.cinema_mode_enabled = False
            self._set_frameless(False)
            self._show_ui_controls()
            
        if hasattr(self, 'minimal_action'):
            self.minimal_action.setChecked(self.cinema_mode_enabled)
        if hasattr(self, 'normal_action'):
            self.normal_action.setChecked(not self.cinema_mode_enabled)
            
        self._save_prefs()

    def _show_context_menu(self, global_pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a1a; color: #ddd; border: 1px solid #333; font-family: 'Segoe UI', sans-serif; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: #0078d4; color: white; }
        """)
        
        view_sub = menu.addMenu("View")
        
        min_act = view_sub.addAction("Minimal View (1)")
        min_act.setCheckable(True)
        min_act.setChecked(getattr(self, 'cinema_mode_enabled', True))
        min_act.triggered.connect(lambda: self._set_view_preset('minimal'))
        
        norm_act = view_sub.addAction("Normal View (2)")
        norm_act.setCheckable(True)
        norm_act.setChecked(not getattr(self, 'cinema_mode_enabled', True))
        norm_act.triggered.connect(lambda: self._set_view_preset('normal'))
        
        fs_act = view_sub.addAction("Fullscreen (F11)")
        fs_act.setCheckable(True)
        fs_act.setChecked(getattr(self, 'fullscreen', False))
        fs_act.triggered.connect(lambda: self._toggle_fullscreen(not self.fullscreen))

        annot_act = view_sub.addAction("Annotation Mode (N)")
        annot_act.setCheckable(True)
        annot_act.setChecked(getattr(self.viewport, 'is_drawing', False))
        annot_act.triggered.connect(lambda: self._toggle_annotate_mode())

        export_all_annot_act = menu.addAction("Export All Annotated Frames... (Ctrl+Shift+E)")
        export_all_annot_act.triggered.connect(self._export_all_annotated_frames)

        menu.addSeparator()
        
        play_act = menu.addAction("Pause" if self.playing else "Play")
        play_act.triggered.connect(self._toggle_play_pause)
        
        stop_act = menu.addAction("Stop")
        stop_act.triggered.connect(self.stop)
        
        menu.addSeparator()
        
        open_act = menu.addAction("Open Media...")
        open_act.triggered.connect(self._open_file)
        
        exit_act = menu.addAction("Exit")
        exit_act.triggered.connect(self.close)
        
        menu.exec(global_pos)

    def _show_ui_controls(self):
        self._ui_visible = True
        self.menuBar().show()
        self.statusBar().show()
        if hasattr(self, 'hud_container'):
            self.hud_container.show()
            self.hud_container.setFixedHeight(60)
        if hasattr(self, 'controls_container'):
            self.controls_container.show()

    def _hide_ui_controls(self):
        self._ui_visible = False
        self.menuBar().hide()
        self.statusBar().hide()
        if hasattr(self, 'hud_container'):
            self.hud_container.hide()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and getattr(self, '_is_frameless', False):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if event.buttons() == QtCore.Qt.MouseButton.LeftButton and getattr(self, '_drag_pos', None) is not None and getattr(self, '_is_frameless', False):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)



    def _show_frame(self, index: int, is_scrubbing: bool = False):
        self.current_index = index

        frame_raw = self.core.get_frame(index, is_scrubbing=is_scrubbing)
        
        # If cache miss, schedule polling for this exact target
        if frame_raw is None:
            self._target_frame_index = index
            if not self._pending_frame_timer.isActive():
                self._pending_frame_timer.start()
            return
        else:
            # Cache hit: always stop polling and clear target to avoid stale frame overwrites
            self._pending_frame_timer.stop()
            self._target_frame_index = -1

        # Force fit if requested (e.g. after fullscreen)
        if getattr(self, '_force_fit_next_frame', False):
            self.viewport.fit_to_window()
            if self.side_by_side and hasattr(self, 'viewport_b'):
                self.viewport_b.fit_to_window()
            self._force_fit_next_frame = False
        
        # Decide which frame to display in the primary viewport
        active_frame = frame_raw
        if not self.side_by_side and not self.wipe_mode and getattr(self, 'show_compare_b', False) and self.compare_loaded:
            idx_b = max(0, min(self.core_b.frame_count() - 1, index + int(getattr(self, 'compare_offset', 0))))
            cframe_raw = self.core_b.get_frame(idx_b)
            if cframe_raw is not None:
                active_frame = cframe_raw

        self.viewport.set_frame(active_frame)
        self.viewport.set_exposure(self.exposure)
        self.viewport.set_gamma(self.gamma)
        self.viewport.set_channel_mode(self.channel_mode)
        self.viewport.set_alpha_mode(getattr(self, 'alpha_mode', 'RGB'))
        if hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.set_grade_params(exposure=self.exposure, gamma=self.gamma)
        
        if hasattr(self, 'scopes_dialog') and self.scopes_dialog and self.scopes_dialog.isVisible():
            self.scopes_dialog.update_image(active_frame)
        
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(index)
        self.frame_slider.blockSignals(False)
        self.current_index = index
        
        if hasattr(self, 'curr_frame_edit') and not self.curr_frame_edit.hasFocus():
            self.curr_frame_edit.setText(str(index))
        if hasattr(self, 'lbl_total_frames_inline') and self.core.media:
            self.lbl_total_frames_inline.setText(f"/ {max(0, self.core.frame_count() - 1)}")
        if hasattr(self, 'status_timecode_badge'):
            fps = self.core.media_fps() or 24.0
            self.status_timecode_badge.setText(self._format_timecode(index, fps))
        
        # Apply annotations when annotation mode is active
        if getattr(self, 'btn_annotate', None) and self.btn_annotate.isChecked():
            strokes = self.annotations.get(index, [])
            self.viewport.set_annotations(strokes)

        # Update undo/redo button states for new frame
        self._update_annotation_undo_redo_ui()

        # Update metadata dialog dynamically if open
        if hasattr(self, 'metadata_dialog') and self.metadata_dialog and self.metadata_dialog.isVisible():
            if self.metadata_dialog.dynamic_update_checkbox.isChecked():
                self.metadata_dialog.update_metadata(index)
 
        # Draw frame in the main viewport in wipe mode if active
        if self.wipe_mode and self.compare_loaded and self.core_b.frame_count() > 0:
            idx_b = max(0, min(self.core_b.frame_count() - 1, index + int(getattr(self, 'compare_offset', 0))))
            cframe_raw = self.core_b.get_frame(idx_b)
            if cframe_raw is not None:
                self.viewport.composite_wipe(active_frame, cframe_raw, self.wipe_slider.value() / 1000.0)
                self.viewport.set_exposure(self.exposure)
                self.viewport.set_gamma(self.gamma)
                self.viewport.set_channel_mode(self.channel_mode)
                self.viewport.set_alpha_mode(getattr(self, 'alpha_mode', 'RGB'))

        # Update and sync all visible secondary/grid viewports
        for v_idx, vp in enumerate(self.viewports):
            if v_idx == 0:
                continue # Already updated primary viewport
            if vp.isVisible():
                core_val = self.cores[v_idx]
                if core_val.frame_count() > 0:
                    offset = int(getattr(self, 'compare_offset', 0)) if v_idx >= 1 else 0
                    idx_val = max(0, min(core_val.frame_count() - 1, index + offset))
                    cframe = core_val.get_frame(idx_val)
                    if cframe is not None:
                        vp.set_frame(cframe)
                        vp.set_exposure(self.exposure)
                        vp.set_gamma(self.gamma)
                        vp.set_channel_mode(self.channel_mode)
                        vp.set_alpha_mode(getattr(self, 'alpha_mode', 'RGB'))
                        
                if getattr(self, 'btn_annotate', None) and self.btn_annotate.isChecked():
                    strokes = self.annotations.get(index, [])
                    vp.set_annotations(strokes)


    def _check_pending_frame(self):
        """Called by timer to check if pending frame is ready."""
        target = self._target_frame_index
        if target < 0:
            self._pending_frame_timer.stop()
            return
        if target != self.current_index:
            self._pending_frame_timer.stop()
            self._target_frame_index = -1
            return
        frame = self.core.get_frame(target)
        if frame is not None:
            self._pending_frame_timer.stop()
            self._target_frame_index = -1
            self._show_frame(target)


    def _advance_frame(self):
        cnt = self.core.frame_count()
        if cnt == 0:
            return

        # Determine Range (fallback to full range if not set)
        r_in = getattr(self, 'range_in', 0)
        r_out = getattr(self, 'range_out', cnt - 1)
        # Validate
        r_in = max(0, min(cnt-1, r_in))
        r_out = max(r_in, min(cnt-1, r_out))

        # Advance logic - unified elapsed-time approach for all media types
        if self._elapsed_timer is None:
            self._elapsed_timer = QtCore.QElapsedTimer()
            self._elapsed_timer.start()

        base_fps = self.core.media_fps() or 24.0
        fps = base_fps * self.playback_speed
        direction = getattr(self, 'play_direction', 1)

        # Audio Master Clock:
        # In media players, the sound card is the true reference clock. When audio is playing forward
        # at 1.0x, video synchronizes directly to the audio position.
        # Only activate when media actually has audio and outside of seek grace periods.
        audio_sync_active = (
            self._audio_player is not None
            and getattr(self, '_has_audio', False)
            and self._audio_player.source().isValid()
            and self._audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            and direction > 0
            and self.playback_speed == 1.0
            and time.time() > getattr(self, '_audio_seek_grace_until', 0.0)
        )

        use_audio_clock = False
        if audio_sync_active:
            a_pos = self._audio_player.position()
            expected_start_ms = int(self._play_start_index * 1000.0 / base_fps)
            # Once audio has reached or passed the initial start time, lock video to audio
            if a_pos >= max(0, expected_start_ms - 100):
                next_idx = int(a_pos * base_fps / 1000.0)
                use_audio_clock = True

        if not use_audio_clock:
            ms = self._elapsed_timer.elapsed()
            frames = int(ms * fps / 1000.0)
            if direction >= 0:
                next_idx = self._play_start_index + frames
            else:
                next_idx = self._play_start_index - frames

        if direction >= 0:
            # Check against Range Out
            if next_idx > r_out:
                if self.loop:
                    next_idx = r_in
                    self._elapsed_timer.restart()
                    self._play_start_index = r_in
                    # Prefetch beginning of loop immediately so looping never drops frames
                    if hasattr(self.core, 'burst_prefetch'):
                        self.core.burst_prefetch(r_in, count=min(48, cnt), direction=1)
                    # Loop audio if applicable
                    if self._audio_player and self._audio_player.source().isValid() and getattr(self, '_has_audio', False) and self.playback_speed == 1.0:
                        pos_ms = int(r_in * 1000.0 / base_fps)
                        self._audio_player.setPosition(pos_ms)
                        if self._audio_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                            self._audio_player.play()
                        self._audio_seek_grace_until = time.time() + 0.15
                else:
                    # Check if playlist has a next shot to play continuously
                    if hasattr(self, 'playlist_service') and len(self.playlist_service.items) > 1:
                        if self.playlist_service.has_next() or self.playlist_service.loop:
                            self._playlist_seamless_next()
                            return
                    next_idx = r_out
                    self.pause()
                    return
        else:
            next_idx = self._play_start_index - frames
            # Check against Range In
            if next_idx < r_in:
                if self.loop:
                    next_idx = r_out
                    self._elapsed_timer.restart()
                    self._play_start_index = r_out
                    if hasattr(self.core, 'burst_prefetch'):
                        self.core.burst_prefetch(r_out, count=min(48, cnt), direction=-1)
                else:
                    # Check if playlist has a previous shot to play continuously in reverse
                    if hasattr(self, 'playlist_service') and len(self.playlist_service.items) > 1:
                        if self.playlist_service.has_prev() or self.playlist_service.loop:
                            self._playlist_seamless_prev()
                            return
                    next_idx = r_in
                    self.pause()
                    return

        # Don't re-display the same frame
        if next_idx == self.current_index:
            return

        # Ensure predictive prefetching is oriented in play_direction across all visible active cores
        if hasattr(self.core, 'predictive_prefetch'):
            self.core.predictive_prefetch(next_idx, direction=direction)
        for v_idx, vp in enumerate(getattr(self, 'viewports', [])):
            if v_idx > 0 and vp.isVisible() and v_idx < len(self.cores):
                c = self.cores[v_idx]
                if c.frame_count() > 0 and hasattr(c, 'predictive_prefetch'):
                    c.predictive_prefetch(next_idx, direction=direction)

        # --- Drop-frame strategy (MPC-style) ---
        # If the target frame isn't ready, we DO NOT jump sideways to find another 
        # (which caused original strobing), and we DO NOT reset the clock (which caused stuttering).
        # We simply drop the frame and wait for the next tick, leaving the clock running in real-time.
        frame_raw = self.core.get_frame(next_idx)
        if frame_raw is None:
            return

        self.seek(next_idx, update_audio=False, from_advance=True)


    def seek(self, index: int, update_audio=True, from_advance=False):
        idx = int(index)
        if 0 <= idx < self.core.frame_count():
            is_scrubbing = False
            if hasattr(self, 'frame_slider') and self.frame_slider.isSliderDown():
                is_scrubbing = True

            # Update elapsed timer and start index only for manual seeks, scrubbing, or jumps
            # (not during internal playback frame advancement, to prevent sub-millisecond clock truncation)
            if self.playing and not from_advance:
                if self._elapsed_timer is None:
                    self._elapsed_timer = QtCore.QElapsedTimer()
                self._elapsed_timer.restart()
                self._play_start_index = idx

            self._show_frame(idx, is_scrubbing=is_scrubbing)
            # Sync audio position for video files when user explicitly seeks or scrubs
            if update_audio and self._audio_player and self._audio_player.source().isValid():
                fps = self.core.media_fps() or 24.0
                pos_ms = int(idx * 1000.0 / fps)
                self._audio_player.setPosition(pos_ms)

    def _on_scrub_finished(self):
        """Called when user releases slider after scrubbing."""
        if hasattr(self, 'core') and self.core and self.core.media:
            self.core.predictive_prefetch(self.current_index, getattr(self.core, 'last_direction', 1))

    def play(self, direction: int = 1, force_restart: bool = False):
        if not force_restart and self.playing and getattr(self, 'play_direction', 1) == direction:
            return
        self.playing = True
        self.play_direction = 1 if direction >= 0 else -1

        # Unified elapsed-time playback for all media types
        self._elapsed_timer = QtCore.QElapsedTimer()
        self._elapsed_timer.start()
        self._play_start_index = self.current_index

        # 8ms heartbeat (~125fps cap) for smooth frame sync
        self.timer.start(8)

        # Prefetch burst: load 48 frames in play direction for primary and visible grid cores
        if hasattr(self.core, 'burst_prefetch'):
            self.core.burst_prefetch(self.current_index, count=48, direction=self.play_direction)
        for v_idx, vp in enumerate(getattr(self, 'viewports', [])):
            if v_idx > 0 and vp.isVisible() and v_idx < len(self.cores):
                c = self.cores[v_idx]
                if c.frame_count() > 0 and hasattr(c, 'burst_prefetch'):
                    c.burst_prefetch(self.current_index, count=48, direction=self.play_direction)

        # Audio: only forward playback at 1.0x plays audio when media actually has an audio stream
        if self._audio_player and self._audio_player.source().isValid() and getattr(self, '_has_audio', False):
            if hasattr(self._audio_player, 'setLoops'):
                try:
                    self._audio_player.setLoops(QMediaPlayer.Loops.Infinite if getattr(self, 'loop', True) else 1)
                except Exception:
                    pass
            if self.play_direction == 1 and self.playback_speed == 1.0:
                fps = self.core.media_fps() or 24.0
                pos_ms = int(self.current_index * 1000.0 / fps)
                self._audio_player.setPosition(pos_ms)
                self._audio_player.play()
            else:
                self._audio_player.pause()
        elif self._audio_player:
            self._audio_player.pause()

        # Update UI
        if hasattr(self, 'btn_play'):
            self.btn_play.blockSignals(True)
            self.btn_play.setChecked(True)
            self.btn_play.setText("||")
            self.btn_play.blockSignals(False)

        dir_lbl = "Reverse " if self.play_direction == -1 else ""
        self._status_base = f"Playing {dir_lbl}({self.playback_speed}x)" if self.playback_speed != 1.0 else (f"Playing {dir_lbl}".strip())
        self._update_status(self._status_base)

    def play_reverse(self):
        """Start reverse playback or cycle reverse speed (JKL style)."""
        if self.playing and getattr(self, 'play_direction', 1) == -1:
            rev_speeds = [1.0, 1.5, 2.0, 4.0]
            try:
                idx = rev_speeds.index(self.playback_speed)
                next_s = rev_speeds[(idx + 1) % len(rev_speeds)]
            except ValueError:
                next_s = 1.0
            self._on_speed_changed(next_s)
            return

        self.playback_speed = 1.0
        if hasattr(self, 'speed_btn'):
            self.speed_btn.setText("1.0x")
        self.play(direction=-1)

    def pause(self):
        if not self.playing:
            return
        self.playing = False
        self.timer.stop()
        self._elapsed_timer = None

        # Audio
        if self._audio_player:
            self._audio_player.pause()

        # Update UI
        if hasattr(self, 'btn_play'):
            self.btn_play.blockSignals(True)
            self.btn_play.setChecked(False)
            self.btn_play.setText("▶")
            self.btn_play.blockSignals(False)

        self._status_base = "Paused"
        self._update_status(self._status_base)

    def stop(self):
        self.pause()
        self.seek(0)
        self._elapsed_timer = None
        if self._audio_player:
            self._audio_player.stop()
        self._status_base = "Stopped"
        self._update_status(self._status_base)

    # ---------- Helpers ----------
    def _interval_ms(self):
        # For videos, honor the source FPS; for images/sequences, use the UI FPS
        if self.core and self.core.media and self.core.media.type == 'video':
            fps = self.core.media_fps() or 24.0
        else:
            try:
                fps = float(self.fps_edit.text())
                if fps <= 0:
                    raise ValueError
            except ValueError:
                fps = 24.0
                self.fps_edit.setText("24.0")
        return int(1000 / fps)

    def _update_timer_interval(self):
        if self.playing:
            self.timer.start(self._interval_ms())

    # ---------- Audio helpers ----------
    def _audio_attach(self, path: str):
        """Attach audio source when a video file is loaded. No-op for image sequences."""
        if not self._audio_player:
            return
            
        try:
            self._audio_player.mediaStatusChanged.disconnect()
        except TypeError:
            pass
            
        ext = os.path.splitext(path)[1].lower()
        video_exts = {'.mov', '.mp4', '.avi', '.mkv', '.mxf', '.webm'}
        
        if ext in video_exts:
            if hasattr(self._audio_player, 'setLoops'):
                try:
                    self._audio_player.setLoops(QMediaPlayer.Loops.Infinite if getattr(self, 'loop', True) else 1)
                except Exception:
                    pass
            # Synchronously initialize _has_audio from media probe
            self._has_audio = bool(getattr(getattr(self, 'core', None), 'media', None) and getattr(self.core.media, 'has_audio', False))
            self._audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
            
            def _on_media_status(status):
                if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
                    has_audio = self._audio_player.hasAudio()
                    self._has_audio = has_audio
                    if hasattr(self, 'btn_mute'):
                        self.btn_mute.setEnabled(has_audio)
                    if hasattr(self, 'volume_slider'):
                        self.volume_slider.setEnabled(has_audio)
                        
                    if has_audio:
                        if hasattr(self, 'btn_mute'):
                            self.btn_mute.setStyleSheet("""
                                QPushButton {
                                    background: transparent;
                                    color: #ccc;
                                    font-size: 14px;
                                    border: 1px solid #444;
                                    border-radius: 4px;
                                    padding: 2px 6px;
                                }
                                QPushButton:checked { color: #ff9800; border-color: #ff9800; }
                                QPushButton:hover { background: #333; color: white; }
                            """)
                        if hasattr(self, 'volume_slider'):
                            self.volume_slider.setStyleSheet("""
                                QSlider::groove:horizontal { border: 1px solid #444; height: 3px; background: #333; border-radius: 1px; }
                                QSlider::handle:horizontal { background: #aaa; border: 1px solid #666; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }
                                QSlider::handle:horizontal:hover { background: #fff; }
                                QSlider::sub-page:horizontal { background: #4a90e2; }
                            """)
                        if self._audio_output:
                            self._audio_output.setVolume(self._audio_volume)
                            self._audio_output.setMuted(self._audio_muted)

                        # If playback has already started (e.g. on initial load), start audio immediately
                        if getattr(self, 'playing', False) and getattr(self, 'play_direction', 1) == 1 and getattr(self, 'playback_speed', 1.0) == 1.0:
                            fps = self.core.media_fps() or 24.0
                            pos_ms = int(getattr(self, 'current_index', 0) * 1000.0 / fps)
                            self._audio_player.setPosition(pos_ms)
                            if self._audio_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                                self._audio_player.play()
                    else:
                        if hasattr(self, 'btn_mute'):
                            self.btn_mute.setStyleSheet("QPushButton { color: #555; background: transparent; border: 1px solid #333; }")
                        if hasattr(self, 'volume_slider'):
                            self.volume_slider.setStyleSheet("""
                                QSlider::groove:horizontal { border: 1px solid #333; height: 3px; background: #222; }
                                QSlider::handle:horizontal { background: #444; border: 1px solid #333; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }
                                QSlider::sub-page:horizontal { background: #555; }
                            """)
            
            self._audio_player.mediaStatusChanged.connect(_on_media_status)
        else:
            # Image sequence — clear audio source
            self._has_audio = False
            self._audio_player.setSource(QUrl())
            if hasattr(self, 'btn_mute'):
                self.btn_mute.setEnabled(False)
                self.btn_mute.setStyleSheet("QPushButton { color: #555; background: transparent; border: 1px solid #333; }")
            if hasattr(self, 'volume_slider'):
                self.volume_slider.setEnabled(False)
                self.volume_slider.setStyleSheet("""
                    QSlider::groove:horizontal { border: 1px solid #333; height: 3px; background: #222; }
                    QSlider::handle:horizontal { background: #444; border: 1px solid #333; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }
                    QSlider::sub-page:horizontal { background: #555; }
                """)

    def _toggle_mute(self, checked: bool = None):
        """Toggle audio mute. Can be called from button or M hotkey."""
        if checked is None:
            self._audio_muted = not self._audio_muted
        else:
            self._audio_muted = bool(checked)
        if self._audio_output:
            self._audio_output.setMuted(self._audio_muted)
        # Update button state
        if hasattr(self, 'btn_mute'):
            self.btn_mute.blockSignals(True)
            self.btn_mute.setChecked(self._audio_muted)
            self.btn_mute.setText("\U0001F507" if self._audio_muted else "\U0001F50A")
            self.btn_mute.blockSignals(False)
        self._save_prefs()

    def _on_volume_changed(self, val: int):
        """Volume slider moved (0-100)."""
        self._audio_volume = val / 100.0
        if self._audio_output:
            self._audio_output.setVolume(self._audio_volume)
            # Un-mute automatically when user drags the slider
            if val > 0 and self._audio_muted:
                self._toggle_mute(False)
        self._save_prefs()

    def _on_speed_changed(self, speed: float):
        self.playback_speed = speed
        if hasattr(self, 'speed_btn'):
            self.speed_btn.setText(f"{speed}x")

        # If playing, we need to reset the elapsed timer and start index
        # so the speed change feels seamless and doesn't jump.
        if self.playing:
            self._elapsed_timer.restart()
            self._play_start_index = self.current_index

        self._refresh_status_metrics()

    def _update_status(self, msg: str):
        self._status_base = msg
        if hasattr(self, 'status_state_badge'):
            if self.playing:
                if getattr(self, 'play_direction', 1) == -1:
                    self.status_state_badge.setText("◀ REVERSE")
                    self.status_state_badge.setStyleSheet("""
                        background-color: rgba(10, 132, 255, 0.15);
                        border: 1px solid rgba(10, 132, 255, 0.35);
                        border-radius: 4px;
                        color: #0a84ff;
                        padding: 2px 7px;
                        font-size: 11px;
                        font-weight: 600;
                    """)
                else:
                    self.status_state_badge.setText("● PLAYING")
                    self.status_state_badge.setStyleSheet("""
                        background-color: rgba(48, 209, 88, 0.15);
                        border: 1px solid rgba(48, 209, 88, 0.35);
                        border-radius: 4px;
                        color: #30d158;
                        padding: 2px 7px;
                        font-size: 11px;
                        font-weight: 600;
                    """)
            elif "Paused" in msg or "Stopped" in msg:
                self.status_state_badge.setText("⏸ PAUSED")
                self.status_state_badge.setStyleSheet("""
                    background-color: rgba(255, 159, 10, 0.15);
                    border: 1px solid rgba(255, 159, 10, 0.35);
                    border-radius: 4px;
                    color: #ff9f0a;
                    padding: 2px 7px;
                    font-size: 11px;
                    font-weight: 600;
                """)
            else:
                self.status_state_badge.setText("● READY")
                self.status_state_badge.setStyleSheet("""
                    background-color: #1e1e22;
                    border: 1px solid #2c2c30;
                    border-radius: 4px;
                    color: #8e8e93;
                    padding: 2px 7px;
                    font-size: 11px;
                    font-weight: 600;
                """)
        self._refresh_status_metrics()

    def _refresh_status_metrics(self):
        if not hasattr(self, 'status_state_badge'):
            return

        if not self.core.media:
            self.status_state_badge.setText("● READY")
            self.status_state_badge.setStyleSheet("""
                background-color: #1e1e22;
                border: 1px solid #2c2c30;
                border-radius: 4px;
                color: #8e8e93;
                padding: 2px 7px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.status_res_badge.setText("No Media")
            self.status_frames_badge.setText("0 Frames")
            self.status_fps_badge.setText("24.00 fps")
            self.status_cache_badge.setText("Cache: 0/0 (0%)")
            self.status_timecode_badge.setText("00:00:00:00")
            return

        cached, cap, pct, mem_mb = self.core.cache_stats()
        fps = self.core.media_fps() or 24.0
        tc = self._format_timecode(self.current_index, fps)
        if mem_mb > 1024:
            mem_str = f"{mem_mb/1024:.1f}GB"
        else:
            mem_str = f"{mem_mb:.0f}MB"

        # Update State badge
        if self.playing:
            if getattr(self, 'play_direction', 1) == -1:
                self.status_state_badge.setText("◀ REVERSE")
                self.status_state_badge.setStyleSheet("""
                    background-color: rgba(10, 132, 255, 0.15);
                    border: 1px solid rgba(10, 132, 255, 0.35);
                    border-radius: 4px;
                    color: #0a84ff;
                    padding: 2px 7px;
                    font-size: 11px;
                    font-weight: 600;
                """)
            else:
                self.status_state_badge.setText("● PLAYING")
                self.status_state_badge.setStyleSheet("""
                    background-color: rgba(48, 209, 88, 0.15);
                    border: 1px solid rgba(48, 209, 88, 0.35);
                    border-radius: 4px;
                    color: #30d158;
                    padding: 2px 7px;
                    font-size: 11px;
                    font-weight: 600;
                """)
        else:
            self.status_state_badge.setText("⏸ PAUSED")
            self.status_state_badge.setStyleSheet("""
                background-color: rgba(255, 159, 10, 0.15);
                border: 1px solid rgba(255, 159, 10, 0.35);
                border-radius: 4px;
                color: #ff9f0a;
                padding: 2px 7px;
                font-size: 11px;
                font-weight: 600;
            """)

        # Resolution badge
        w, h = 0, 0
        if self.core.media.size:
            w, h = self.core.media.size
        if w > 0 and h > 0:
            self.status_res_badge.setText(f"{w}×{h}")
        else:
            self.status_res_badge.setText("Unknown Res")

        # Total Frames badge
        cnt = self.core.frame_count()
        missing = getattr(self.core.media, 'missing_frames', []) if self.core.media else []
        if missing:
            self.status_frames_badge.setText(f"{cnt} Frames (⚠️ {len(missing)} Missing)")
            self.status_frames_badge.setStyleSheet("""
                background-color: rgba(255, 69, 58, 0.15);
                border: 1px solid rgba(255, 69, 58, 0.4);
                border-radius: 4px;
                color: #ff453a;
                padding: 2px 7px;
                font-family: 'SF Mono', Consolas, monospace;
                font-size: 11px;
                font-weight: 600;
            """)
            missing_preview = ", ".join(str(m) for m in missing[:8])
            if len(missing) > 8:
                missing_preview += f" ... (+{len(missing)-8} more)"
            self.status_frames_badge.setToolTip(f"Missing Frames in Sequence: {missing_preview}")
        else:
            self.status_frames_badge.setText(f"{cnt} Frames")
            self.status_frames_badge.setStyleSheet(getattr(self, '_mono_badge_style', ''))
            self.status_frames_badge.setToolTip("Total Frames in Sequence")

        # FPS badge
        self.status_fps_badge.setText(f"{fps:.2f} fps")

        # Cache & Timecode badges
        self.status_cache_badge.setText(f"Cache: {cached}/{cap} ({pct:.0f}%) · {mem_str}")
        self.status_timecode_badge.setText(tc)

        # Update cached frame indicators on timeline
        if self.prefs.get('show_cached_timeline', True):
            self.frame_slider.set_cached_indices(self.core.get_cached_indices())

    def _format_timecode(self, frame: int, fps: float) -> str:
        if hasattr(self.core, 'media') and self.core.media and getattr(self.core.media, 'timeline', None):
            return self.core.media.timeline.format_timecode(frame)
        from core.timeline_service import frame_to_timecode
        return frame_to_timecode(frame, fps)

    # ---------- Cache capacity controls ----------
    def refresh_timeline_cache(self):
        """Refresh / flush and reload the timeline cache immediately (Shortcut: C)."""
        if not self.core or not self.core.media:
            self.statusBar().showMessage("No media loaded to refresh cache", 2000)
            return

        # Clear memory frame cache and loader queues
        self.core.clear_cache()

        # Reset timeline cache indicator
        if hasattr(self, 'frame_slider'):
            self.frame_slider.set_cached_indices(set())
            self.frame_slider.update()

        # Force reload current frame and burst prefetch around playhead
        self.seek(self.current_index)
        direction = 1 if getattr(self, 'playback_direction', 1) >= 0 else -1
        self.core.burst_prefetch(self.current_index, count=getattr(self, 'prefetch_count', 48), direction=direction)

        self.statusBar().showMessage("Timeline cache refreshed (C)", 3000)

    def _set_cache_capacity_dialog(self):
        try:
            current = int(getattr(getattr(self.core, 'cache', None), 'capacity', 200))
        except Exception:
            current = 200
        val, ok = QtWidgets.QInputDialog.getInt(
            self,
            "Set Cache Size",
            "Cache capacity (frames):",
            current,
            0,
            100000,
            1,
        )
        if ok:
            self._apply_cache_capacity(int(val))

    def _apply_cache_capacity(self, capacity: int):
        capacity = max(0, int(capacity))
        # Primary core
        if hasattr(self.core, 'set_cache_capacity'):
            self.core.set_cache_capacity(capacity)
        elif hasattr(self.core, 'cache') and hasattr(self.core.cache, '_cache'):
            self.core.cache.capacity = capacity
            # Evict down immediately
            while len(self.core.cache._cache) > capacity:
                try:
                    self.core.cache._cache.popitem(last=False)
                except Exception:
                    break
        # Compare core
        if hasattr(self, 'core_b') and self.core_b:
            if hasattr(self.core_b, 'set_cache_capacity'):
                self.core_b.set_cache_capacity(capacity)
            elif hasattr(self.core_b, 'cache') and hasattr(self.core_b.cache, '_cache'):
                self.core_b.cache.capacity = capacity
                while len(self.core_b.cache._cache) > capacity:
                    try:
                        self.core_b.cache._cache.popitem(last=False)
                    except Exception:
                        break
        # Update status immediately
        self._update_status(self._status_base)

    def _open_file(self):
        media_filter = (
            "All Supported Media (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.mov *.mp4 *.avi *.mkv *.mxf *.webm);;"
            "Image Sequences (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.tga *.bmp *.webp);;"
            "Video Files (*.mov *.mp4 *.avi *.mkv *.mxf *.webm *.m4v *.flv *.ts);;"
            "All Files (*.*)"
        )
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Media", "", media_filter)
        if path:
            self.load_media(path)

    def _open_file_compare(self):
        media_filter = (
            "All Supported Media (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.mov *.mp4 *.avi *.mkv *.mxf *.webm);;"
            "Image Sequences (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.tga *.bmp *.webp);;"
            "Video Files (*.mov *.mp4 *.avi *.mkv *.mxf *.webm *.m4v *.flv *.ts);;"
            "All Files (*.*)"
        )
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Compare Media", "", media_filter)
        if path:
            self.load_compare_media(path)

    def load_compare_media(self, path: str):
        try:
            self.core_b.load(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Compare Load Error", str(e))
            return
        self.compare_loaded = True
        # Ensure side-by-side is visible when loading compare
        if not (self.side_by_side or self.wipe_mode):
            self._set_compare_mode('side')
        if self.side_by_side or self.wipe_mode:
            self._show_frame(self.current_index)
        self._status_base = f"Loaded A: {self.core.media.path if self.core.media else ''} | B: {path}"
        self._update_status(self._status_base)

    def _configure_frame_slider_ticks(self):
        """Adjust tick interval to keep grid readable for large frame counts."""
        fc = self.core.frame_count()
        if fc <= 0:
            return
        max_ticks = 120  # target maximum visible tick marks
        interval = max(1, int(fc / max_ticks))
        self.frame_slider.setTickInterval(interval)
        self.frame_slider.setPageStep(max(1, interval))
        # Ensure tick position is set (idempotent)
        self.frame_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)

    def _set_compare_mode(self, mode: str):
        # Toggle logic: if requesting the same mode that is currently active, switch to single
        if mode == 'side' and getattr(self, 'grid_mode', 'single') == 'side':
            mode = 'single'
        elif mode == 'wipe' and self.wipe_mode:
            mode = 'single'
            
        self.wipe_mode = False
        if mode == 'single':
            self.side_action.setChecked(False)
            self.wipe_action.setChecked(False)
            self._wipe_row.hide()
            self._set_grid_layout('single')
        elif mode == 'side':
            self.side_action.setChecked(True)
            self.wipe_action.setChecked(False)
            self._wipe_row.hide()
            self._set_grid_layout('side')
        elif mode == 'wipe':
            self.wipe_action.setChecked(True)
            self.side_action.setChecked(False)
            self.wipe_mode = True
            self._wipe_row.show()
            self._set_grid_layout('single')
        self._update_wipe()

    def _update_wipe(self):
        if not self.wipe_mode:
            return
        ratio = self.wipe_slider.value() / 1000.0
        if self.compare_loaded and self.core_b.frame_count() > 0:
            base_raw = self.core.get_frame(self.current_index)
            idx_b = max(0, min(self.core_b.frame_count()-1, self.current_index + int(getattr(self, 'compare_offset', 0))))
            top_raw = self.core_b.get_frame(idx_b)
            
            if base_raw is not None and top_raw is not None:
                self.viewport.composite_wipe(base_raw, top_raw, ratio)
                self.viewport.set_exposure(self.exposure)
                self.viewport.set_gamma(self.gamma)
                self.viewport.set_channel_mode(self.channel_mode)

    # ---------- Folder Navigation (Page Up / Page Down) ----------
    _MEDIA_EXTS = {
        '.mov', '.mp4', '.avi', '.mkv', '.mxf', '.webm', '.m4v', '.flv', '.ts',
        '.exr', '.sxr', '.tif', '.tiff', '.dpx', '.cin', '.png', '.jpg', '.jpeg', '.tga', '.bmp', '.webp'
    }

    def _navigate_folder(self, direction: int):
        """Load next (+1) or previous (-1) media file in the same folder."""
        if not self.core.media:
            return

        current_path = self.core.media.path
        # For sequences, media.path is the folder; for video, it's the file
        if self.core.media.type == 'sequence':
            folder = current_path
            # Use the first file in the sequence as reference
            if self.core.sequence:
                current_file = self.core.sequence[0]
            else:
                return
        else:
            folder = os.path.dirname(current_path)
            current_file = current_path

        # Scan folder for supported media
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            return

        image_exts = {'.exr', '.sxr', '.tif', '.tiff', '.dpx', '.cin', '.png', '.jpg', '.jpeg', '.tga', '.bmp', '.webp'}
        media_files = []
        seen_seq = set()  # track sequence base names to avoid duplicates
        for name in entries:
            ext = os.path.splitext(name)[1].lower()
            if ext not in self._MEDIA_EXTS:
                continue
            full = os.path.join(folder, name)
            if ext in image_exts:
                # Group image sequences: only add the first file per sequence
                # Strip frame numbers to get base name
                import re
                base = re.sub(r'[\._]\d{3,}(?=\.[^.]+$)', '', name, flags=re.IGNORECASE)
                if base not in seen_seq:
                    seen_seq.add(base)
                    media_files.append(full)
            else:
                media_files.append(full)

        if not media_files:
            return

        # Find current position
        current_idx = -1
        for i, f in enumerate(media_files):
            if os.path.normcase(f) == os.path.normcase(current_file):
                current_idx = i
                break
            # For sequences, check if current folder matches
            if self.core.media.type == 'sequence' and os.path.normcase(os.path.dirname(f)) == os.path.normcase(folder) and os.path.splitext(f)[1].lower() in image_exts:
                current_idx = i
                break

        if current_idx < 0:
            current_idx = 0

        new_idx = current_idx + direction
        if new_idx < 0:
            new_idx = len(media_files) - 1  # Wrap to end
        elif new_idx >= len(media_files):
            new_idx = 0  # Wrap to start

        target = media_files[new_idx]
        if os.path.normcase(target) != os.path.normcase(current_file):
            self.pause()
            self.load_media(target)
            self.play()  # Auto-play on navigation

    def _wire_annotation_toolbar(self):
        """Connect annotation toolbar signals. Called after toolbar is created."""
        tb = self.annotation_toolbar
        tb.tool_changed.connect(self._on_annotation_tool_changed)
        tb.color_changed.connect(self._on_annotation_color_changed)
        tb.width_changed.connect(self._on_annotation_width_changed)
        tb.undo_requested.connect(self._annotation_undo)
        tb.redo_requested.connect(self._annotation_redo)
        tb.clear_frame_requested.connect(self._clear_annotations)
        tb.clear_all_requested.connect(self._clear_all_annotations)
        # Note: viewport.stroke_finished is already connected in __init__


    # ---------- Keyboard Shortcuts ----------
    def keyPressEvent(self, event: QtGui.QKeyEvent):  # type: ignore[override]
        # Ignore main window keyboard shortcuts if focus is inside any text input widget
        focus_widget = QtWidgets.QApplication.focusWidget()
        if focus_widget and isinstance(focus_widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()

        # F1 — Open Keyboard Shortcuts & Hotkey Reference
        if key == QtCore.Qt.Key.Key_F1:
            self._show_shortcuts_dialog()
            event.accept()
            return

        # Annotation mode shortcuts: N or Alt+A
        if key == QtCore.Qt.Key.Key_N or (key == QtCore.Qt.Key.Key_A and bool(mods & QtCore.Qt.KeyboardModifier.AltModifier)):
            self._toggle_annotate_mode()
            event.accept()
            return

        # Ctrl+Shift+E — Export all annotated frames
        if key == QtCore.Qt.Key.Key_E and (mods & QtCore.Qt.KeyboardModifier.ControlModifier) and (mods & QtCore.Qt.KeyboardModifier.ShiftModifier):
            self._export_all_annotated_frames()
            event.accept()
            return

        # Ctrl+Z — annotation undo
        if key == QtCore.Qt.Key.Key_Z and (mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            if mods & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._annotation_redo()
            else:
                self._annotation_undo()
            event.accept()
            return

        # Playlist and Studio Shortcuts
        if key == QtCore.Qt.Key.Key_PageUp:
            self.playlist_prev_shot()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_PageDown:
            self.playlist_next_shot()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_L and bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            self._toggle_playlist_panel()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_K and bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            self._open_current_shot_in_kitsu()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_P and bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier) and bool(mods & QtCore.Qt.KeyboardModifier.AltModifier):
            self._on_publish_kitsu_review()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_F and bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier) and bool(mods & QtCore.Qt.KeyboardModifier.AltModifier):
            if hasattr(self, 'false_color_action'):
                self.false_color_action.trigger()
            event.accept()
            return

        if key == QtCore.Qt.Key.Key_Escape:
            if getattr(self, 'fullscreen', False):
                self._toggle_fullscreen(False)
            elif getattr(self.viewport, 'is_drawing', False):
                self._toggle_annotate_mode()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_Tab:
            self._toggle_ab_compare()
            event.accept()
            return
        elif key == QtCore.Qt.Key.Key_Space:
            self.pause() if self.playing else self.play()
        elif key == QtCore.Qt.Key.Key_C:
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._set_view_preset('minimal' if not self.cinema_mode_enabled else 'normal')
            elif event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier:
                self.refresh_timeline_cache()
            event.accept()
            return
        elif key in (QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_AltGr):
            if self.menuBar().isHidden():
                self.menuBar().show()
            else:
                if getattr(self, 'cinema_mode_enabled', True) and not getattr(self, '_ui_visible', True):
                    self.menuBar().hide()
        elif key == QtCore.Qt.Key.Key_1 and not (event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            self._set_view_preset('minimal')
        elif key == QtCore.Qt.Key.Key_2 and not (event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            self._set_view_preset('normal')
        elif key == QtCore.Qt.Key.Key_3 and not (event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            self._toggle_fullscreen(not self.fullscreen)
        elif key == QtCore.Qt.Key.Key_R:
            self._set_channel('R')
        elif key == QtCore.Qt.Key.Key_G:
            self._set_channel('G')
        elif key == QtCore.Qt.Key.Key_B:
            if (mods & QtCore.Qt.KeyboardModifier.AltModifier):
                self._toggle_slot_badges()
            elif mods & QtCore.Qt.KeyboardModifier.ControlModifier:
                self._set_channel('B')
            else:
                self._toggle_bookmark()
        elif key == QtCore.Qt.Key.Key_A:
            if mods & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._cycle_alpha_mode()
            else:
                self._set_channel('A')
        elif key == QtCore.Qt.Key.Key_S:
            # Toggle Side-by-Side on/off
            if self.side_by_side and not self.wipe_mode:
                self._set_compare_mode('single')
            else:
                self._set_compare_mode('side')
        elif key == QtCore.Qt.Key.Key_W:
            # Toggle Wipe on/off
            if self.wipe_mode:
                self._set_compare_mode('single')
            else:
                self._set_compare_mode('wipe')
        elif key == QtCore.Qt.Key.Key_I:
            if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
                self._toggle_properties_hud()
            else:
                self._set_in_point()
        elif key == QtCore.Qt.Key.Key_O:
            if (mods & QtCore.Qt.KeyboardModifier.ControlModifier) or (mods & QtCore.Qt.KeyboardModifier.AltModifier):
                if hasattr(self, 'ocio_enable_btn'):
                    self.ocio_enable_btn.toggle()
            else:
                self._set_out_point()
        elif key == QtCore.Qt.Key.Key_X:
            self._clear_in_out_range()
        elif key == QtCore.Qt.Key.Key_H and (mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            self._toggle_scopes()
        elif key == QtCore.Qt.Key.Key_Up and (mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            if mods & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._version_latest()
            else:
                self._version_up()
        elif key == QtCore.Qt.Key.Key_Down and (mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            self._version_down()
        elif key == QtCore.Qt.Key.Key_E:
            # Cycle Playback Strategy
            current = self.core.strategy
            all_strats = list(PlaybackStrategy)
            idx = all_strats.index(current)
            next_strat = all_strats[(idx + 1) % len(all_strats)]
            self._set_playback_strategy(next_strat)
        elif key == QtCore.Qt.Key.Key_M:
            self._toggle_mute()
        elif key == QtCore.Qt.Key.Key_Right:
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._jump_to_next_annotated_frame()
            else:
                self.seek(self.current_index + 1)
        elif key == QtCore.Qt.Key.Key_Left:
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._jump_to_prev_annotated_frame()
            else:
                self.seek(self.current_index - 1)
        elif key == QtCore.Qt.Key.Key_Home:
            self.seek(0)
        elif key == QtCore.Qt.Key.Key_End:
            self.seek(self.core.frame_count() - 1)
        
        # --- Playback Navigation (JKL) ---
        elif key == QtCore.Qt.Key.Key_L:
            if not self.playing or getattr(self, 'play_direction', 1) != 1:
                self.play_direction = 1
                self._on_speed_changed(1.0)
                self.play(direction=1)
            else:
                # Cycle forward speeds
                fwd_speeds = [1.0, 1.5, 2.0, 4.0]
                try:
                    idx = fwd_speeds.index(self.playback_speed)
                    next_s = fwd_speeds[(idx + 1) % len(fwd_speeds)]
                except ValueError:
                    next_s = 1.0
                self._on_speed_changed(next_s)
        elif key == QtCore.Qt.Key.Key_K:
            self.pause()
        elif key == QtCore.Qt.Key.Key_J:
            self.play_reverse()
        
        # --- Speed Presets (Alt + 0/1/2/3) ---
        elif event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            if key == QtCore.Qt.Key.Key_1:
                self._on_speed_changed(1.0)
            elif key == QtCore.Qt.Key.Key_2:
                self._on_speed_changed(2.0)
            elif key == QtCore.Qt.Key.Key_3:
                self._on_speed_changed(4.0)
            elif key == QtCore.Qt.Key.Key_0:
                self._on_speed_changed(0.5)

        # --- Gamma Shortcuts ([ / ]) ---
        elif key == QtCore.Qt.Key.Key_BracketLeft:
            self.gam_slider.setValue(self.gam_slider.value() - 100)
        elif key == QtCore.Qt.Key.Key_BracketRight:
            self.gam_slider.setValue(self.gam_slider.value() + 100)
            
        # --- Exposure Shortcuts (- / =) ---
        elif key == QtCore.Qt.Key.Key_Minus and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.exp_slider.setValue(self.exp_slider.value() - 250)
        elif key in (QtCore.Qt.Key.Key_Equal, QtCore.Qt.Key.Key_Plus) and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.exp_slider.setValue(self.exp_slider.value() + 250)

        # --- Zoom Shortcuts (Ctrl + / -, / or \ to reset) ---
        elif key in (QtCore.Qt.Key.Key_Slash, QtCore.Qt.Key.Key_Backslash):
            self.viewport.fit_to_window()
            if hasattr(self, 'viewport_b') and self.viewport_b:
                self.viewport_b.fit_to_window()
            self._update_zoom_label()
            event.accept()
            return
        elif key in (QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Equal) and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            curr = getattr(self.viewport, 'current_zoom', getattr(self.viewport, '_zoom', 1.0))
            self.viewport.set_zoom(curr * 1.2)
            self._update_zoom_label()
        elif key in (QtCore.Qt.Key.Key_Minus, QtCore.Qt.Key.Key_Underscore) and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            curr = getattr(self.viewport, 'current_zoom', getattr(self.viewport, '_zoom', 1.0))
            self.viewport.set_zoom(curr / 1.2)
            self._update_zoom_label()
        elif key == QtCore.Qt.Key.Key_F:
            # Fullscreen toggle via F; Shift+F for fit
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.viewport.fit_to_window()
                if hasattr(self, 'viewport_b') and self.viewport_b:
                    self.viewport_b.fit_to_window()
                self._update_zoom_label()
            else:
                self._toggle_fullscreen(not self.fullscreen)
        elif key == QtCore.Qt.Key.Key_U:
            # U key also toggles fullscreen
            self._toggle_fullscreen(not self.fullscreen)
        elif key == QtCore.Qt.Key.Key_PageDown:
            self._navigate_folder(1)   # Next media in folder
        elif key == QtCore.Qt.Key.Key_PageUp:
            self._navigate_folder(-1)  # Previous media in folder
        else:
            event.ignore()

    def _update_zoom_label(self):
        zoom_val = getattr(self.viewport, 'current_zoom', getattr(self.viewport, '_zoom', 1.0))
        zoom_pct = int(round(zoom_val * 100))
        self._update_status(f"Zoom: {zoom_pct}%")

    def _toggle_fullscreen(self, enable: bool):
        self.fullscreen = enable
        if enable:
            # Save UI state before hiding
            self._pre_fullscreen_state = {
                'menu_visible': self.menuBar().isVisible(),
                'status_visible': self.statusBar().isVisible(),
                'hud_visible': self.hud_container.isVisible(),
                'was_maximized': self.isMaximized()
            }
            self.menuBar().hide()
            self.statusBar().hide()
            self.hud_container.hide()
            if hasattr(self, '_wipe_row') and self._wipe_row.isVisible():
                self._pre_fullscreen_state['wipe_visible'] = True
                self._wipe_row.hide()
            self.showFullScreen()
        else:
            state = getattr(self, '_pre_fullscreen_state', {})
            if state.get('was_maximized', False):
                self.showMaximized()
            else:
                self.showNormal()
                
            if state.get('menu_visible', True):
                self.menuBar().show()
            if state.get('status_visible', True):
                self.statusBar().show()
            if state.get('hud_visible', True):
                self.hud_container.show()
            if state.get('wipe_visible', False) and hasattr(self, '_wipe_row'):
                self._wipe_row.show()
            
            # Restore viewport visualization after window resize
            # We use a short delay (50ms) to ensure OS window transitions and layout are stable.
            def _refresh():
                # Force layout engine to update
                self.centralWidget().updateGeometry()
                if self.centralWidget().layout():
                    self.centralWidget().layout().activate()
                
                # Re-push frame & reset camera
                self._force_fit_next_frame = True
                self._show_frame(self.current_index)
                self.viewport.fit_to_window()
                self.viewport.canvas.update()
                
                if self.side_by_side and hasattr(self, 'viewport_b') and self.viewport_b:
                    self.viewport_b.fit_to_window()
                    self.viewport_b.canvas.update()
            
            QtCore.QTimer.singleShot(50, _refresh)

    def _set_playback_strategy(self, strategy: PlaybackStrategy):
        self.core.set_strategy(strategy)
        if hasattr(self, 'core_b') and self.core_b:
            self.core_b.set_strategy(strategy)
        
        # Update UI checks
        for action in self.strategy_group.actions():
            if "Performance" in action.text() and strategy == PlaybackStrategy.PERFORMANCE: action.setChecked(True)
            elif "Progressive" in action.text() and strategy == PlaybackStrategy.PROGRESSIVE: action.setChecked(True)
            elif "Stream" in action.text() and strategy == PlaybackStrategy.STREAM: action.setChecked(True)
            elif "Read-behind" in action.text() and strategy == PlaybackStrategy.READ_BEHIND: action.setChecked(True)
            
        self._save_prefs()
        self._update_status(f"Strategy: {strategy.name}")

    def _toggle_economy_mode(self, checked):
        # Legacy support for old settings/buttons
        self._set_playback_strategy(PlaybackStrategy.STREAM if checked else PlaybackStrategy.PERFORMANCE)

    def _connect_camera_sync(self):
        if getattr(self, '_camera_sync_connected', False):
            return
        self._camera_sync_connected = True
        for vp in self.viewports:
            vp.view.camera.events.transform_change.connect(
                lambda event, source_vp=vp: self._on_viewport_view_changed(source_vp)
            )

    def showEvent(self, event):
        super().showEvent(event)
        set_dark_title_bar(self.winId())
        self._connect_camera_sync()
        self._show_frame(self.current_index)

    def closeEvent(self, event):
        self._save_prefs()
        super().closeEvent(event)

    def _toggle_safe_guides(self, checked):
        viewports = getattr(self, 'viewports', [getattr(self, 'viewport', None)])
        for vp in viewports:
            if vp:
                vp.set_guides_enabled(checked)
        if hasattr(self, 'guides_toggle_action'):
            self.guides_toggle_action.blockSignals(True)
            self.guides_toggle_action.setChecked(checked)
            self.guides_toggle_action.blockSignals(False)
        self.statusBar().showMessage(f"Safe Guides: {'ON' if checked else 'OFF'}", 2000)

    def _update_guides_config(self):
        c = self.guide_center_action.isChecked()
        t = self.guide_thirds_action.isChecked()
        a = self.guide_action_action.isChecked()
        ti = self.guide_title_action.isChecked()
        viewports = getattr(self, 'viewports', [getattr(self, 'viewport', None)])
        for vp in viewports:
            if vp:
                vp.set_guides_config(c, t, a, ti)

    def _get_marked_frames(self) -> list[int]:
        active_annots = {k for k, v in self.annotations.items() if v}
        return sorted(list(active_annots | self.bookmarks))

    def _jump_to_next_annotated_frame(self):
        targets = self._get_marked_frames()
        if not targets:
            return
        next_frames = [idx for idx in targets if idx > self.current_index]
        if next_frames:
            self.seek(next_frames[0])
        else:
            self.seek(targets[0])

    def _jump_to_prev_annotated_frame(self):
        targets = self._get_marked_frames()
        if not targets:
            return
        prev_frames = [idx for idx in targets if idx < self.current_index]
        if prev_frames:
            self.seek(prev_frames[-1])
        else:
            self.seek(targets[-1])

    def _export_contact_sheet(self):
        import time
        if not self.core.frame_count():
            QtWidgets.QMessageBox.warning(self, "No Media", "No media loaded.")
            return

        annotated_indices = sorted([idx for idx, strokes in self.annotations.items() if strokes])
        if not annotated_indices:
            QtWidgets.QMessageBox.information(
                self, "No Annotations",
                "There are no annotated frames in the current clip to build a contact sheet.\n"
                "Draw annotations on frames before exporting."
            )
            return

        html_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save HTML Contact Sheet", "contact_sheet.html", "HTML Files (*.html)"
        )
        if not html_path:
            return

        html_dir = os.path.dirname(html_path)
        html_base = os.path.splitext(os.path.basename(html_path))[0]
        images_dir_name = f"{html_base}_images"
        images_dir_path = os.path.join(html_dir, images_dir_name)
        os.makedirs(images_dir_path, exist_ok=True)

        progress = QtWidgets.QProgressDialog(
            "Generating Contact Sheet...", "Cancel", 0, len(annotated_indices), self
        )
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        orig_idx = self.current_index
        was_playing = self.playing
        if was_playing:
            self.pause()

        items_html = []
        try:
            for i, frame_idx in enumerate(annotated_indices):
                if progress.wasCanceled():
                    break
                progress.setValue(i)
                progress.setLabelText(f"Baking frame {frame_idx + 1} ({i + 1}/{len(annotated_indices)})...")
                QtWidgets.QApplication.processEvents()

                self.seek(frame_idx)
                QtWidgets.QApplication.processEvents()
                time.sleep(0.05) 

                arr = self.viewport.get_frame_with_annotations()
                if arr is not None:
                    h, w = arr.shape[:2]
                    c = arr.shape[2] if len(arr.shape) > 2 else 3
                    fmt = QtGui.QImage.Format.Format_RGB888 if c == 3 else QtGui.QImage.Format.Format_RGBA8888
                    image = QtGui.QImage(arr.tobytes(), w, h, w * c, fmt)
                    image_filename = f"frame_{frame_idx + 1:04d}.png"
                    image_path = os.path.join(images_dir_path, image_filename)
                    image.save(image_path)

                    comments = []
                    strokes = self.annotations.get(frame_idx, [])
                    for s in strokes:
                        if s.get('tool') == 'text' and s.get('text'):
                            comments.append(s.get('text'))
                    
                    comments_str = "<br>".join(comments) if comments else "<i>No text notes</i>"

                    relative_img_path = f"{images_dir_name}/{image_filename}"
                    item_markup = f"""
                    <div class="card">
                        <div class="card-header">Frame {frame_idx + 1}</div>
                        <a href="{relative_img_path}" target="_blank">
                            <img src="{relative_img_path}" class="card-img" />
                        </a>
                        <div class="card-body">
                            <strong>Notes:</strong>
                            <p>{comments_str}</p>
                        </div>
                    </div>
                    """
                    items_html.append(item_markup)

            progress.setValue(len(annotated_indices))
        finally:
            self.seek(orig_idx)
            if was_playing:
                self.play()

        media_name = os.path.basename(self.core.media.path) if self.core.media else "VFX Sequence"
        metadata_lines = []
        if self.core.media:
            metadata_lines.append(f"<li><strong>Resolution:</strong> {self.core.media.size[0]}x{self.core.media.size[1]}</li>")
            metadata_lines.append(f"<li><strong>FPS:</strong> {self.core.media.fps:.3f}</li>")
            metadata_lines.append(f"<li><strong>Path:</strong> {self.core.media.path}</li>")

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>VFX Review Contact Sheet - {media_name}</title>
    <style>
        body {{
            background-color: #121214;
            color: #e0e0e4;
            font-family: 'Segoe UI', sans-serif;
            margin: 20px;
        }}
        h1 {{
            color: #0a84ff;
            border-bottom: 2px solid #2a2a2e;
            padding-bottom: 10px;
        }}
        .meta-box {{
            background-color: #1c1c1e;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #2a2a2e;
            margin-bottom: 25px;
        }}
        .meta-box ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 20px;
        }}
        .card {{
            background-color: #1c1c1e;
            border: 1px solid #2a2a2e;
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .card-header {{
            background-color: #242427;
            padding: 8px 12px;
            font-weight: bold;
            font-size: 14px;
            border-bottom: 1px solid #2a2a2e;
            color: #0a84ff;
        }}
        .card-img {{
            width: 100%;
            display: block;
            border-bottom: 1px solid #2a2a2e;
            transition: opacity 0.2s;
        }}
        .card-img:hover {{
            opacity: 0.85;
        }}
        .card-body {{
            padding: 12px;
            font-size: 13px;
        }}
        .card-body strong {{
            color: #aaaaaf;
            display: block;
            margin-bottom: 4px;
        }}
        .card-body p {{
            margin: 0;
            color: #dddddf;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
    <h1>VFX Review Contact Sheet</h1>
    <div class="meta-box">
        <h3>Media Information</h3>
        <ul>
            <li><strong>Media:</strong> {media_name}</li>
            {"".join(metadata_lines)}
            <li><strong>Generated:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</li>
        </ul>
    </div>
    <div class="grid">
        {"".join(items_html)}
    </div>
</body>
</html>
"""
        try:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle("Contact Sheet Generated")
            msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            msg_box.setText(f"HTML Contact Sheet generated successfully at:\n{html_path}")
            open_btn = msg_box.addButton("Open Contact Sheet", QtWidgets.QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton(QtWidgets.QMessageBox.StandardButton.Ok)
            msg_box.exec()
            if msg_box.clickedButton() == open_btn:
                try:
                    os.startfile(html_path)
                except Exception as e:
                    print(f"Could not open HTML contact sheet: {e}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export Error", f"Failed to save contact sheet HTML: {e}")

    def _toggle_ab_compare(self):
        if not self.compare_loaded:
            return
        self.show_compare_b = not getattr(self, 'show_compare_b', False)
        active_ver = "B" if self.show_compare_b else "A"
        self.status.showMessage(f"A/B Compare: Viewing Version {active_ver}", 2000)
        self._show_frame(self.current_index)

    def _on_viewport_view_changed(self, source_vp):
        if getattr(self, '_syncing_cameras', False):
            return
        self._syncing_cameras = True
        try:
            rect = source_vp.view.camera.rect
            for vp in self.viewports:
                if vp != source_vp and vp.isVisible():
                    vp.view.camera.rect = rect
        finally:
            self._syncing_cameras = False

    def _set_grid_layout(self, mode: str):
        self.grid_mode = mode
        
        # Hide all viewports and remove from layout
        for vp in self.viewports:
            self.grid_layout.removeWidget(vp)
            vp.hide()
            vp.set_slot_badge(False)
            
        if mode == 'single':
            self.grid_layout.addWidget(self.viewport, 0, 0)
            self.viewport.show()
            self.side_by_side = False
        elif mode == 'side':
            self.grid_layout.addWidget(self.viewport, 0, 0)
            self.grid_layout.addWidget(self.viewport_b, 0, 1)
            self.viewport.show()
            self.viewport_b.show()
            self.viewport.set_slot_badge(self.show_slot_badges, "Slot 1 (Left)")
            self.viewport_b.set_slot_badge(self.show_slot_badges, "Slot 2 (Right)")
            self.side_by_side = True
        elif mode == 'grid4':
            slot_names = ["Slot 1 (Top-Left)", "Slot 2 (Top-Right)", "Slot 3 (Bottom-Left)", "Slot 4 (Bottom-Right)"]
            for i, vp in enumerate(self.viewports[:4]):
                row = i // 2
                col = i % 2
                self.grid_layout.addWidget(vp, row, col)
                vp.show()
                vp.set_slot_badge(self.show_slot_badges, slot_names[i])
            self.side_by_side = True
        elif mode == 'grid6':
            for i, vp in enumerate(self.viewports[:6]):
                row = i // 3
                col = i % 3
                self.grid_layout.addWidget(vp, row, col)
                vp.show()
                vp.set_slot_badge(self.show_slot_badges, f"Slot {i + 1}")
            self.side_by_side = True
                
        # Force frame display refresh only if window is visible
        if self.isVisible():
            self._show_frame(self.current_index)

    def _toggle_slot_badges(self, visible: Optional[bool] = None):
        """Toggle slot name/index badges on viewports in grid layout."""
        if visible is None:
            self.show_slot_badges = not getattr(self, 'show_slot_badges', True)
        else:
            self.show_slot_badges = bool(visible)

        if hasattr(self, 'show_slot_badges_action'):
            self.show_slot_badges_action.blockSignals(True)
            self.show_slot_badges_action.setChecked(self.show_slot_badges)
            self.show_slot_badges_action.blockSignals(False)

        # Update visibility on all viewports
        for vp in getattr(self, 'viewports', []):
            if hasattr(vp, 'slot_badge'):
                if getattr(self, 'grid_mode', 'single') == 'single':
                    vp.slot_badge.setVisible(False)
                else:
                    vp.slot_badge.setVisible(self.show_slot_badges and vp.isVisible())
                    if self.show_slot_badges and vp.isVisible():
                        vp.slot_badge.adjustSize()
                        vp.slot_badge.raise_()

        self._status_base = f"Slot Badges: {'Shown' if self.show_slot_badges else 'Hidden'}"
        self._update_status(self._status_base)
        self._save_prefs()

    def _load_media_slot(self, slot_idx: int):
        media_filter = (
            "All Supported Media (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.mov *.mp4 *.avi *.mkv *.mxf *.webm);;"
            "Image Sequences (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.tga *.bmp *.webp);;"
            "Video Files (*.mov *.mp4 *.avi *.mkv *.mxf *.webm *.m4v *.flv *.ts);;"
            "All Files (*.*)"
        )
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, f"Load Slot {slot_idx + 1} Media", "", media_filter)
        if not path:
            return
        self.load_media_into_slot(slot_idx, path, autoplay=True)

    def load_media_into_slot(self, slot_idx: int, path: str, shot_title: str = None, autoplay: bool = True):
        """
        Loads a video file or image sequence directly into a specific layout slot (0-5).
        Enables multi-viewport drag-and-drop targeting any tile in single, 2-up, 4-up, or 6-up grids.
        """
        if slot_idx == 0:
            self.load_media(path)
            if autoplay and not self.playing:
                self.play()
            return

        if not (0 <= slot_idx < len(self.cores)):
            return

        # Auto-switch layout to reveal the slot if currently in single view
        if getattr(self, 'grid_mode', 'single') == 'single':
            if slot_idx == 1:
                self._set_grid_layout('side')
            elif slot_idx in (2, 3):
                self._set_grid_layout('grid4')
            elif slot_idx in (4, 5):
                self._set_grid_layout('grid6')
        elif getattr(self, 'grid_mode', 'single') == 'side' and slot_idx >= 2:
            if slot_idx in (2, 3):
                self._set_grid_layout('grid4')
            else:
                self._set_grid_layout('grid6')
        elif getattr(self, 'grid_mode', 'single') == 'grid4' and slot_idx >= 4:
            self._set_grid_layout('grid6')

        core = self.cores[slot_idx]
        try:
            core.load(path)
            # Sync OCIO
            if hasattr(self, 'color_manager') and self.color_manager.ocio_enabled:
                core.loader.set_ocio_params(
                    self.color_manager.ocio_enabled,
                    self.color_manager.input_cs,
                    self.color_manager.get_resolved_output_cs(),
                    self.color_manager.config_path
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", f"Failed to load slot {slot_idx + 1}: {e}")
            return
            
        if slot_idx == 1:
            self.compare_loaded = True

        # Ensure viewport is visible
        if slot_idx < len(self.viewports):
            vp = self.viewports[slot_idx]
            vp.show()
            name_display = shot_title or os.path.basename(path)
            vp.set_slot_badge(self.show_slot_badges, f"Slot {slot_idx + 1}: {name_display}")

        # Burst prefetch around playhead for this slot
        direction = 1 if getattr(self, 'play_direction', 1) >= 0 else -1
        if hasattr(core, 'burst_prefetch'):
            core.burst_prefetch(self.current_index, count=48, direction=direction)

        # Show frame
        self._show_frame(self.current_index)

        # Drag-and-play: start synchronized playback if autoplay requested or already playing
        if autoplay or self.playing:
            self.play(direction=direction, force_restart=False)

        name_display = shot_title or os.path.basename(path)
        self.status.showMessage(f"Loaded & Playing in Slot {slot_idx + 1}: {name_display}", 3000)

    def handle_shot_dropped_on_slot(self, slot_idx: int, shot_data: dict):
        """Handle clip dropped directly onto a viewport tile from the Playlist / Shot Browser."""
        path = shot_data.get('media_path', '')
        preview_id = shot_data.get('kitsu_preview_id')
        name = shot_data.get('name') or shot_data.get('shot_name') or "Shot"

        # If media is not on disk yet (e.g. Kitsu preview), download/cache it
        if not path or not os.path.exists(path):
            if preview_id or (path and (path.startswith("http://") or path.startswith("https://"))):
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
                self.statusBar().showMessage(f"Downloading preview for {name} from Kitsu...", 5000)
                try:
                    from core.kitsu_service import kitsu_client
                    cached_file = kitsu_client.download_preview_file(
                        preview_file_id=preview_id,
                        media_url=path if path and path.startswith("http") else None
                    )
                    if cached_file and os.path.exists(cached_file):
                        path = cached_file
                except Exception as e:
                    print(f"[Kitsu Drop] Failed to download preview: {e}")
                finally:
                    QtWidgets.QApplication.restoreOverrideCursor()

        if path and os.path.exists(path):
            self.load_media_into_slot(slot_idx, path, shot_title=name, autoplay=True)
        else:
            QtWidgets.QMessageBox.warning(
                self, "Media File Missing",
                f"Could not load shot for Slot {slot_idx + 1}:\n{path or name}"
            )

    def _on_playlist_send_to_slot(self, item, slot_idx: int):
        """Context menu callback to send a playlist shot to a specific grid slot."""
        if not item:
            return
        shot_data = {
            'media_path': getattr(item, 'media_path', ''),
            'kitsu_preview_id': getattr(item, 'kitsu_preview_id', None),
            'name': getattr(item, 'shot_name', '') or getattr(item, 'name', '') or "Shot"
        }
        self.handle_shot_dropped_on_slot(slot_idx, shot_data)

    def _toggle_grade_panel(self, checked=None):
        if checked is None:
            checked = not self.color_grading_panel.isVisible()
        self.color_grading_panel.setVisible(checked)
        if hasattr(self, 'grade_panel_action'):
            self.grade_panel_action.blockSignals(True)
            self.grade_panel_action.setChecked(checked)
            self.grade_panel_action.blockSignals(False)
        if hasattr(self, 'btn_grade'):
            self.btn_grade.blockSignals(True)
            self.btn_grade.setChecked(checked)
            self.btn_grade.blockSignals(False)

    def _build_color_grading_panel(self):
        self.color_grading_panel = QtWidgets.QFrame()
        self.color_grading_panel.setFixedWidth(280)
        self.color_grading_panel.setStyleSheet("""
            QFrame {
                background-color: #161618;
                border-left: 1px solid #2a2a2e;
                color: #c8c8cc;
            }
            QLabel {
                font-size: 11px;
                color: #8a8a8f;
                background: transparent;
                border: none;
            }
            QDoubleSpinBox {
                background-color: #242427;
                color: #e0e0e5;
                border: 1px solid #3c3c40;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 11px;
                min-height: 20px;
                max-height: 20px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #333336;
                height: 4px;
                background: #18181a;
                margin: 2px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #c8c8cc;
                border: 1px solid #5a5a5e;
                width: 8px;
                height: 10px;
                margin: -3px 0;
                border-radius: 1px;
            }
            QPushButton {
                background-color: #242427;
                color: #e0e0e5;
                border: 1px solid #3c3c40;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2c2c30;
                border-color: #0a84ff;
                color: #ffffff;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self.color_grading_panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Header Title + Close button
        hdr_box = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel("ASC CDL COLOR GRADE")
        title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #0a84ff; letter-spacing: 1px;")
        hdr_box.addWidget(title_lbl)
        hdr_box.addStretch()
        btn_close = QtWidgets.QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("padding: 0; font-size: 10px; background: transparent; border: none; color: #888;")
        btn_close.setToolTip("Close Grading Panel")
        btn_close.clicked.connect(lambda: self._toggle_grade_panel(False))
        hdr_box.addWidget(btn_close)
        layout.addLayout(hdr_box)

        # Scroll Area for controls
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_content = QtWidgets.QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        self.cdl_controls = {} # Store controls references

        # Helper to build a channel row (Label, Slider, Spinbox)
        def add_channel_row(parent_layout, label_text, key, min_val, max_val, default_val, section=None):
            row_layout = QtWidgets.QHBoxLayout()
            row_layout.setSpacing(6)

            lbl = QtWidgets.QLabel(label_text)
            lbl.setFixedWidth(15)
            # Custom coloring for R, G, B, S labels
            if label_text == "R": lbl.setStyleSheet("color: #ff453a; font-weight: bold;")
            elif label_text == "G": lbl.setStyleSheet("color: #34c759; font-weight: bold;")
            elif label_text == "B": lbl.setStyleSheet("color: #0a84ff; font-weight: bold;")
            elif label_text == "S": lbl.setStyleSheet("color: #ff9500; font-weight: bold;")

            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(min_val, max_val)
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
            spin.setValue(default_val)
            spin.setFixedWidth(62)

            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setRange(int(min_val * 1000), int(max_val * 1000))
            slider.setValue(int(default_val * 1000))

            # Sync slider and spinbox
            def on_spin_val(val):
                slider.blockSignals(True)
                slider.setValue(int(val * 1000))
                slider.blockSignals(False)
                if section:
                    self._sync_wheel_from_controls(section)
                self._on_cdl_changed()

            def on_slider_val(val):
                spin.blockSignals(True)
                spin.setValue(val / 1000.0)
                spin.blockSignals(False)
                if section:
                    self._sync_wheel_from_controls(section)
                self._on_cdl_changed()

            spin.valueChanged.connect(on_spin_val)
            slider.valueChanged.connect(on_slider_val)

            row_layout.addWidget(lbl)
            row_layout.addWidget(slider)
            row_layout.addWidget(spin)
            parent_layout.addLayout(row_layout)

            self.cdl_controls[key] = (slider, spin, default_val)

        # Helper to build a CDL section header
        def add_section_header(parent_layout, title, reset_slot):
            hdr_layout = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(title)
            lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #ffffff;")
            btn_reset = QtWidgets.QPushButton("Reset")
            btn_reset.setFixedWidth(45)
            btn_reset.setStyleSheet("padding: 1px 4px; font-size: 9px; min-height: 16px; max-height: 16px;")
            btn_reset.clicked.connect(reset_slot)
            hdr_layout.addWidget(lbl)
            hdr_layout.addStretch(1)
            hdr_layout.addWidget(btn_reset)
            parent_layout.addLayout(hdr_layout)

        # --- SLOPE (GAIN) ---
        add_section_header(scroll_layout, "Slope (Gain)", self._reset_slope)
        slope_wheel_box = QtWidgets.QHBoxLayout()
        slope_wheel_box.setContentsMargins(0, 2, 0, 4)
        slope_wheel_box.addStretch()
        self.wheel_slope = ColorWheelWidget(wheel_radius=40)
        self.wheel_slope.setToolTip("Slope / Gain Balance: Tint highlights [Shift=Fine, 2xClick=Center]")
        self.wheel_slope.balance_changed.connect(lambda x, y: self._on_wheel_balance_changed("slope", x, y))
        slope_wheel_box.addWidget(self.wheel_slope)
        slope_wheel_box.addStretch()
        scroll_layout.addLayout(slope_wheel_box)

        add_channel_row(scroll_layout, "R", "slope_r", 0.0, 4.0, 1.0, section="slope")
        add_channel_row(scroll_layout, "G", "slope_g", 0.0, 4.0, 1.0, section="slope")
        add_channel_row(scroll_layout, "B", "slope_b", 0.0, 4.0, 1.0, section="slope")
        scroll_layout.addSpacing(6)

        # --- OFFSET (LIFT) ---
        add_section_header(scroll_layout, "Offset (Lift)", self._reset_offset)
        offset_wheel_box = QtWidgets.QHBoxLayout()
        offset_wheel_box.setContentsMargins(0, 2, 0, 4)
        offset_wheel_box.addStretch()
        self.wheel_offset = ColorWheelWidget(wheel_radius=40)
        self.wheel_offset.setToolTip("Offset / Lift Balance: Tint shadows [Shift=Fine, 2xClick=Center]")
        self.wheel_offset.balance_changed.connect(lambda x, y: self._on_wheel_balance_changed("offset", x, y))
        offset_wheel_box.addWidget(self.wheel_offset)
        offset_wheel_box.addStretch()
        scroll_layout.addLayout(offset_wheel_box)

        add_channel_row(scroll_layout, "R", "offset_r", -1.0, 1.0, 0.0, section="offset")
        add_channel_row(scroll_layout, "G", "offset_g", -1.0, 1.0, 0.0, section="offset")
        add_channel_row(scroll_layout, "B", "offset_b", -1.0, 1.0, 0.0, section="offset")
        scroll_layout.addSpacing(6)

        # --- POWER (GAMMA) ---
        add_section_header(scroll_layout, "Power (Gamma)", self._reset_power)
        power_wheel_box = QtWidgets.QHBoxLayout()
        power_wheel_box.setContentsMargins(0, 2, 0, 4)
        power_wheel_box.addStretch()
        self.wheel_power = ColorWheelWidget(wheel_radius=40)
        self.wheel_power.setToolTip("Power / Gamma Balance: Tint midtones [Shift=Fine, 2xClick=Center]")
        self.wheel_power.balance_changed.connect(lambda x, y: self._on_wheel_balance_changed("power", x, y))
        power_wheel_box.addWidget(self.wheel_power)
        power_wheel_box.addStretch()
        scroll_layout.addLayout(power_wheel_box)

        add_channel_row(scroll_layout, "R", "power_r", 0.1, 4.0, 1.0, section="power")
        add_channel_row(scroll_layout, "G", "power_g", 0.1, 4.0, 1.0, section="power")
        add_channel_row(scroll_layout, "B", "power_b", 0.1, 4.0, 1.0, section="power")
        scroll_layout.addSpacing(6)

        # --- SATURATION ---
        add_section_header(scroll_layout, "Saturation", self._reset_sat)
        add_channel_row(scroll_layout, "S", "sat", 0.0, 4.0, 1.0, section=None)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # --- BOTTOM ACTIONS PANEL ---
        bottom_box = QtWidgets.QVBoxLayout()
        bottom_box.setSpacing(6)

        btn_reset_all = QtWidgets.QPushButton("Reset All Grades")
        btn_reset_all.clicked.connect(self._reset_all_cdl)
        bottom_box.addWidget(btn_reset_all)

        io_box = QtWidgets.QHBoxLayout()
        io_box.setSpacing(6)
        btn_import = QtWidgets.QPushButton("Import CDL...")
        btn_import.clicked.connect(self._import_cdl)
        btn_export = QtWidgets.QPushButton("Export CDL...")
        btn_export.clicked.connect(self._export_cdl)
        io_box.addWidget(btn_import)
        io_box.addWidget(btn_export)
        bottom_box.addLayout(io_box)

        layout.addLayout(bottom_box)
        self.color_grading_panel.hide()

    def _on_wheel_balance_changed(self, section: str, x: float, y: float):
        if getattr(self, '_updating_cdl_internal', False):
            return
        self._updating_cdl_internal = True
        try:
            dr = x
            dg = -0.5 * x + 0.866025 * y
            db = -0.5 * x - 0.866025 * y

            if section == "slope":
                r_spin = self.cdl_controls["slope_r"][1]
                g_spin = self.cdl_controls["slope_g"][1]
                b_spin = self.cdl_controls["slope_b"][1]
                mean = (r_spin.value() + g_spin.value() + b_spin.value()) / 3.0
                scale = 0.5
                r_spin.setValue(max(0.0, min(4.0, mean + scale * dr)))
                g_spin.setValue(max(0.0, min(4.0, mean + scale * dg)))
                b_spin.setValue(max(0.0, min(4.0, mean + scale * db)))
            elif section == "offset":
                r_spin = self.cdl_controls["offset_r"][1]
                g_spin = self.cdl_controls["offset_g"][1]
                b_spin = self.cdl_controls["offset_b"][1]
                mean = (r_spin.value() + g_spin.value() + b_spin.value()) / 3.0
                scale = 0.25
                r_spin.setValue(max(-1.0, min(1.0, mean + scale * dr)))
                g_spin.setValue(max(-1.0, min(1.0, mean + scale * dg)))
                b_spin.setValue(max(-1.0, min(1.0, mean + scale * db)))
            elif section == "power":
                r_spin = self.cdl_controls["power_r"][1]
                g_spin = self.cdl_controls["power_g"][1]
                b_spin = self.cdl_controls["power_b"][1]
                mean = (r_spin.value() + g_spin.value() + b_spin.value()) / 3.0
                scale = 0.4
                r_spin.setValue(max(0.1, min(4.0, mean + scale * dr)))
                g_spin.setValue(max(0.1, min(4.0, mean + scale * dg)))
                b_spin.setValue(max(0.1, min(4.0, mean + scale * db)))
        finally:
            self._updating_cdl_internal = False
        self._on_cdl_changed()

    def _sync_wheel_from_controls(self, section: str):
        if getattr(self, '_updating_cdl_internal', False):
            return
        self._updating_cdl_internal = True
        try:
            if section == "slope" and hasattr(self, "wheel_slope"):
                r = self.cdl_controls["slope_r"][1].value()
                g = self.cdl_controls["slope_g"][1].value()
                b = self.cdl_controls["slope_b"][1].value()
                mean = (r + g + b) / 3.0
                dr, dg, db = r - mean, g - mean, b - mean
                scale = 0.5
                x = (2.0 * dr - dg - db) / (3.0 * scale)
                y = (dg - db) / (1.7320508 * scale)
                self.wheel_slope.set_balance(x, y, emit_signal=False)
            elif section == "offset" and hasattr(self, "wheel_offset"):
                r = self.cdl_controls["offset_r"][1].value()
                g = self.cdl_controls["offset_g"][1].value()
                b = self.cdl_controls["offset_b"][1].value()
                mean = (r + g + b) / 3.0
                dr, dg, db = r - mean, g - mean, b - mean
                scale = 0.25
                x = (2.0 * dr - dg - db) / (3.0 * scale)
                y = (dg - db) / (1.7320508 * scale)
                self.wheel_offset.set_balance(x, y, emit_signal=False)
            elif section == "power" and hasattr(self, "wheel_power"):
                r = self.cdl_controls["power_r"][1].value()
                g = self.cdl_controls["power_g"][1].value()
                b = self.cdl_controls["power_b"][1].value()
                mean = (r + g + b) / 3.0
                dr, dg, db = r - mean, g - mean, b - mean
                scale = 0.4
                x = (2.0 * dr - dg - db) / (3.0 * scale)
                y = (dg - db) / (1.7320508 * scale)
                self.wheel_power.set_balance(x, y, emit_signal=False)
        finally:
            self._updating_cdl_internal = False

    def _reset_slope(self):
        for key in ("slope_r", "slope_g", "slope_b"):
            if key in self.cdl_controls:
                self.cdl_controls[key][1].setValue(self.cdl_controls[key][2])
        if hasattr(self, "wheel_slope"):
            self.wheel_slope.set_balance(0.0, 0.0, emit_signal=False)
        self._on_cdl_changed()

    def _reset_offset(self):
        for key in ("offset_r", "offset_g", "offset_b"):
            if key in self.cdl_controls:
                self.cdl_controls[key][1].setValue(self.cdl_controls[key][2])
        if hasattr(self, "wheel_offset"):
            self.wheel_offset.set_balance(0.0, 0.0, emit_signal=False)
        self._on_cdl_changed()

    def _reset_power(self):
        for key in ("power_r", "power_g", "power_b"):
            if key in self.cdl_controls:
                self.cdl_controls[key][1].setValue(self.cdl_controls[key][2])
        if hasattr(self, "wheel_power"):
            self.wheel_power.set_balance(0.0, 0.0, emit_signal=False)
        self._on_cdl_changed()

    def _reset_sat(self):
        if "sat" in self.cdl_controls:
            self.cdl_controls["sat"][1].setValue(self.cdl_controls["sat"][2])
        self._on_cdl_changed()

    def _reset_all_cdl(self):
        """Reset all color grading parameters to neutral."""
        for key in getattr(self, 'cdl_controls', {}):
            self.cdl_controls[key][1].setValue(self.cdl_controls[key][2])
        if hasattr(self, "wheel_slope"):
            self.wheel_slope.set_balance(0.0, 0.0, emit_signal=False)
        if hasattr(self, "wheel_offset"):
            self.wheel_offset.set_balance(0.0, 0.0, emit_signal=False)
        if hasattr(self, "wheel_power"):
            self.wheel_power.set_balance(0.0, 0.0, emit_signal=False)
        self._on_cdl_changed()

    def _on_cdl_changed(self):
        if not hasattr(self, 'cdl_controls') or not self.cdl_controls:
            return

        def get_val(key):
            return float(self.cdl_controls[key][1].value())

        slope = (get_val("slope_r"), get_val("slope_g"), get_val("slope_b"))
        offset = (get_val("offset_r"), get_val("offset_g"), get_val("offset_b"))
        power = (get_val("power_r"), get_val("power_g"), get_val("power_b"))
        saturation = get_val("sat")

        if hasattr(self, 'viewport') and self.viewport:
            self.viewport.set_cdl_params(slope, offset, power, saturation)
        if hasattr(self, 'viewport_b') and self.viewport_b:
            self.viewport_b.set_cdl_params(slope, offset, power, saturation)
        for vp in getattr(self, 'viewports', []):
            if hasattr(vp, 'set_cdl_params'):
                vp.set_cdl_params(slope, offset, power, saturation)
        if hasattr(self, 'core') and hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.set_cdl_params(slope, offset, power, saturation)

        if hasattr(self, 'viewport') and self.viewport:
            self.viewport.canvas.update()
        for vp in getattr(self, 'viewports', []):
            if vp.isVisible():
                vp.canvas.update()

    def _import_cdl(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import ASC CDL XML", "", "CDL Files (*.cdl *.xml *.cc)")
        if not path:
            return
        from core.color_manager import load_cdl_file
        res = load_cdl_file(path)
        if res:
            slope, offset, power, sat = res
            for key, val in zip(("slope_r", "slope_g", "slope_b"), slope):
                if key in self.cdl_controls:
                    self.cdl_controls[key][1].setValue(val)
            for key, val in zip(("offset_r", "offset_g", "offset_b"), offset):
                if key in self.cdl_controls:
                    self.cdl_controls[key][1].setValue(val)
            for key, val in zip(("power_r", "power_g", "power_b"), power):
                if key in self.cdl_controls:
                    self.cdl_controls[key][1].setValue(val)
            if "sat" in self.cdl_controls:
                self.cdl_controls["sat"][1].setValue(sat)

            self._on_cdl_changed()
            if hasattr(self, 'status') and self.status:
                self.status.showMessage(f"CDL Imported: {os.path.basename(path)}", 3000)
            elif hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().showMessage(f"CDL Imported: {os.path.basename(path)}", 3000)
        else:
            QtWidgets.QMessageBox.warning(self, "Import Error", "Failed to parse CDL file. Please check XML format.")

    def _export_cdl(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export ASC CDL XML", "grade.cdl", "CDL Files (*.cdl)")
        if not path:
            return

        def get_val(key):
            return float(self.cdl_controls[key][1].value())

        slope = (get_val("slope_r"), get_val("slope_g"), get_val("slope_b"))
        offset = (get_val("offset_r"), get_val("offset_g"), get_val("offset_b"))
        power = (get_val("power_r"), get_val("power_g"), get_val("power_b"))
        sat = get_val("sat")

        from core.color_manager import save_cdl_file
        if save_cdl_file(path, slope, offset, power, sat):
            if hasattr(self, 'status') and self.status:
                self.status.showMessage(f"CDL Exported: {os.path.basename(path)}", 3000)
            elif hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().showMessage(f"CDL Exported: {os.path.basename(path)}", 3000)
        else:
            QtWidgets.QMessageBox.warning(self, "Export Error", "Failed to write CDL file.")

    # ---------- Phase 5: Studio Platform & Playlist Navigation ----------
    def _toggle_false_color(self, enabled: bool):
        """Toggle 10-zone false color exposure & clipping heatmap."""
        if hasattr(self, 'core') and hasattr(self.core, 'color_pipeline'):
            self.core.color_pipeline.state.false_color = enabled
        if hasattr(self, 'core_b') and hasattr(self.core_b, 'color_pipeline'):
            self.core_b.color_pipeline.state.false_color = enabled
        if hasattr(self, 'viewport') and self.viewport:
            self.viewport.set_false_color(enabled)
            self.viewport.update()
        if hasattr(self, 'viewports'):
            for vp in self.viewports:
                vp.set_false_color(enabled)
                vp.update()
        if hasattr(self, 'false_color_action') and self.false_color_action.isChecked() != enabled:
            self.false_color_action.blockSignals(True)
            self.false_color_action.setChecked(enabled)
            self.false_color_action.blockSignals(False)
        if hasattr(self, 'btn_false_color') and self.btn_false_color.isChecked() != enabled:
            self.btn_false_color.blockSignals(True)
            self.btn_false_color.setChecked(enabled)
            self.btn_false_color.blockSignals(False)
        if self.core.frame_count():
            self._show_frame(self.current_index)

    def _toggle_playlist_panel(self):
        """Toggle the collapsible playlist / shot browser drawer."""
        if self.playlist_widget.isVisible():
            self.playlist_widget.hide()
        else:
            self.playlist_widget.show()
            self.playlist_widget.refresh()

    def _trigger_playlist_prefetch(self, count: int = 2):
        """
        Asynchronously prefetch / download upcoming media items in the playlist
        so playback transitions seamlessly without any network stalls.
        """
        if not hasattr(self, 'playlist_service') or not self.playlist_service.items:
            return

        cur_idx = self.playlist_service.current_index
        total = len(self.playlist_service.items)

        items_to_check = []
        for offset in range(1, count + 1):
            target_idx = cur_idx + offset
            if target_idx < total:
                items_to_check.append(self.playlist_service.items[target_idx])
            elif self.playlist_service.loop and total > 1:
                items_to_check.append(self.playlist_service.items[target_idx % total])

        if not items_to_check:
            return

        class _PrefetchTask(QtCore.QRunnable):
            def __init__(self, target_item: PlaylistItem):
                super().__init__()
                self.target_item = target_item

            def run(self):
                try:
                    m_path = self.target_item.media_path
                    p_id = getattr(self.target_item, 'kitsu_preview_id', None)
                    if (not m_path or not os.path.exists(m_path)) and (p_id or (m_path and m_path.startswith("http"))):
                        cached = kitsu_client.download_preview_file(
                            preview_file_id=p_id,
                            media_url=m_path if m_path and m_path.startswith("http") else None
                        )
                        if cached and os.path.exists(cached):
                            self.target_item.media_path = cached
                except Exception as e:
                    print(f"[Kitsu Prefetch] Error pre-caching upcoming shot: {e}")

        for it in items_to_check:
            m_path = it.media_path
            p_id = getattr(it, 'kitsu_preview_id', None)
            if (not m_path or not os.path.exists(m_path)) and (p_id or (m_path and m_path.startswith("http"))):
                QtCore.QThreadPool.globalInstance().start(_PrefetchTask(it))

    def _playlist_seamless_next(self):
        """
        Seamlessly transition to the next playlist item without interrupting playback.
        Eliminates the pause/halt between shots in the playlist, cutting directly like an edit timeline.
        """
        item = self.playlist_service.next_item()
        if not item:
            self.pause()
            return

        self.playlist_widget.set_current_index(self.playlist_service.current_index)
        self._current_kitsu_shot = item
        path = item.media_path
        preview_id = getattr(item, 'kitsu_preview_id', None)

        # If file is not cached yet, download synchronously as fallback
        if not path or not os.path.exists(path):
            if preview_id or (path and (path.startswith("http://") or path.startswith("https://"))):
                try:
                    cached_file = kitsu_client.download_preview_file(
                        preview_file_id=preview_id,
                        media_url=path if path and path.startswith("http") else None
                    )
                    if cached_file and os.path.exists(cached_file):
                        item.media_path = cached_file
                        path = cached_file
                except Exception as e:
                    print(f"[Kitsu] Failed to download preview media: {e}")

        if not path or not os.path.exists(path):
            self.pause()
            self._on_playlist_shot_selected(item)
            return

        # Perform fast seamless cut
        self._loading_from_playlist = True
        try:
            self.core.load(path)
        except Exception as e:
            self.pause()
            print(f"[Seamless Transition] Failed to load {path}: {e}")
            return
        finally:
            self._loading_from_playlist = False

        cnt = self.core.frame_count()
        self.current_index = 0
        self.range_in = 0
        self.range_out = max(0, cnt - 1)

        self.frame_slider.setMaximum(max(0, cnt - 1))
        self.frame_slider.setValue(0)
        self._configure_frame_slider_ticks()
        if hasattr(self, 'range_start_edit'):
            self.range_start_edit.setText("0")
        if hasattr(self, 'range_end_edit'):
            self.range_end_edit.setText(str(self.range_out))

        # Auto-load Persistent Annotations & Bookmarks
        try:
            sidecar = AnnotationService.load_sidecar(path)
            if sidecar:
                self.annotations = sidecar.get("annotations", {})
                self.bookmarks = set(sidecar.get("bookmarks", []))
            else:
                self.annotations = {}
                self.bookmarks = set()
        except Exception:
            self.annotations = {}
            self.bookmarks = set()

        self._refresh_annotation_display()
        self._update_timeline_markers()

        # Audio attach and position reset
        self._audio_attach(path)
        if self._audio_player and self._audio_player.source().isValid():
            self._audio_player.setPosition(0)
            if self.playing:
                self._audio_player.play()

        # Reset playback clock for the new clip
        if self._elapsed_timer is not None:
            self._elapsed_timer.restart()
        self._play_start_index = 0

        # Show frame 0 immediately
        self._show_frame(0)

        # Trigger prefetch of upcoming clips
        self._trigger_playlist_prefetch(count=2)

    def _playlist_seamless_prev(self):
        """
        Seamlessly transition to the previous playlist item without interrupting reverse playback.
        Eliminates the pause/halt between shots in the playlist, cutting directly like an edit timeline.
        """
        item = self.playlist_service.prev_item()
        if not item:
            self.pause()
            return

        self.playlist_widget.set_current_index(self.playlist_service.current_index)
        self._current_kitsu_shot = item
        path = item.media_path
        preview_id = getattr(item, 'kitsu_preview_id', None)

        if not path or not os.path.exists(path):
            if preview_id or (path and (path.startswith("http://") or path.startswith("https://"))):
                try:
                    cached_file = kitsu_client.download_preview_file(
                        preview_file_id=preview_id,
                        media_url=path if path and path.startswith("http") else None
                    )
                    if cached_file and os.path.exists(cached_file):
                        item.media_path = cached_file
                        path = cached_file
                except Exception as e:
                    print(f"[Kitsu] Failed to download preview media: {e}")

        if not path or not os.path.exists(path):
            self.pause()
            self._on_playlist_shot_selected(item)
            return

        self._loading_from_playlist = True
        try:
            self.core.load(path)
        except Exception as e:
            self.pause()
            print(f"[Seamless Transition] Failed to load {path}: {e}")
            return
        finally:
            self._loading_from_playlist = False

        cnt = self.core.frame_count()
        last_frame = max(0, cnt - 1)
        self.current_index = last_frame
        self.range_in = 0
        self.range_out = last_frame

        self.frame_slider.setMaximum(last_frame)
        self.frame_slider.setValue(last_frame)
        self._configure_frame_slider_ticks()
        if hasattr(self, 'range_start_edit'):
            self.range_start_edit.setText("0")
        if hasattr(self, 'range_end_edit'):
            self.range_end_edit.setText(str(self.range_out))

        try:
            sidecar = AnnotationService.load_sidecar(path)
            if sidecar:
                self.annotations = sidecar.get("annotations", {})
                self.bookmarks = set(sidecar.get("bookmarks", []))
            else:
                self.annotations = {}
                self.bookmarks = set()
        except Exception:
            self.annotations = {}
            self.bookmarks = set()

        self._refresh_annotation_display()
        self._update_timeline_markers()

        self._audio_attach(path)
        if self._audio_player and self._audio_player.source().isValid():
            self._audio_player.pause()

        if self._elapsed_timer is not None:
            self._elapsed_timer.restart()
        self._play_start_index = last_frame

        self._show_frame(last_frame)
        self._trigger_playlist_prefetch(count=2)

    def playlist_next_shot(self, autoplay: bool = False):
        """Advance to the next shot in the playlist."""
        item = self.playlist_service.next_item()
        if item:
            self.playlist_widget.set_current_index(self.playlist_service.current_index)
            self._on_playlist_shot_selected(item)
            self._trigger_playlist_prefetch(count=2)
            if autoplay:
                self.play()

    def playlist_prev_shot(self, autoplay: bool = False):
        """Go back to the previous shot in the playlist."""
        item = self.playlist_service.prev_item()
        if item:
            self.playlist_widget.set_current_index(self.playlist_service.current_index)
            self._on_playlist_shot_selected(item)
            self._trigger_playlist_prefetch(count=2)
            if autoplay:
                self.play()

    def _on_playlist_shot_selected(self, item: PlaylistItem):
        """Load media for the selected playlist item and update Kitsu review context."""
        if not item:
            return
        self._current_kitsu_shot = item
        path = item.media_path
        preview_id = getattr(item, 'kitsu_preview_id', None)

        # If media is not already on disk, download/cache it from Kitsu
        if not path or not os.path.exists(path):
            if preview_id or (path and (path.startswith("http://") or path.startswith("https://"))):
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
                self.statusBar().showMessage(f"Downloading preview for {item.name or item.shot} from Kitsu...", 5000)
                try:
                    cached_file = kitsu_client.download_preview_file(
                        preview_file_id=preview_id,
                        media_url=path if path and path.startswith("http") else None
                    )
                    if cached_file and os.path.exists(cached_file):
                        item.media_path = cached_file
                        path = cached_file
                except Exception as e:
                    print(f"[Kitsu] Failed to download preview media: {e}")
                finally:
                    QtWidgets.QApplication.restoreOverrideCursor()

        if path and os.path.exists(path):
            self._loading_from_playlist = True
            try:
                self.load_media(path)
            finally:
                self._loading_from_playlist = False
        else:
            QtWidgets.QMessageBox.warning(
                self, "Media File Missing",
                f"Media could not be loaded or downloaded from Kitsu:\n{path or item.name}\n\nPlease verify network connection or storage mount."
            )

    def _on_playlist_add_files(self):
        """Allow user to select multiple files or sequences to add to the playlist."""
        media_filter = (
            "All Supported Media (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.mov *.mp4 *.avi *.mkv *.mxf *.webm);;"
            "Video Files (*.mov *.mp4 *.avi *.mkv *.mxf *.webm *.m4v *.flv *.ts);;"
            "Image Sequences (*.exr *.sxr *.tif *.tiff *.dpx *.cin *.png *.jpg *.jpeg *.tga *.bmp *.webp);;"
            "All Files (*.*)"
        )
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add Media Files to Playlist (Select Multiple)", "", media_filter)
        if paths:
            self.add_media_paths_to_playlist(paths)

    def _on_playlist_add_folder(self):
        """Allow user to select a folder containing video files or image sequences."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Add Media Folder to Playlist")
        if folder:
            self.add_media_paths_to_playlist([folder])

    def add_media_paths_to_playlist(self, paths: List[str]):
        """
        Process multiple file and/or directory paths, group image sequences so only one entry is created
        per sequence, create PlaylistItem instances, and add them to the playlist.
        """
        if not paths:
            return

        import re
        from core.player_core import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, detect_image_sequence

        added_items: List[PlaylistItem] = []
        processed_seq_bases = set()

        # Collect all concrete files if directories are passed
        flat_files: List[str] = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in sorted(files):
                        flat_files.append(os.path.join(root, f))
            elif os.path.isfile(p):
                flat_files.append(p)

        for file_path in flat_files:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                ctx = kitsu_client.parse_shot_context(file_path)
                shot_name = ctx.get("shot") or os.path.splitext(os.path.basename(file_path))[0]
                item = PlaylistItem(
                    media_path=file_path,
                    name=os.path.basename(file_path),
                    sequence=ctx.get("sequence", ""),
                    shot=shot_name,
                    task=ctx.get("task", ""),
                    version=ctx.get("version", "")
                )
                added_items.append(item)
            elif ext in IMAGE_EXTENSIONS:
                seq = detect_image_sequence(file_path)
                if seq:
                    first_f = seq[0]
                    folder = os.path.dirname(first_f)
                    base = os.path.splitext(os.path.basename(first_f))[0]
                    base_key = os.path.join(folder, re.sub(r'\d+$', '', base))
                    if base_key in processed_seq_bases:
                        continue
                    processed_seq_bases.add(base_key)

                    ctx = kitsu_client.parse_shot_context(first_f)
                    shot_name = ctx.get("shot") or re.sub(r'[._-]\d+$', '', os.path.splitext(os.path.basename(first_f))[0])
                    item = PlaylistItem(
                        media_path=first_f,
                        name=shot_name,
                        sequence=ctx.get("sequence", ""),
                        shot=shot_name,
                        task=ctx.get("task", ""),
                        version=ctx.get("version", ""),
                        frame_count=len(seq)
                    )
                    added_items.append(item)
                else:
                    ctx = kitsu_client.parse_shot_context(file_path)
                    shot_name = ctx.get("shot") or os.path.splitext(os.path.basename(file_path))[0]
                    item = PlaylistItem(
                        media_path=file_path,
                        name=os.path.basename(file_path),
                        sequence=ctx.get("sequence", ""),
                        shot=shot_name,
                        task=ctx.get("task", ""),
                        version=ctx.get("version", ""),
                        frame_count=1
                    )
                    added_items.append(item)

        if not added_items:
            QtWidgets.QMessageBox.information(self, "No Media Found", "No supported video or image sequence files found in the selection.")
            return

        was_empty = self.playlist_service.is_empty()
        for it in added_items:
            self.playlist_service.add_item(it)

        self.playlist_widget.refresh()
        self.playlist_widget.show()

        if was_empty and self.playlist_service.items:
            first = self.playlist_service.set_current_index(0)
            self.playlist_widget.set_current_index(0)
            if first:
                self._on_playlist_shot_selected(first)

        self.status.showMessage(f"Added {len(added_items)} shot(s) to playlist", 3000)

    def _open_current_shot_in_kitsu(self, item=None):
        """Open the active shot / task URL in default web browser (Ctrl+K)."""
        target = item or getattr(self, '_current_kitsu_shot', None)
        url = None
        if target:
            if target.kitsu_url:
                url = target.kitsu_url
            elif getattr(target, 'kitsu_shot_id', None):
                url = kitsu_client.build_shot_url(target.kitsu_shot_id, getattr(target, 'kitsu_project_id', None))
            elif getattr(target, 'kitsu_task_id', None):
                url = kitsu_client.build_task_url(target.kitsu_task_id, getattr(target, 'kitsu_project_id', None))

        if not url and self.core.media and self.core.media.path:
            ctx = kitsu_client.parse_shot_context(self.core.media.path)
            if ctx.get('shot') and kitsu_client.is_authenticated():
                try:
                    shot_obj = kitsu_client.get_shot_by_name(ctx['shot'])
                    if shot_obj and shot_obj.get('id'):
                        url = kitsu_client.build_shot_url(shot_obj['id'], shot_obj.get('project_id'))
                except Exception:
                    pass

        if not url and kitsu_client.host_url:
            url = f"{kitsu_client.host_url.rstrip('/')}/productions"

        if url:
            webbrowser.open(url)
            self.statusBar().showMessage(f"Opening in Kitsu: {url}", 4000)
        else:
            self._on_configure_kitsu()

    def _on_kitsu_shot_opened(self, item):
        if item:
            s_name = getattr(item, 'shot_name', None) or getattr(item, 'name', 'Shot')
            self.statusBar().showMessage(f"Opened {s_name} in Kitsu browser", 3000)

    def _on_load_kitsu_playlist(self):
        """Open Kitsu Connect dialog and load selected review playlist into the player."""
        dlg = KitsuConnectDialog(parent=self, prefs=self.prefs)
        if dlg.exec():
            items = dlg.get_selected_playlist_items()
            if items:
                self._custom_playlist_active = True
                self.playlist_service.clear()
                for item in items:
                    self.playlist_service.add_item(item)
                self.playlist_widget.refresh()
                self.playlist_widget.show()
                # Load first shot
                first = self.playlist_service.set_current_index(0)
                self.playlist_widget.set_current_index(0)
                if first:
                    self._on_playlist_shot_selected(first)
                self._trigger_playlist_prefetch(count=2)

    def _on_publish_kitsu_review(self, target_item=None):
        """Capture current annotated frame and launch Kitsu supervisor review publish dialog."""
        if not self.core.frame_count():
            QtWidgets.QMessageBox.warning(self, "No Media", "Please load a shot before publishing a review.")
            return

        if not kitsu_client.is_authenticated():
            conn_dlg = KitsuConnectDialog(parent=self, prefs=self.prefs)
            if not conn_dlg.exec():
                return

        item = target_item or getattr(self, '_current_kitsu_shot', None)
        shot_name = "Shot"
        shot_id = None
        task_id = None
        seq_name = ""
        task_name = ""

        if item:
            shot_name = item.shot_name or item.name
            shot_id = getattr(item, 'kitsu_shot_id', None)
            task_id = getattr(item, 'kitsu_task_id', None)
            seq_name = getattr(item, 'sequence_name', '')
            task_name = getattr(item, 'task_name', '')

        if not shot_id and self.core.media and self.core.media.path:
            ctx = kitsu_client.parse_shot_context(self.core.media.path)
            if ctx.get('shot'):
                shot_name = ctx['shot']
                seq_name = ctx.get('sequence', '')
                task_name = ctx.get('task', '')
                if kitsu_client.is_authenticated():
                    try:
                        s_data = kitsu_client.get_shot_by_name(shot_name)
                        if s_data:
                            shot_id = s_data.get('id')
                    except Exception:
                        pass

        preview_path = None
        try:
            arr = self.viewport.get_frame_with_annotations()
            if arr is not None:
                h, w = arr.shape[:2]
                c = arr.shape[2] if len(arr.shape) > 2 else 3
                fmt = QtGui.QImage.Format.Format_RGB888 if c == 3 else QtGui.QImage.Format.Format_RGBA8888
                img = QtGui.QImage(arr.tobytes(), w, h, w * c, fmt)
                temp_dir = tempfile.gettempdir()
                clean_name = "".join([c for c in shot_name if c.isalnum() or c in ('-', '_')])
                preview_path = os.path.join(temp_dir, f"kitsu_annot_{clean_name}_{self.current_index + 1:04d}.png")
                img.save(preview_path, "PNG")
        except Exception as e:
            print(f"[Kitsu] Warning: Failed to render snapshot preview: {e}")

        shot_ctx = {
            "shot": shot_name,
            "sequence": seq_name,
            "task": task_name,
        }

        dlg = KitsuPublishDialog(
            task_id=task_id,
            shot_id=shot_id,
            shot_name=shot_name,
            preview_image_path=preview_path,
            shot_context=shot_ctx,
            parent=self,
            prefs=self.prefs
        )
        if dlg.exec():
            QtWidgets.QMessageBox.information(
                self, "Review Note Published",
                f"Review feedback and annotations successfully published to Kitsu for {shot_name}!"
            )

    def _on_configure_kitsu(self):
        """Open Kitsu connection and credentials dialog."""
        dlg = KitsuConnectDialog(parent=self, prefs=self.prefs)
        dlg.exec()

    def _on_toggle_clear_kitsu_cache_exit(self, checked: bool):
        self.prefs["clear_kitsu_cache_on_exit"] = checked
        self._save_prefs()
        self.statusBar().showMessage(
            f"Kitsu cache auto-clear on exit {'enabled' if checked else 'disabled'}.", 3000
        )

    def _on_clear_kitsu_cache_now(self):
        """Manually wipe all cached Kitsu preview media and thumbnails."""
        files_rem, bytes_freed = kitsu_client.clear_cache()
        if bytes_freed >= 1024 * 1024:
            freed_str = f"{bytes_freed / (1024 * 1024):.1f} MB"
        else:
            freed_str = f"{bytes_freed / 1024:.0f} KB"
        QtWidgets.QMessageBox.information(
            self, "Kitsu Cache Cleared",
            f"Local Kitsu media cache has been cleared.\nRemoved {files_rem} files ({freed_str} freed)."
        )
        self.statusBar().showMessage(f"Kitsu cache cleared: {files_rem} files ({freed_str}) removed.", 4000)

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handle application exit and clean up resources/cache if configured."""
        try:
            if self.prefs.get("clear_kitsu_cache_on_exit", False):
                files_rem, bytes_freed = kitsu_client.clear_cache()
                print(f"[Kitsu] Exit cleanup: deleted {files_rem} cached files ({bytes_freed} bytes freed).")
        except Exception as e:
            print(f"[Kitsu] Warning: Error during exit cache cleanup: {e}")

        # Stop playback and timers
        try:
            self.pause()
            if hasattr(self, 'timer') and self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass

        super().closeEvent(event)

    # ---------- Run ----------
    def run(self):
        self.show()
        sys.exit(QtWidgets.QApplication.instance().exec())

