"""Enhanced PyQt6 main window for VFXPlayer with compare & advanced controls."""

import sys, os, json
from typing import Optional, Tuple
from PyQt6 import QtWidgets, QtGui, QtCore
from gui.vispy_viewport import VispyViewport
from core.color_manager import ColorManager
from gui.settings_dialog import SettingsDialog


class PlayheadSlider(QtWidgets.QSlider):
    """Horizontal slider with a thin red playhead line drawn at current value.

    Previously defined inside a method; lifted to module scope so it's available
    when building the toolbar. Draws a red line at the handle center for a
    clearer playhead indicator without custom overlay widgets."""
    def __init__(self, *args, **kwargs):
        super().__init__(QtCore.Qt.Orientation.Horizontal, *args, **kwargs)
        self.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.setTickInterval(1)
        self.setSingleStep(1)

    def paintEvent(self, event: QtGui.QPaintEvent):  # type: ignore[override]
        super().paintEvent(event)
        if self.maximum() <= self.minimum():
            return
        ratio = (self.value() - self.minimum()) / max(1, (self.maximum() - self.minimum()))
        x = int(ratio * (self.width() - 1))
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        pen = QtGui.QPen(QtGui.QColor(255, 60, 60))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawLine(x, 0, x, self.height())
        p.end()


from core.color_manager import ColorManager


if getattr(sys, 'frozen', False):
    _APP_ROOT = os.path.dirname(sys.executable)
else:
    _APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PREFS_PATH = os.path.join(_APP_ROOT, "prefs.json")


from gui.vispy_viewport import VispyViewport

# PlayerViewport class removed, using VispyViewport instead



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.setWindowTitle("VFXPlayer")
        self.resize(1280, 800)
        self.setMinimumSize(800, 500)

        # Apply "Dark Pro" Theme
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QMenuBar { background-color: #1a1a1a; border-bottom: 1px solid #333; }
            QMenuBar::item { padding: 8px 12px; }
            QMenuBar::item:selected { background-color: #333; }
            QMenu { background-color: #1a1a1a; border: 1px solid #333; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: #0078d4; }
            QScrollBar:vertical { background: #1a1a1a; width: 12px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 6px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QSplitter::handle { background: #333; }
            QStatusBar { background-color: #1a1a1a; color: #888; }
            QPushButton { background-color: #2a2a2a; border: none; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #3a3a3a; }
            QPushButton:pressed { background-color: #0078d4; }
            QLineEdit { background-color: #222; border: 1px solid #333; border-radius: 4px; padding: 4px; color: #ddd; selection-background-color: #0078d4; }
            QComboBox { background-color: #222; border: 1px solid #333; border-radius: 4px; padding: 4px; }
            QDoubleSpinBox, QSpinBox { background-color: #222; border: 1px solid #333; border-radius: 4px; padding: 4px; }
            QLabel { color: #aaa; }
        """)

        # Viewports
        try:
            self.viewport = VispyViewport(main_window=self, role='primary')
            self.viewport_b = VispyViewport(main_window=self, role='secondary')
            self.viewport_b.hide()
            # Connect viewport click interactions
            self.viewport.single_clicked.connect(self._toggle_play_pause)
            self.viewport.double_clicked.connect(lambda: self._toggle_fullscreen(not self.fullscreen))
        except Exception as e:
            # Fallback or re-raise
            raise e

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.viewport)
        self.splitter.addWidget(self.viewport_b)
        self.splitter.setSizes([1, 1])

        # Comparison state
        self.wipe_mode = False
        self.side_by_side = False
        self.fullscreen = False
        self.compare_offset = 0

        # Main Layout (Stacking for HUD)
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
        self.viewport_layout.addWidget(self.splitter)
        
        self.main_layout.addWidget(self.viewport_container, 1)

        # HUD Container (Bottom)
        self.hud_container = QtWidgets.QFrame()
        self.hud_container.setFixedHeight(60)
        self.hud_container.setStyleSheet("background-color: #181818; border-top: 1px solid #2a2a2a;")
        self.hud_layout = QtWidgets.QHBoxLayout(self.hud_container)
        self.hud_layout.setContentsMargins(16, 0, 16, 0)
        self.main_layout.addWidget(self.hud_container)

        # Init wipe UI (hidden by default)
        self.side_by_side = False
        self.wipe_mode = False
        self._init_wipe_ui()

        # Initialize OCIO
        try:
            self.color_manager = ColorManager()
        except Exception:
            # Minimal fallback to avoid crash
            class DummyCM:
                def __init__(self):
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
        self.prefs = {}
        self._load_prefs()
        # Apply prefs to manager
        self.color_manager.ocio_enabled = getattr(self, '_prefs_ocio_enabled', True)
        self.color_manager.input_cs = getattr(self, '_prefs_input_cs', self.color_manager.input_cs)
        self.color_manager.output_cs = getattr(self, '_prefs_output_cs', self.color_manager.output_cs)
        self.color_manager.rebuild_processor()

        # Build menus & HUD
        self._build_menu()
        self._build_hud()
        


        # Secondary core
        from core.player_core import PlayerCore
        primary_cap = getattr(self.core, 'cache_capacity', 500)
        self.core_b = PlayerCore(cache_capacity=primary_cap, prefetch_enabled=False)
        
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
        self.current_index = 0
        self.loop = True
        self._elapsed_timer = None
        self._play_start_index = 0

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
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

    def _build_hud(self):
        """Construct the bottom Heads-Up Display for controls."""
        l = self.hud_layout
        
        btn_style = """
            QPushButton {
                background-color: #333;
                color: #ddd;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #555; }
            QPushButton:checked { background-color: #4a90e2; color: white; }
        """
        
        # 1. Playback Controls
        self.prev_btn = QtWidgets.QPushButton("⏮")
        self.prev_btn.setFixedSize(40, 40)
        self.prev_btn.clicked.connect(lambda: self.seek(self.current_index - 1))
        
        self.play_btn = QtWidgets.QPushButton("▶")
        self.play_btn.setFixedSize(50, 40)
        self.play_btn.clicked.connect(self.play)
        
        self.pause_btn = QtWidgets.QPushButton("⏸")
        self.pause_btn.setFixedSize(50, 40)
        self.pause_btn.clicked.connect(self.pause)
        self.pause_btn.hide()
        
        self.next_btn = QtWidgets.QPushButton("⏭")
        self.next_btn.setFixedSize(40, 40)
        self.next_btn.clicked.connect(lambda: self.seek(self.current_index + 1))
        
        l.addWidget(self.prev_btn)
        self.play_btn.setCheckable(True)
        self.play_btn.setStyleSheet(btn_style)
        self.play_btn.clicked.connect(lambda: self.pause() if self.play_btn.isChecked() else self.play())
        self.hud_layout.addWidget(self.play_btn)

        # 2. Timeline Slider
        self.frame_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.frame_slider.setMinimumHeight(40)
        self.frame_slider.setMinimumWidth(300) # Ensure it's not squashed
        self.frame_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #444;
                height: 10px;
                background: #2a2a2a;
                margin: 0px;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #4a90e2;
                border-radius: 5px;
            }
            QSlider::add-page:horizontal {
                background: #2a2a2a;
                border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: #c0c0c0;
                border: 1px solid #555;
                width: 22px;
                height: 22px;
                margin: -6px 0;
                border-radius: 11px;
            }
            QSlider::handle:horizontal:hover { background: #fff; }
        """)
        self.frame_slider.valueChanged.connect(self._show_frame)
        self.hud_layout.addWidget(self.frame_slider, 1) # stretch

        # 3. Info
        self.frame_info = QtWidgets.QLabel("Frame: 0/0")
        self.frame_info.setStyleSheet("color: #aaa; font-weight: bold; font-size: 12px;")
        self.hud_layout.addWidget(self.frame_info)

        # 4. FPS
        self.hud_layout.addWidget(QtWidgets.QLabel("FPS:"))
        self.fps_edit = QtWidgets.QLineEdit("24.0")
        self.fps_edit.setFixedWidth(50)
        self.fps_edit.setStyleSheet("background: #222; color: #ddd; border: 1px solid #444; padding: 4px;")
        self.fps_edit.editingFinished.connect(self._update_timer_interval)
        self.hud_layout.addWidget(self.fps_edit)
        
        # 5. Exposure
        self.hud_layout.addSpacing(12)
        
        exp_lbl = QtWidgets.QPushButton("Exp:")
        exp_lbl.setToolTip("Click to reset Exposure to 0.0")
        exp_lbl.setFlat(True)
        exp_lbl.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        exp_lbl.setStyleSheet("color: #aaa; font-weight: bold; border: none; padding: 2px 4px;")
        exp_lbl.clicked.connect(self._reset_exposure)
        self.hud_layout.addWidget(exp_lbl)

        self.exp_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.exp_slider.setRange(-100, 100) # -10.0 to 10.0
        self.exp_slider.setValue(int(self.exposure * 10))
        self.exp_slider.setFixedWidth(100)
        self.exp_slider.setStyleSheet(self.frame_slider.styleSheet()) # Reuse style
        self.exp_slider.valueChanged.connect(self._on_exp_slider)
        self.hud_layout.addWidget(self.exp_slider)
        
        self.exp_spin = QtWidgets.QDoubleSpinBox()
        self.exp_spin.setRange(-10.0, 10.0)
        self.exp_spin.setSingleStep(0.1)
        self.exp_spin.setValue(self.exposure)
        self.exp_spin.setFixedWidth(60)
        self.exp_spin.setStyleSheet("background: #222; color: #ddd; padding: 4px;")
        self.exp_spin.valueChanged.connect(self._on_exp_spin)
        self.hud_layout.addWidget(self.exp_spin)
        
        # 6. Gamma
        self.hud_layout.addSpacing(12)
        
        gam_lbl = QtWidgets.QPushButton("Gam:")
        gam_lbl.setToolTip("Click to reset Gamma to 1.0")
        gam_lbl.setFlat(True)
        gam_lbl.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        gam_lbl.setStyleSheet("color: #aaa; font-weight: bold; border: none; padding: 2px 4px;")
        gam_lbl.clicked.connect(self._reset_gamma)
        self.hud_layout.addWidget(gam_lbl)

        self.gam_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.gam_slider.setRange(1, 50) # 0.1 to 5.0
        self.gam_slider.setValue(int(self.gamma * 10))
        self.gam_slider.setFixedWidth(100)
        self.gam_slider.setStyleSheet(self.frame_slider.styleSheet())
        self.gam_slider.valueChanged.connect(self._on_gam_slider)
        self.hud_layout.addWidget(self.gam_slider)

        self.gam_spin = QtWidgets.QDoubleSpinBox()
        self.gam_spin.setRange(0.1, 5.0)
        self.gam_spin.setSingleStep(0.1)
        self.gam_spin.setValue(self.gamma)
        self.gam_spin.setFixedWidth(60)
        self.gam_spin.setStyleSheet("background: #222; color: #ddd; padding: 4px;")
        self.gam_spin.valueChanged.connect(self._on_gam_spin)
        self.hud_layout.addWidget(self.gam_spin)

        # OCIO controls are now in the top bar (see _build_menu)


    def _build_toolbar(self):
        # Legacy toolbar method - deprecated by HUD
        pass

    def play(self):
        if self.playing: return
        self.playing = True
        self.play_btn.hide(); self.pause_btn.show()
        if self.core.media and self.core.media.type == 'video':
             self._elapsed_timer = QtCore.QElapsedTimer()
             self._elapsed_timer.start()
             self._play_start_index = self.current_index
        self.timer.start()

    def pause(self):
        if not self.playing: return
        self.playing = False
        self.pause_btn.hide(); self.play_btn.show()
        self.timer.stop()

    def stop(self):
        self.pause()
        self.seek(0)

    def seek(self, index):
        if self.core.frame_count() == 0:
            return
        idx = max(0, min(self.core.frame_count() - 1, index))
        # If scrubbing (dragging slider), maybe pause?
        # For now, just show frame
        self._show_frame(idx)
        # Update elapsed anchor if playing video
        if self.playing and self.core.media.type == 'video':
            self._elapsed_timer.restart()
            self._play_start_index = idx

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
        # File Menu
        file_menu = self.menuBar().addMenu("File")
        
        # ... (rest of menus will be added normally)
        
        # We want the Viewer dropdown to appear in the Menu Bar, right after plugins/help
        # But we build menus sequentially. "Playback" is added later.
        # So we should create a placeholder or add it at the end of _build_menu.
        
        # Let's defer adding the Viewer widget until after other menus are added.
        # But here we are at the top of _build_menu. 
        # We can init the widget here and add it at the end.
        
        self.viewer_container = QtWidgets.QWidget()
        # Ensure it's transparent to blend with menu bar
        self.viewer_container.setStyleSheet("background: transparent;")
        vc_layout = QtWidgets.QHBoxLayout(self.viewer_container)
        vc_layout.setContentsMargins(10, 2, 0, 2) # Add slight vertical padding
        vc_layout.setSpacing(5)
        
        lbl = QtWidgets.QLabel("Viewer:")
        lbl.setStyleSheet("color: #ddd;") # Ensure visibility
        vc_layout.addWidget(lbl)
        
        self.viewer_combo = QtWidgets.QComboBox()
        self.viewer_combo.setMinimumWidth(200) # Slightly wider
        self.viewer_combo.setStyleSheet("""
            QComboBox { 
                background-color: #333; 
                color: #ddd; 
                border: 1px solid #555; 
                border-radius: 3px;
                padding: 2px 5px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { 
                image: none; 
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #aaa;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: #ddd;
                selection-background-color: #555;
            }
        """)
        self.viewer_combo.addItems(self.color_manager.view_choices)
        if self.color_manager.output_cs in self.color_manager.view_choices:
            self.viewer_combo.setCurrentText(self.color_manager.output_cs)
        self.viewer_combo.currentTextChanged.connect(self._on_viewer_changed)
        vc_layout.addWidget(self.viewer_combo)
        
        # We will add this container to the menu bar using QWidgetAction
        # Important: QWidgetAction needs the widget to be visible?
        # self.viewer_container.show() # Not usually needed for actions, but let's see.

        
        open_action = QtGui.QAction("Open Media...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        
        open_comp_action = QtGui.QAction("Open Compare Media...", self)
        open_comp_action.setShortcut("Ctrl+Shift+O")
        open_comp_action.triggered.connect(self._open_file_compare)
        file_menu.addAction(open_comp_action)

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
        
        fs_action = QtGui.QAction("Fullscreen", self)
        fs_action.setCheckable(True)
        fs_action.setShortcut("F11")
        fs_action.triggered.connect(lambda: self._toggle_fullscreen(fs_action.isChecked()))
        view_menu.addAction(fs_action)

        # Playback Menu
        play_menu = self.menuBar().addMenu("Playback")
        
        play_action = QtGui.QAction("Play/Pause", self)
        play_action.setShortcut("Space")
        play_action.triggered.connect(lambda: self.pause() if self.playing else self.play())
        play_menu.addAction(play_action)

        stop_action = QtGui.QAction("Stop", self)
        stop_action.triggered.connect(self.stop)
        play_menu.addAction(stop_action)

        stop_action = QtGui.QAction("Stop", self)
        stop_action.triggered.connect(self.stop)
        play_menu.addAction(stop_action)
        
        # Add OCIO controls + Viewer Dropdown to Menu Bar (Corner Widget)
        if self.color_manager.config:
            ocio_combo_style = """
                QComboBox {
                    background-color: #333;
                    color: #ddd;
                    border: 1px solid #555;
                    border-radius: 3px;
                    padding: 2px 5px;
                    min-width: 120px;
                }
                QComboBox::drop-down { border: none; }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 4px solid #aaa;
                    margin-right: 5px;
                }
                QComboBox QAbstractItemView {
                    background-color: #333;
                    color: #ddd;
                    selection-background-color: #555;
                }
            """
            ocio_btn_style = """
                QPushButton {
                    background-color: #333;
                    color: #ddd;
                    border: 1px solid #555;
                    border-radius: 3px;
                    padding: 3px 10px;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #0078d4;
                    border-color: #0078d4;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #444;
                }
            """

            # OCIO toggle button
            self.ocio_btn = QtWidgets.QPushButton("OCIO")
            self.ocio_btn.setCheckable(True)
            self.ocio_btn.setChecked(self.color_manager.ocio_enabled)
            self.ocio_btn.setStyleSheet(ocio_btn_style)
            self.ocio_btn.toggled.connect(self._toggle_ocio_enabled)
            vc_layout.addWidget(self.ocio_btn)

            # Input colorspace
            in_lbl = QtWidgets.QLabel("In:")
            in_lbl.setStyleSheet("color: #aaa;")
            vc_layout.addWidget(in_lbl)
            self.ocio_input_combo = QtWidgets.QComboBox()
            self.ocio_input_combo.addItems(self.color_manager.input_choices)
            if self.color_manager.input_cs:
                self.ocio_input_combo.setCurrentText(self.color_manager.input_cs)
            self.ocio_input_combo.currentTextChanged.connect(self._on_ocio_changed)
            self.ocio_input_combo.setStyleSheet(ocio_combo_style)
            vc_layout.addWidget(self.ocio_input_combo)

            # Output colorspace
            out_lbl = QtWidgets.QLabel("Out:")
            out_lbl.setStyleSheet("color: #aaa;")
            vc_layout.addWidget(out_lbl)
            self.ocio_output_combo = QtWidgets.QComboBox()
            self.ocio_output_combo.addItems(self.color_manager.output_choices)
            if self.color_manager.output_cs:
                self.ocio_output_combo.setCurrentText(self.color_manager.output_cs)
            self.ocio_output_combo.currentTextChanged.connect(self._on_ocio_changed)
            self.ocio_output_combo.setStyleSheet(ocio_combo_style)
            vc_layout.addWidget(self.ocio_output_combo)

        self.menuBar().setCornerWidget(self.viewer_container, QtCore.Qt.Corner.TopRightCorner)

    def _load_ocio_config_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open OCIO Config", "", "OCIO Files (*.ocio);;All Files (*.*)")
        if path:
            try:
                os.environ['OCIO'] = path
                self.color_manager = ColorManager() # Reload
                self._update_ocio_ui()
                self._show_frame(self.current_index)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load config: {e}")

    def _update_ocio_ui(self):
        if not self.color_manager.config: return
        # Update combo boxes if they exist
        if hasattr(self, 'ocio_input_combo'):
            self.ocio_input_combo.clear()
            self.ocio_input_combo.addItems(self.color_manager.input_choices)
            if self.color_manager.input_cs:
                self.ocio_input_combo.setCurrentText(self.color_manager.input_cs)
                
        if hasattr(self, 'ocio_output_combo'):
            self.ocio_output_combo.clear()
            self.ocio_output_combo.addItems(self.color_manager.output_choices)
            if self.color_manager.output_cs:
                self.ocio_output_combo.setCurrentText(self.color_manager.output_cs)
                
        if hasattr(self, 'ocio_btn'):
            self.ocio_btn.setChecked(self.color_manager.ocio_enabled)


    def _on_viewer_changed(self, text):
        if not text: return
        if text != self.color_manager.output_cs:
            self.color_manager.output_cs = text
            self.color_manager.rebuild_processor()
            self._sync_ocio_to_loader()  # Re-process cached frames
            if self.core.frame_count():
                self._show_frame(self.current_index)
            self._save_prefs()
            
            idx = self.ocio_output_combo.findText(text)
            if idx >= 0:
                self.ocio_output_combo.blockSignals(True)
                self.ocio_output_combo.setCurrentIndex(idx)
                self.ocio_output_combo.blockSignals(False)

    def _on_ocio_changed(self, *_):
        if not self.color_manager.config: return
        
        in_cs = self.ocio_input_combo.currentText()
        out_cs = self.ocio_output_combo.currentText()
        
        if in_cs and in_cs != self.color_manager.input_cs:
            self.color_manager.input_cs = in_cs
            
        if out_cs and out_cs != self.color_manager.output_cs:
            self.color_manager.output_cs = out_cs
            idx = self.viewer_combo.findText(out_cs)
            if idx >= 0:
                self.viewer_combo.blockSignals(True)
                self.viewer_combo.setCurrentIndex(idx)
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
        
        # Update both primary and compare loaders
        self.core.loader.set_ocio_params(enabled, input_cs, output_cs, config_path)
        if hasattr(self, 'core_b'):
            self.core_b.loader.set_ocio_params(enabled, input_cs, output_cs, config_path)
        
        # Clear cache since cached frames have old OCIO baked in
        with self.core.cache_lock:
            self.core.cache.clear()
            self.core.loader.clear_pending()
        if hasattr(self, 'core_b'):
            with self.core_b.cache_lock:
                self.core_b.cache.clear()
                self.core_b.loader.clear_pending()

    def _on_exp_slider(self, val: int):
        float_val = val / 10.0
        if self.exp_spin.value() != float_val:
            self.exp_spin.blockSignals(True)
            self.exp_spin.setValue(float_val)
            self.exp_spin.blockSignals(False)
            self._on_exposure_changed(float_val)

    def _on_exp_spin(self, val: float):
        slider_val = int(val * 10)
        if self.exp_slider.value() != slider_val:
            self.exp_slider.blockSignals(True)
            self.exp_slider.setValue(slider_val)
            self.exp_slider.blockSignals(False)
        self._on_exposure_changed(val)

    def _on_gam_slider(self, val: int):
        float_val = val / 10.0
        if self.gam_spin.value() != float_val:
            self.gam_spin.blockSignals(True)
            self.gam_spin.setValue(float_val)
            self.gam_spin.blockSignals(False)
            self._on_gamma_changed(float_val)

    def _on_gam_spin(self, val: float):
        slider_val = int(val * 10)
        if self.gam_slider.value() != slider_val:
            self.gam_slider.blockSignals(True)
            self.gam_slider.setValue(slider_val)
            self.gam_slider.blockSignals(False)
        self._on_gamma_changed(val)

    def _on_exposure_changed(self, val: float):
        self.exposure = float(val)
        if self.core.frame_count():
            self._show_frame(self.current_index)
        self._save_prefs()

    def _on_gamma_changed(self, val: float):
        self.gamma = float(val)
        if self.core.frame_count():
            self._show_frame(self.current_index)
        self._save_prefs()

    def _toggle_play_pause(self):
        """Single click on viewport: toggle play/pause."""
        if self.playing:
            self.pause()
        else:
            self.play()

    def _reset_exposure(self):
        """Click Exp: label → reset exposure to 0.0."""
        self.exposure = 0.0
        self.exp_slider.blockSignals(True)
        self.exp_slider.setValue(0)
        self.exp_slider.blockSignals(False)
        self.exp_spin.blockSignals(True)
        self.exp_spin.setValue(0.0)
        self.exp_spin.blockSignals(False)
        if self.core.frame_count():
            self._show_frame(self.current_index)
        self._save_prefs()

    def _reset_gamma(self):
        """Click Gam: label → reset gamma to 1.0."""
        self.gamma = 1.0
        self.gam_slider.blockSignals(True)
        self.gam_slider.setValue(10)  # 10 = 1.0 * 10
        self.gam_slider.blockSignals(False)
        self.gam_spin.blockSignals(True)
        self.gam_spin.setValue(1.0)
        self.gam_spin.blockSignals(False)
        if self.core.frame_count():
            self._show_frame(self.current_index)
        self._save_prefs()

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
            with open(_PREFS_PATH, 'r', encoding='utf-8') as f:
                self.prefs = json.load(f)
            
            # Map legacy/flat keys to self.prefs if needed (or just use them)
            # We continue to use attributes for some runtime state
            self._prefs_input_cs = self.prefs.get('ocio_input')
            self._prefs_output_cs = self.prefs.get('ocio_output')
            self._prefs_ocio_enabled = self.prefs.get('ocio_enabled', True)
            self.exposure = float(self.prefs.get('exposure', 0.0))
            self.gamma = float(self.prefs.get('gamma', 1.0))
            self.compare_offset = int(self.prefs.get('compare_offset', 0))
            
            # Apply cache size if present
            if 'cache_size' in self.prefs:
                # We can't apply it here easily because self.core might not be fully init or we want to do it later.
                # Actually getattr(self.core) in init handles defaults. 
                # We should apply it after core init.
                pass
        except Exception:
            self.prefs = {}

    def _save_prefs(self):
        try:
            # Update prefs with current runtime state
            self.prefs['ocio_input'] = self.color_manager.input_cs
            self.prefs['ocio_output'] = self.color_manager.output_cs
            self.prefs['ocio_enabled'] = self.color_manager.ocio_enabled
            self.prefs['exposure'] = self.exposure
            self.prefs['gamma'] = self.gamma
            self.prefs['compare_offset'] = getattr(self, 'compare_offset', 0)
            
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
            # 1. Cache
            if 'cache_size' in self.prefs:
                self._apply_cache_capacity(int(self.prefs['cache_size']))
            
            # 2. Defaults (applied on next load)
            
            self._save_prefs()

    # ---------- Core Actions ----------
    def load_media(self, path: str):
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
            # Videos generally shouldn't prefetch frames
            self.core.prefetch_enabled = False
        else:
            self.fps_edit.setDisabled(False)
            self.core.prefetch_enabled = True
            
        # Apply OCIO Defaults based on type
        ext = os.path.splitext(path)[1].lower()
        def_key = None
        if ext in ('.exr', '.sxr', '.dpx', '.cin'): # Image sequences
            def_key = 'exr'
        elif ext in ('.mov', '.mp4', '.avi', '.mkv', '.webm'): # Videos
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

        # Sync OCIO params to background loader
        self._sync_ocio_to_loader()
        
        self.current_index = 0
        self.frame_slider.setMaximum(max(0, self.core.frame_count() - 1))
        self._configure_frame_slider_ticks()
        
        # Reset viewport state to force auto-fit when frame loads
        self.viewport._last_shape = None
        self._show_frame(0)
        
        self._status_base = f"Loaded: {path}"
        self._update_status(self._status_base)
        self._update_timer_interval()
        
        # Auto-play on load as requested
        self.play()


    def _show_frame(self, index: int):
        frame_raw = self.core.get_frame(index)
        
        # If cache miss, schedule polling
        if frame_raw is None:
            self._target_frame_index = index
            if not self._pending_frame_timer.isActive():
                self._pending_frame_timer.start()
            return
        else:
            # Cache hit: stop polling if we reached target
            if index == self._target_frame_index:
                self._pending_frame_timer.stop()
                self._target_frame_index = -1

        # Process frame through color pipeline (always returns float32 0-1)
        frame = self.color_manager.process(frame_raw, self.exposure, self.gamma)

        # Display frame
        self.viewport.set_frame(frame)
        self.frame_info.setText(f"Frame: {index + 1}/{self.core.frame_count()}")
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(index)
        self.frame_slider.blockSignals(False)
        self.current_index = index

        if self.compare_loaded and self.core_b.frame_count() > 0:
            idx_b = max(0, min(self.core_b.frame_count() - 1, index + int(getattr(self, 'compare_offset', 0))))
            cframe_raw = self.core_b.get_frame(idx_b)
            
            if cframe_raw is not None:
                cframe = self.color_manager.process(cframe_raw, self.exposure, self.gamma)
            else:
                cframe = None
            
            if self.side_by_side:
                self.viewport_b.show()
                if cframe is not None:
                    self.viewport_b.set_frame(cframe)
            elif self.wipe_mode:
                self.viewport_b.hide()
                if cframe is not None:
                    self.viewport.composite_wipe(frame, cframe, self.wipe_slider.value()/1000.0)


    def _check_pending_frame(self):
        """Called by timer to check if pending frame is ready."""
        if self._target_frame_index >= 0:
            frame = self.core.get_frame(self._target_frame_index)
            if frame is not None:
                self._show_frame(self._target_frame_index) # This will stop timer


    def _advance_frame(self):
        if self.core.frame_count() == 0:
            return
        # Video: drive frame index by elapsed time for realtime playback
        if self.core.media and self.core.media.type == 'video' and self._elapsed_timer is not None:
            fps = self.core.media_fps() or 24.0
            elapsed_ms = self._elapsed_timer.elapsed()
            frames_should_be = int((elapsed_ms / 1000.0) * fps)
            target = self._play_start_index + frames_should_be
            if target >= self.core.frame_count():
                if self.loop:
                    target = target % max(1, self.core.frame_count())
                    # reset anchor to keep elapsed mapping stable over loops
                    self._play_start_index = target
                    self._elapsed_timer.restart()
                else:
                    self.pause(); return
            if target != self.current_index:
                self._show_frame(target)
            return
        # Images/sequences: simple step
        nxt = self.current_index + 1
        if nxt >= self.core.frame_count():
            if self.loop:
                nxt = 0
            else:
                self.pause(); return
        self._show_frame(nxt)

    def seek(self, index: int):
        idx = int(index)
        if 0 <= idx < self.core.frame_count():
            self._show_frame(idx)

    def play(self):
        if self.playing:
            return
        self.playing = True
        # Videos use a faster heartbeat + elapsed-time sync
        if self.core.media and self.core.media.type == 'video':
            self._elapsed_timer = QtCore.QElapsedTimer()
            self._elapsed_timer.start()
            self._play_start_index = self.current_index
            self.timer.start(10)  # 10ms heartbeat for smoother sync
        else:
            self.timer.start(self._interval_ms())
        self._status_base = "Playing"
        self._update_status(self._status_base)

    def pause(self):
        if not self.playing:
            return
        self.playing = False
        self.timer.stop()
        self._elapsed_timer = None
        self._status_base = "Paused"
        self._update_status(self._status_base)

    def stop(self):
        self.pause()
        self.seek(0)
        self._elapsed_timer = None
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

    def _update_status(self, msg: str):
        self.status.showMessage(msg)

    def _refresh_status_metrics(self):
        if not self.core.media:
            self.status.showMessage(self._status_base)
            return
        cached, cap, pct = self.core.cache_stats()
        fps = self.core.media_fps() or 24.0
        tc = self._format_timecode(self.current_index, fps)
        self.status.showMessage(f"{self._status_base} | Cache {cached}/{cap} ({pct:.0f}%) | {tc}")

    def _format_timecode(self, frame: int, fps: float) -> str:
        if fps <= 0:
            return "--:--:--:--"
        total_seconds = int(frame / fps)
        ff = int(frame % fps)
        hh = total_seconds // 3600
        mm = (total_seconds % 3600) // 60
        ss = total_seconds % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    # ---------- Cache capacity controls ----------
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
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Media", "", "Media Files (*.*)")
        if path:
            self.load_media(path)

    def _open_file_compare(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Compare Media", "", "Media Files (*.*)")
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
        if mode == 'side' and self.side_by_side:
            mode = 'single'
        elif mode == 'wipe' and self.wipe_mode:
            mode = 'single'
            
        # Reset modes
        self.side_by_side = False
        self.wipe_mode = False
        if mode == 'single':
            self.side_action.setChecked(False)
            self.wipe_action.setChecked(False)
            self.viewport_b.hide()
            self._wipe_row.hide()
        elif mode == 'side':
            self.side_action.setChecked(True)
            self.wipe_action.setChecked(False)
            self.side_by_side = True
            self.viewport_b.show()
            self._wipe_row.hide()
            if self.compare_loaded and self.core.frame_count():
                self._show_frame(self.current_index)
        elif mode == 'wipe':
            self.wipe_action.setChecked(True)
            self.side_action.setChecked(False)
            self.wipe_mode = True
            self.viewport_b.hide()
            self._wipe_row.show()
        self._update_wipe()

    def _update_wipe(self):
        if not self.wipe_mode:
            return
        ratio = self.wipe_slider.value() / 1000.0
        if self.compare_loaded and self.core_b.frame_count() > 0:
            # obtain current frames for composite (reuse cached)
            base_raw = self.core.get_frame(self.current_index)
            idx_b = max(0, min(self.core_b.frame_count()-1, self.current_index + int(getattr(self, 'compare_offset', 0))))
            top_raw = self.core_b.get_frame(idx_b)
            
            if base_raw is not None:
                base = self.color_manager.process(base_raw, self.exposure, self.gamma)
            else:
                base = None
            if top_raw is not None:
                top = self.color_manager.process(top_raw, self.exposure, self.gamma)
            else:
                top = None
            
            if base is not None and top is not None:
                self.viewport.composite_wipe(base, top, ratio)

    # ---------- Folder Navigation (Page Up / Page Down) ----------
    _MEDIA_EXTS = {'.mov', '.mp4', '.avi', '.mkv', '.mxf', '.webm', '.exr'}

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

        media_files = []
        seen_seq = set()  # track EXR sequence base names to avoid duplicates
        for name in entries:
            ext = os.path.splitext(name)[1].lower()
            if ext not in self._MEDIA_EXTS:
                continue
            full = os.path.join(folder, name)
            if ext == '.exr':
                # Group EXR sequences: only add the first file per sequence
                # Strip frame numbers to get base name
                import re
                base = re.sub(r'[\._]\d{3,}(?=\.exr$)', '', name, flags=re.IGNORECASE)
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
            if self.core.media.type == 'sequence' and os.path.normcase(os.path.dirname(f)) == os.path.normcase(folder) and f.lower().endswith('.exr'):
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

    # ---------- Keyboard Shortcuts ----------
    def keyPressEvent(self, event: QtGui.QKeyEvent):  # type: ignore[override]
        key = event.key()
        if key == QtCore.Qt.Key.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen(False)
        elif key == QtCore.Qt.Key.Key_Space:
            self.pause() if self.playing else self.play()
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
        elif key == QtCore.Qt.Key.Key_O and hasattr(self, 'ocio_enable_btn'):
            self.ocio_enable_btn.toggle()
        elif key == QtCore.Qt.Key.Key_Right:
            self.seek(self.current_index + 1)
        elif key == QtCore.Qt.Key.Key_Left:
            self.seek(self.current_index - 1)
        elif key == QtCore.Qt.Key.Key_Home:
            self.seek(0)
        elif key == QtCore.Qt.Key.Key_End:
            self.seek(self.core.frame_count() - 1)

        # --- Gamma Shortcuts ([ / ]) ---
        elif key == QtCore.Qt.Key.Key_BracketLeft:
            self.gam_slider.setValue(self.gam_slider.value() - 10) # -0.1
        elif key == QtCore.Qt.Key.Key_BracketRight:
            self.gam_slider.setValue(self.gam_slider.value() + 10) # +0.1
            
        # --- Exposure Shortcuts (- / =) ---
        elif key == QtCore.Qt.Key.Key_Minus and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.exp_slider.setValue(self.exp_slider.value() - 25) # -0.25
        elif key in (QtCore.Qt.Key.Key_Equal, QtCore.Qt.Key.Key_Plus) and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.exp_slider.setValue(self.exp_slider.value() + 25) # +0.25

        # --- Zoom Shortcuts (Ctrl + / -) ---
        elif key in (QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Equal) and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.viewport.set_zoom(self.viewport._zoom * 1.1)
            self._update_zoom_label()
        elif key in (QtCore.Qt.Key.Key_Minus, QtCore.Qt.Key.Key_Underscore) and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.viewport.set_zoom(self.viewport._zoom / 1.1)
            self._update_zoom_label()
        elif key == QtCore.Qt.Key.Key_F:
            # Fullscreen toggle via F; Shift+F for fit
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.viewport.fit_to_window()
                self._update_zoom_label()
            else:
                self._toggle_fullscreen(not self.fullscreen)
        elif key == QtCore.Qt.Key.Key_PageDown:
            self._navigate_folder(1)   # Next media in folder
        elif key == QtCore.Qt.Key.Key_PageUp:
            self._navigate_folder(-1)  # Previous media in folder
        else:
            event.ignore()

    def _toggle_fullscreen(self, enable: bool):
        self.fullscreen = enable
        if enable:
            # Save UI state before hiding
            self._pre_fullscreen_state = {
                'menu_visible': self.menuBar().isVisible(),
                'status_visible': self.statusBar().isVisible(),
                'hud_visible': self.hud_container.isVisible(),
            }
            self.menuBar().hide()
            self.statusBar().hide()
            self.hud_container.hide()
            if hasattr(self, '_wipe_row') and self._wipe_row.isVisible():
                self._pre_fullscreen_state['wipe_visible'] = True
                self._wipe_row.hide()
            self.showFullScreen()
        else:
            self.showNormal()
            state = getattr(self, '_pre_fullscreen_state', {})
            if state.get('menu_visible', True):
                self.menuBar().show()
            if state.get('status_visible', True):
                self.statusBar().show()
            if state.get('hud_visible', True):
                self.hud_container.show()
            if state.get('wipe_visible', False) and hasattr(self, '_wipe_row'):
                self._wipe_row.show()

    def closeEvent(self, event):
        self._save_prefs()
        super().closeEvent(event)

    # ---------- Run ----------
    def run(self):
        self.show()
        sys.exit(QtWidgets.QApplication.instance().exec())

