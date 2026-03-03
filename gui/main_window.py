"""Enhanced PyQt6 main window for VFXPlayer with compare & advanced controls."""

import sys, os, json
from typing import Optional, Tuple
from PyQt6 import QtWidgets, QtGui, QtCore
from gui.vispy_viewport import VispyViewport
from core.color_manager import ColorManager
from gui.settings_dialog import SettingsDialog


class PlayheadSlider(QtWidgets.QSlider):
    """Horizontal slider with playhead line and cached-frame indicators."""
    def __init__(self, *args, **kwargs):
        super().__init__(QtCore.Qt.Orientation.Horizontal, *args, **kwargs)
        self.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.setTickInterval(1)
        self.setSingleStep(1)
        self._cached_indices = set()  # Set of cached frame indices
        self._show_cached = True  # Whether to show cached frame indicators
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #333;
                height: 4px;
                background: #111;
                margin: 0px 0;
            }
            QSlider::sub-page:horizontal {
                background: #4a90e2;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 1px solid #333;
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover {
                background: #4a90e2;
            }
        """)

    def set_cached_indices(self, indices: set):
        """Update the set of cached frame indices and repaint."""
        self._cached_indices = indices
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
        
        # --- Draw cached frame indicators (green bar at bottom of groove) ---
        if self._show_cached and self._cached_indices and rng > 0:
            cache_pen = QtGui.QPen(QtGui.QColor("#2ecc71"))  # Green
            cache_pen.setWidth(2)
            p.setPen(cache_pen)
            groove_y = self.height() // 2 + 3  # Just below groove center
            for idx in self._cached_indices:
                if self.minimum() <= idx <= self.maximum():
                    ratio = (idx - self.minimum()) / rng
                    cx = margin + int(ratio * track_w)
                    p.drawLine(cx, groove_y, cx, groove_y + 3)
        
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



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.setWindowTitle("VFXPlayer")
        self.resize(1280, 800)
        self.setMinimumSize(800, 500)

        # Set Window Icon
        icon_path = os.path.join(_APP_ROOT, "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        elif os.path.exists(os.path.join(_APP_ROOT, "logo.ico")):
            self.setWindowIcon(QtGui.QIcon(os.path.join(_APP_ROOT, "logo.ico")))

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
            self.viewport.pixel_probe_hover.connect(self._on_pixel_probe)
            self.viewport_b.pixel_probe_hover.connect(self._on_pixel_probe)
            self.viewport.stroke_finished.connect(self._on_stroke_finished)
            self.viewport_b.stroke_finished.connect(self._on_stroke_finished)
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
        self.annotations = {} # mapping frame index -> list of stroke dicts
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
        self.playback_speed = 1.0
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
        """Construct the bottom Heads-Up Display for controls (Nuke-style)."""
        # Main HUD layout: Vertical (Slider Top, Controls Bottom)
        self.hud_layout.setContentsMargins(0, 0, 0, 0)
        self.hud_layout.setSpacing(0)
        
        # We need to rebuild the hud_container's layout to be Vertical if it was horizontal
        # But self.hud_layout is already defined as QHBoxLayout in __init__?
        # Let's check __init__. 
        # In __init__: self.hud_layout = QtWidgets.QHBoxLayout(self.hud_container)
        # We need to change this to QVBoxLayout or add a container.
        # Since we can't easily change the layout type of an existing widget without re-creating it,
        # let's reparent the current layout or just work with what we have? 
        # Actually, it's better to clear the existing layout item in __init__ or just modify it here if possible.
        # But `replace_file_content` on `_build_hud` won't change `__init__`.
        # So I will treat `self.hud_layout` as the *container* interaction. 
        # Wait, if `self.hud_layout` is QHBoxLayout, I can't put a vertical structure effectively unless I add a wrapper.
        
        # Let's clean up `self.hud_container` layout.
        # We'll create a new strict layout inside this method.
        
        # Remove old layout if it exists (standard PyQt trick)
        if self.hud_container.layout():
            QtWidgets.QWidget().setLayout(self.hud_container.layout()) # Re-parent to dummy to delete?
            # Or just delete the implementation? 
            # Safest is to just make a new widget structure inside the existing generic container if I can't change __init__.
            # But I CAN change __init__ in a separate tool call. 
            # For now, let's assume I can't change __init__ easily in this single block.
            # I will assume I can just delete the old layout or ignore it? No.
            pass

        # Use a local widget to hold everything if needed, but let's try to update __init__ too if we can.
        # Actually, let's just use the existing `self.hud_container`.
    


    def _build_hud(self):
        """Construct the bottom Heads-Up Display for controls (Nuke-style)."""
        # Re-orient to Vertical: Slider (Row 1) | Controls (Row 2)
        
        # --- ROW 1: Timeline Slider ---
        slider_container = QtWidgets.QWidget()
        slider_container.setFixedHeight(24)
        slider_container.setStyleSheet("background-color: #222; border-bottom: 1px solid #333;")
        slider_layout = QtWidgets.QHBoxLayout(slider_container)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        
        self.frame_slider = PlayheadSlider() # User custom class
        self.frame_slider.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.frame_slider.valueChanged.connect(self._show_frame)
        
        slider_layout.addWidget(self.frame_slider)
        self.hud_layout.addWidget(slider_container)
        
        # --- ROW 2: Transport Controls ---
        controls_container = QtWidgets.QWidget()
        controls_container.setFixedHeight(36)
        controls_container.setStyleSheet("background-color: #1a1a1a;")
        controls_layout = QtWidgets.QHBoxLayout(controls_container)
        controls_layout.setContentsMargins(10, 2, 10, 2)
        controls_layout.setSpacing(8)
        
        # Styles
        btn_style = """
            QPushButton {
                background-color: transparent; 
                color: #ccc; 
                border: none; 
                font-size: 14px; 
                padding: 4px;
            }
            QPushButton:hover { color: white; background-color: #333; border-radius: 3px; }
            QPushButton:pressed { color: #aaa; }
        """
        input_style = """
            QLineEdit {
                background-color: #111; 
                color: #ddd; 
                border: 1px solid #333; 
                border-radius: 3px; 
                padding: 2px;
                selection-background-color: #4a90e2;
                font-family: Consolas, monospace;
            }
            QLineEdit:focus { border-color: #555; }
        """
        
        # 1. Frame Range (Left) - In/Out
        self.range_start_edit = QtWidgets.QLineEdit("0")
        self.range_start_edit.setFixedWidth(40)
        self.range_start_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.range_start_edit.setStyleSheet(input_style)
        self.range_start_edit.editingFinished.connect(self._update_range)
        
        self.range_end_edit = QtWidgets.QLineEdit("100")
        self.range_end_edit.setFixedWidth(40)
        self.range_end_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.range_end_edit.setStyleSheet(input_style)
        self.range_end_edit.editingFinished.connect(self._update_range)
        
        controls_layout.addWidget(QtWidgets.QLabel("In:"))
        controls_layout.addWidget(self.range_start_edit)
        controls_layout.addWidget(QtWidgets.QLabel("Out:"))
        controls_layout.addWidget(self.range_end_edit)
        
        controls_layout.addStretch(1) # Spacer
        
        # 2. Transport Buttons (Center)
        # First Frame
        self.btn_first = QtWidgets.QPushButton("|<")
        self.btn_first.setFixedSize(30, 28)
        self.btn_first.setStyleSheet(btn_style)
        self.btn_first.setToolTip("Go to First Frame")
        self.btn_first.clicked.connect(self._go_to_start)
        controls_layout.addWidget(self.btn_first)
        
        # Prev Frame
        self.btn_prev = QtWidgets.QPushButton("<")
        self.btn_prev.setFixedSize(30, 28)
        self.btn_prev.setStyleSheet(btn_style)
        self.btn_prev.setToolTip("Previous Frame")
        self.btn_prev.clicked.connect(lambda: self.seek(self.current_index - 1))
        controls_layout.addWidget(self.btn_prev)
        
        # Play/Pause
        self.btn_play = QtWidgets.QPushButton("▶") # Toggles icon
        self.btn_play.setFixedSize(30, 28)
        self.btn_play.setStyleSheet(btn_style)
        self.btn_play.setCheckable(True)
        self.btn_play.setToolTip("Play/Pause")
        self.btn_play.clicked.connect(self._toggle_play_button)
        controls_layout.addWidget(self.btn_play)
        
        # Next Frame
        self.btn_next = QtWidgets.QPushButton(">")
        self.btn_next.setFixedSize(30, 28)
        self.btn_next.setStyleSheet(btn_style)
        self.btn_next.setToolTip("Next Frame")
        self.btn_next.clicked.connect(lambda: self.seek(self.current_index + 1))
        controls_layout.addWidget(self.btn_next)
        
        # Last Frame
        self.btn_last = QtWidgets.QPushButton(">|")
        self.btn_last.setFixedSize(30, 28)
        self.btn_last.setStyleSheet(btn_style)
        self.btn_last.setToolTip("Go to Last Frame")
        self.btn_last.clicked.connect(self._go_to_end)
        controls_layout.addWidget(self.btn_last)
        
        # Current Frame Input
        self.curr_frame_edit = QtWidgets.QLineEdit("0")
        self.curr_frame_edit.setFixedWidth(50)
        self.curr_frame_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.curr_frame_edit.setStyleSheet("""
            QLineEdit {
                background-color: #222;
                color: #e0e0e0;
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 2px;
                font-size: 13px;
            }
        """)
        self.curr_frame_edit.returnPressed.connect(self._on_frame_input)
        controls_layout.addWidget(self.curr_frame_edit)
        
        controls_layout.addStretch(1) # Spacer
        
        # --- Drawing Tools ---
        self.btn_draw = QtWidgets.QPushButton("Draw")
        self.btn_draw.setCheckable(True)
        self.btn_draw.setFixedSize(60, 28)
        self.btn_draw.setToolTip("Toggle Annotation Mode")
        self.btn_draw.setStyleSheet("""
            QPushButton { background: transparent; color: #ccc; font-size: 13px; border: 1px solid #444; border-radius: 4px; font-weight: bold; }
            QPushButton:checked { color: #fff; background: #c62828; border: 1px solid #ff5252; }
            QPushButton:hover { background: #333; }
        """)
        self.btn_draw.clicked.connect(self._toggle_draw_mode)
        controls_layout.addWidget(self.btn_draw)
        
        self.draw_color_combo = QtWidgets.QComboBox()
        self.draw_color_combo.addItems(["Red", "Green", "Blue", "Yellow"])
        self.draw_color_combo.setStyleSheet("""
            QComboBox { background: #222; color: #ddd; border: 1px solid #444; border-radius: 3px; padding: 2px 5px; }
            QComboBox::drop-down { border: none; }
        """)
        self.draw_color_combo.currentIndexChanged.connect(self._change_draw_color)
        controls_layout.addWidget(self.draw_color_combo)
        
        self.btn_clear_draw = QtWidgets.QPushButton("Clear")
        self.btn_clear_draw.setFixedSize(45, 28)
        self.btn_clear_draw.setToolTip("Clear Annotations for Current Frame")
        self.btn_clear_draw.setStyleSheet("""
            QPushButton { background: transparent; color: #ccc; font-size: 13px; border: 1px solid #444; border-radius: 4px; }
            QPushButton:hover { background: #333; color: white; }
        """)
        self.btn_clear_draw.clicked.connect(self._clear_annotations)
        controls_layout.addWidget(self.btn_clear_draw)
        
        controls_layout.addSpacing(20)
        
        # 3. Right Controls: Channel, FPS, Loop, Gamma/Exp (Compact)
        self.lbl_channel = QtWidgets.QLabel("RGB")
        self.lbl_channel.setToolTip("Current Channel (Hotkeys: R, G, B, A, C)")
        self.lbl_channel.setStyleSheet("color: #4a90e2; font-weight: bold; font-size: 14px; padding-right: 10px;")
        controls_layout.addWidget(self.lbl_channel)
        
        # Pixel Probe Label
        self.lbl_probe = QtWidgets.QLabel("")
        self.lbl_probe.setMinimumWidth(250)
        self.lbl_probe.setStyleSheet("color: #aaa; font-family: consolas, monospace; font-size: 12px; padding-right: 10px;")
        controls_layout.addWidget(self.lbl_probe)
        
        # FPS
        controls_layout.addWidget(QtWidgets.QLabel("FPS:"))
        self.fps_edit = QtWidgets.QLineEdit("24.0")
        self.fps_edit.setFixedWidth(40)
        self.fps_edit.setStyleSheet(input_style)
        self.fps_edit.editingFinished.connect(self._update_timer_interval)
        controls_layout.addWidget(self.fps_edit)
        
        controls_layout.addSpacing(10)
        
        # Loop Checkbox (Icon style)
        self.loop_btn = QtWidgets.QPushButton("Loop")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        self.loop_btn.setFixedSize(60, 28)
        self.loop_btn.setToolTip("Loop Playback")
        self.loop_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #ccc; font-size: 13px; border: none; font-weight: bold; }
            QPushButton:checked { color: #4a90e2; }
            QPushButton:hover { color: white; }
        """)
        self.loop_btn.toggled.connect(self._toggle_loop)
        controls_layout.addWidget(self.loop_btn)

        # --- Playback Speed Control ---
        self.speed_btn = QtWidgets.QPushButton("1x")
        self.speed_btn.setFixedSize(50, 28)
        self.speed_btn.setToolTip("Playback Speed. Click to change.")
        self.speed_btn.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                color: #ccc; 
                font-size: 13px; 
                border: 1px solid #444; 
                border-radius: 4px; 
                font-weight: bold;
                font-family: consolas, monospace;
            }
            QPushButton:hover { background: #333; color: white; border: 1px solid #666; }
        """)
        
        # Create Menu for speed selection
        speed_menu = QtWidgets.QMenu(self)
        speed_menu.setStyleSheet("""
            QMenu { background: #222; color: #ddd; border: 1px solid #444; }
            QMenu::item:selected { background: #444; }
        """)
        
        self.speed_speeds = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0]
        for s in self.speed_speeds:
            act = speed_menu.addAction(f"{s}x")
            act.triggered.connect(lambda checked, val=s: self._on_speed_changed(val))
        
        self.speed_btn.setMenu(speed_menu)
        controls_layout.addWidget(self.speed_btn)

        controls_layout.addSpacing(10)

        controls_layout.addSpacing(10)

        # Bottom HUD now focuses on playback/timeline.
        # Exposure and Gamma have moved to the top bar.

        self.hud_layout.addWidget(controls_container)



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
        vc_layout.setContentsMargins(10, 0, 5, 0) # Less horizontal padding
        vc_layout.setSpacing(6) # Tighter spacing
        
        # --- NEW GPU GAIN / GAMMA SLIDERS ---
        # Exposure (Gain)
        self.exp_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.exp_slider.setRange(-8000, 8000) # Maps to -8.0 to 8.0 stop
        self.exp_slider.setValue(int(self.exposure * 1000))
        self.exp_slider.setFixedWidth(80) # Narrower
        self.exp_slider.setToolTip("Exposure (f-stops). Click 'E' to reset.")
        self.exp_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 4px;
                background: #333;
                margin: 2px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #bbb;
                border: 1px solid #777;
                width: 10px;
                height: 14px;
                margin: -6px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #ddd;
            }
        """)
        
        self.lbl_exp_val = QtWidgets.QLabel(f"{self.exposure:+.2f}")
        self.lbl_exp_val.setFixedWidth(35)
        self.lbl_exp_val.setStyleSheet("color: #ccc; font-family: consolas, monospace; font-size: 11px;")
        
        self.exp_slider.valueChanged.connect(self._on_exposure_changed)
        
        exp_box = QtWidgets.QHBoxLayout()
        exp_box.setSpacing(2)
        btn_e = QtWidgets.QPushButton("E")
        btn_e.setFixedSize(16, 16)
        btn_e.setStyleSheet("background: #444; color: white; border-radius: 8px; font-weight: bold; font-size: 9px;")
        btn_e.clicked.connect(self._reset_exposure)
        exp_box.addWidget(btn_e)
        exp_box.addWidget(self.exp_slider)
        exp_box.addWidget(self.lbl_exp_val)
        vc_layout.addLayout(exp_box)
        
        # Gamma
        self.gam_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.gam_slider.setRange(100, 4000) # Maps to 0.1 to 4.0
        self.gam_slider.setValue(int(self.gamma * 1000))
        self.gam_slider.setFixedWidth(80) # Narrower
        self.gam_slider.setToolTip("Gamma. Click 'G' to reset.")
        self.gam_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 4px;
                background: #333;
                margin: 2px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #bbb;
                border: 1px solid #777;
                width: 10px;
                height: 14px;
                margin: -6px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #ddd;
            }
        """)
        
        self.lbl_gam_val = QtWidgets.QLabel(f"{self.gamma:.2f}")
        self.lbl_gam_val.setFixedWidth(30)
        self.lbl_gam_val.setStyleSheet("color: #ccc; font-family: consolas, monospace; font-size: 11px;")
        
        self.gam_slider.valueChanged.connect(self._on_gamma_changed)
        
        gam_box = QtWidgets.QHBoxLayout()
        gam_box.setSpacing(2)
        btn_g = QtWidgets.QPushButton("G")
        btn_g.setFixedSize(16, 16)
        btn_g.setStyleSheet("background: #444; color: white; border-radius: 8px; font-weight: bold; font-size: 9px;")
        btn_g.clicked.connect(self._reset_gamma)
        gam_box.addWidget(btn_g)
        gam_box.addWidget(self.gam_slider)
        gam_box.addWidget(self.lbl_gam_val)
        vc_layout.addLayout(gam_box)
        
        vc_layout.addSpacing(5)
        
        lbl = QtWidgets.QLabel("V:") # Shortened from "Viewer:"
        lbl.setStyleSheet("color: #888;") 
        vc_layout.addWidget(lbl)
        
        self.viewer_combo = QtWidgets.QComboBox()
        self.viewer_combo.setMinimumWidth(100) # Narrower
        self.viewer_combo.setMaximumWidth(150)
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
            self.ocio_input_combo.setMaximumWidth(120) # Prevent it from pushing menus too far
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
            self.ocio_output_combo.setMaximumWidth(120)
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

    def _on_exposure_changed(self, val: int):
        self.exposure = float(val / 1000.0)
        if hasattr(self, 'lbl_exp_val'):
            self.lbl_exp_val.setText(f"{self.exposure:+.2f}")
            
        # Refresh current frame with new exposure (no cache clear!)
        if self.core.frame_count():
            self._show_frame(self.current_index)
        
        self._save_prefs()

    def _on_gamma_changed(self, val: int):
        self.gamma = float(val / 1000.0)
        if hasattr(self, 'lbl_gam_val'):
            self.lbl_gam_val.setText(f"{self.gamma:.2f}")
            
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
            
        if self.core.frame_count():
            self._show_frame(self.current_index)

    def _on_pixel_probe(self, x: float, y: float):
        if not hasattr(self, 'lbl_probe') or not hasattr(self, 'core') or self.core.frame_count() == 0:
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

    def _toggle_draw_mode(self, enabled: bool):
        self.viewport.is_drawing = enabled
        self.viewport_b.is_drawing = enabled
        if enabled:
            # Init color on first activation
            self._change_draw_color(self.draw_color_combo.currentIndex())
            # Ensure visual is updated
            if self.core.frame_count():
                strokes = self.annotations.get(self.current_index, [])
                self.viewport.set_annotations(strokes)
                if self.side_by_side and hasattr(self, 'viewport_b'):
                    self.viewport_b.set_annotations(strokes)

    def _change_draw_color(self, idx: int):
        colors = {
            0: (1.0, 0.0, 0.0, 1.0), # Red
            1: (0.0, 1.0, 0.0, 1.0), # Green
            2: (0.0, 0.0, 1.0, 1.0), # Blue
            3: (1.0, 1.0, 0.0, 1.0)  # Yellow
        }
        color = colors.get(idx, (1.0, 0.0, 0.0, 1.0))
        self.viewport.draw_color = color
        self.viewport_b.draw_color = color

    def _on_stroke_finished(self, points: list, color: tuple):
        if self.current_index not in self.annotations:
            self.annotations[self.current_index] = []
        
        # Store stroke data
        self.annotations[self.current_index].append({
            'points': points,
            'color': color
        })

    def _clear_annotations(self):
        if self.current_index in self.annotations:
            del self.annotations[self.current_index]
            self.viewport.set_annotations([])
            if self.side_by_side and hasattr(self, 'viewport_b'):
                self.viewport_b.set_annotations([])

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
            
            # Apply cache settings if present
            if 'cache_gb' in self.prefs:
                self.core.set_cache_gb(float(self.prefs['cache_gb']))
            if 'cache_enabled' in self.prefs:
                self.core.cache_enabled = self.prefs['cache_enabled']
            if 'preload_cache' in self.prefs:
                self.core.prefetch_enabled = self.prefs['preload_cache']
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
            self.prefs['cache_gb'] = self.core.cache_gb
            self.prefs['cache_enabled'] = self.core.cache_enabled
            self.prefs['preload_cache'] = self.core.prefetch_enabled
            self.prefs['show_cached_timeline'] = self.prefs.get('show_cached_timeline', True)
            
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
            
            # 4. Show cached in timeline
            self.frame_slider.set_show_cached(self.prefs.get('show_cached_timeline', True))
            
            # 5. Defaults (applied on next load)
            
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

        # Process frame through color pipeline (NumPy CPU)
        frame = self.color_manager.process(frame_raw, self.exposure, self.gamma, self.channel_mode)

        # Display frame
        self.viewport.set_frame(frame)
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(index)
        self.frame_slider.blockSignals(False)
        self.current_index = index
        
        # Apply annotations if drawing is enabled
        if self.btn_draw.isChecked():
            strokes = self.annotations.get(index, [])
            self.viewport.set_annotations(strokes)

        if self.compare_loaded and self.core_b.frame_count() > 0:
            idx_b = max(0, min(self.core_b.frame_count() - 1, index + int(getattr(self, 'compare_offset', 0))))
            cframe_raw = self.core_b.get_frame(idx_b)
            
            if cframe_raw is not None:
                cframe = self.color_manager.process(cframe_raw, self.exposure, self.gamma, self.channel_mode)
            else:
                cframe = None
            
            if self.side_by_side:
                self.viewport_b.show()
                if cframe is not None:
                    self.viewport_b.set_frame(cframe)
                if self.btn_draw.isChecked():
                    self.viewport_b.set_annotations(strokes)
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
        
        fps = (self.core.media_fps() or 24.0) * self.playback_speed
        ms = self._elapsed_timer.elapsed()
        frames = int(ms * fps / 1000.0)
        next_idx = self._play_start_index + frames
            
        # Check against Range Out
        if next_idx > r_out:
            if self.loop:
                next_idx = r_in
                self._elapsed_timer.restart()
                self._play_start_index = r_in
            else:
                next_idx = r_out
                self.pause()
                return # Stop advancement
        
        # Don't re-display the same frame
        if next_idx == self.current_index:
            return
                
        # --- Drop-frame tolerance ---
        # If the target frame isn't cached, try the next sequential frame.
        # This prevents stalling during playback on cache misses.
        frame_raw = self.core.get_frame(next_idx)
        if frame_raw is None:
            # Skip up to 3 frames looking for a cached one
            for skip in range(1, 4):
                alt = next_idx + skip
                if alt > r_out:
                    break
                frame_raw = self.core.get_frame(alt)
                if frame_raw is not None:
                    next_idx = alt
                    break
            if frame_raw is None:
                return  # No cached frame available, wait for next tick

        self.seek(next_idx)


    def seek(self, index: int):
        idx = int(index)
        if 0 <= idx < self.core.frame_count():
            self._show_frame(idx)

    def play(self):
        if self.playing:
            return
        self.playing = True
        
        # Unified elapsed-time playback for all media types
        self._elapsed_timer = QtCore.QElapsedTimer()
        self._elapsed_timer.start()
        self._play_start_index = self.current_index
        
        # 8ms heartbeat (~125fps cap) for smooth frame sync
        self.timer.start(8)
        
        # Aggressive prefetch burst: load next 48 frames immediately
        self.core.burst_prefetch(self.current_index, count=48)
        
        # Update UI
        if hasattr(self, 'btn_play'):
            self.btn_play.blockSignals(True)
            self.btn_play.setChecked(True)
            self.btn_play.setText("||")
            self.btn_play.blockSignals(False)

        self._status_base = "Playing"
        self._update_status(self._status_base)

    def pause(self):
        if not self.playing:
            return
        self.playing = False
        self.timer.stop()
        self._elapsed_timer = None
        
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
        self.status.showMessage(msg)

    def _refresh_status_metrics(self):
        if not self.core.media:
            self.status.showMessage(self._status_base)
            return
        cached, cap, pct, mem_mb = self.core.cache_stats()
        fps = self.core.media_fps() or 24.0
        tc = self._format_timecode(self.current_index, fps)
        if mem_mb > 1024:
            mem_str = f"{mem_mb/1024:.1f}GB"
        else:
            mem_str = f"{mem_mb:.0f}MB"
        self.status.showMessage(f"{self._status_base} | Cache {cached}/{cap} ({pct:.0f}%) {mem_str} | {tc}")
        
        # Update cached frame indicators on timeline
        if self.prefs.get('show_cached_timeline', True):
            self.frame_slider.set_cached_indices(self.core.get_cached_indices())

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
        elif key == QtCore.Qt.Key.Key_C:
            self._set_channel('RGB')
        elif key == QtCore.Qt.Key.Key_R:
            self._set_channel('R')
        elif key == QtCore.Qt.Key.Key_G:
            self._set_channel('G')
        elif key == QtCore.Qt.Key.Key_B:
            self._set_channel('B')
        elif key == QtCore.Qt.Key.Key_A:
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
        
        # --- Playback Navigation (JKL) ---
        elif key == QtCore.Qt.Key.Key_L:
            if not self.playing:
                self.play()
                self._on_speed_changed(1.0)
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
            # For now, J acts as "Play 1x" or we could implement reverse later.
            # Industry JKL: J is reverse, but let's stick to forward/pause for now.
            if not self.playing:
                self.play()
                self._on_speed_changed(1.0) # Placeholder for reverse
        
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
        elif key == QtCore.Qt.Key.Key_U:
            # U key also toggles fullscreen
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

