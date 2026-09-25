"""Shortcuts & Hotkey Reference Dialog for VFX Review Player matching Nuke aesthetics."""

import os
import sys
from PyQt6 import QtWidgets, QtGui, QtCore

SHORTCUTS_DATA = [
    # Category: Playback & Transport
    {
        "category": "Playback & Transport",
        "key": "Space",
        "action": "Play / Pause",
        "desc": "Toggle playback in the forward direction."
    },
    {
        "category": "Playback & Transport",
        "key": "Shift+Space",
        "action": "Play Reverse",
        "desc": "Play clip backward in reverse direction."
    },
    {
        "category": "Playback & Transport",
        "key": "J",
        "action": "Play Reverse (JKL)",
        "desc": "Shuttle backward in reverse."
    },
    {
        "category": "Playback & Transport",
        "key": "K",
        "action": "Pause (JKL)",
        "desc": "Pause playback immediately."
    },
    {
        "category": "Playback & Transport",
        "key": "L",
        "action": "Play Forward / Shuttle",
        "desc": "Play forward; tap repeatedly to cycle speeds (1x, 1.5x, 2x, 4x)."
    },
    {
        "category": "Playback & Transport",
        "key": "Left Arrow",
        "action": "Step Backward",
        "desc": "Step 1 frame backward."
    },
    {
        "category": "Playback & Transport",
        "key": "Right Arrow",
        "action": "Step Forward",
        "desc": "Step 1 frame forward."
    },
    {
        "category": "Playback & Transport",
        "key": "Home",
        "action": "First Frame",
        "desc": "Jump playhead to first frame of sequence."
    },
    {
        "category": "Playback & Transport",
        "key": "End",
        "action": "Last Frame",
        "desc": "Jump playhead to last frame of sequence."
    },
    {
        "category": "Playback & Transport",
        "key": "I",
        "action": "Set In Point",
        "desc": "Set playback loop start boundary at current frame."
    },
    {
        "category": "Playback & Transport",
        "key": "O",
        "action": "Set Out Point",
        "desc": "Set playback loop end boundary at current frame."
    },
    {
        "category": "Playback & Transport",
        "key": "X",
        "action": "Clear In/Out Points",
        "desc": "Reset playback range to full sequence length."
    },
    {
        "category": "Playback & Transport",
        "key": "C",
        "action": "Flush Cache",
        "desc": "Flush and reload timeline RAM frame cache."
    },
    {
        "category": "Playback & Transport",
        "key": "B",
        "action": "Toggle Bookmark",
        "desc": "Place or remove a bookmark marker on current frame."
    },
    {
        "category": "Playback & Transport",
        "key": "Shift+Left",
        "action": "Previous Bookmark / Note",
        "desc": "Jump to previous frame with bookmark or annotation."
    },
    {
        "category": "Playback & Transport",
        "key": "Shift+Right",
        "action": "Next Bookmark / Note",
        "desc": "Jump to next frame with bookmark or annotation."
    },
    {
        "category": "Playback & Transport",
        "key": "M",
        "action": "Toggle Audio Mute",
        "desc": "Mute or unmute audio track for video playback."
    },
    {
        "category": "Playback & Transport",
        "key": "Alt+0",
        "action": "Speed 0.5x",
        "desc": "Set playback rate to half-speed (slow motion)."
    },
    {
        "category": "Playback & Transport",
        "key": "Alt+1",
        "action": "Speed 1.0x",
        "desc": "Set playback rate to real-time 1.0x speed."
    },
    {
        "category": "Playback & Transport",
        "key": "Alt+2",
        "action": "Speed 2.0x",
        "desc": "Set playback rate to double-speed (fast forward)."
    },
    {
        "category": "Playback & Transport",
        "key": "Alt+3",
        "action": "Speed 4.0x",
        "desc": "Set playback rate to 4.0x speed."
    },

    # Category: Display & Viewport
    {
        "category": "Display & Viewport",
        "key": "F",
        "action": "Fullscreen / Fit",
        "desc": "Toggle fullscreen mode. Shift+F fits image to window."
    },
    {
        "category": "Display & Viewport",
        "key": "Shift+F",
        "action": "Fit to Window",
        "desc": "Fit current frame proportionally to viewport."
    },
    {
        "category": "Display & Viewport",
        "key": "F11",
        "action": "Fullscreen Mode",
        "desc": "Toggle borderless fullscreen display."
    },
    {
        "category": "Display & Viewport",
        "key": "U",
        "action": "Fullscreen Toggle",
        "desc": "Alternate hotkey for toggling fullscreen mode."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+1",
        "action": "Minimal View",
        "desc": "Toggle borderless cinema view (auto-hides UI controls)."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+2",
        "action": "Normal View",
        "desc": "Restore standard UI layout with menus and transport bar."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl++",
        "action": "Zoom In",
        "desc": "Magnify viewport image by +20%."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+-",
        "action": "Zoom Out",
        "desc": "Reduce viewport image by -20%."
    },
    {
        "category": "Display & Viewport",
        "key": "/ or \\",
        "action": "Reset Zoom / Fit",
        "desc": "Reset zoom level to 100% and fit image to viewport."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+I",
        "action": "Metadata Properties",
        "desc": "Toggle HUD overlay displaying resolution, codec, and header tags."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+H",
        "action": "Video Scopes",
        "desc": "Open real-time RGB Waveform, Vectorscope, and Histogram."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+Shift+G",
        "action": "Safe Guides",
        "desc": "Toggle Rule of Thirds, Crosshair, Action & Title Safe guides."
    },
    {
        "category": "Display & Viewport",
        "key": "Ctrl+Alt+F",
        "action": "False Color Exposure",
        "desc": "Toggle 10-zone false color exposure & clipping heatmap."
    },

    # Category: Color & Channels
    {
        "category": "Color & Channels",
        "key": "R",
        "action": "Red Channel",
        "desc": "Isolate Red color channel."
    },
    {
        "category": "Color & Channels",
        "key": "G",
        "action": "Green Channel",
        "desc": "Isolate Green color channel."
    },
    {
        "category": "Color & Channels",
        "key": "B / Ctrl+B",
        "action": "Blue Channel",
        "desc": "Isolate Blue color channel (Ctrl+B guarantees channel switch)."
    },
    {
        "category": "Color & Channels",
        "key": "A",
        "action": "Alpha Channel (Matte)",
        "desc": "Display alpha channel as grayscale matte."
    },
    {
        "category": "Color & Channels",
        "key": "Shift+A",
        "action": "Cycle Alpha Presentation",
        "desc": "Cycle alpha overlay mode (RGB, Checkerboard, Matte, Black, White)."
    },
    {
        "category": "Color & Channels",
        "key": "Ctrl+G",
        "action": "Color Grade / CDL Panel",
        "desc": "Toggle 3-Way ASC CDL chromatic color wheels and color grading panel."
    },
    {
        "category": "Color & Channels",
        "key": "+ or =",
        "action": "Exposure Up (+0.25)",
        "desc": "Nudge exposure brighter by +0.25 f-stops."
    },
    {
        "category": "Color & Channels",
        "key": "-",
        "action": "Exposure Down (-0.25)",
        "desc": "Nudge exposure darker by -0.25 f-stops."
    },
    {
        "category": "Color & Channels",
        "key": "]",
        "action": "Gamma Up (+0.10)",
        "desc": "Increase display gamma by +0.10."
    },
    {
        "category": "Color & Channels",
        "key": "[",
        "action": "Gamma Down (-0.10)",
        "desc": "Decrease display gamma by -0.10."
    },
    {
        "category": "Color & Channels",
        "key": "Ctrl+O / Alt+O",
        "action": "Toggle OCIO",
        "desc": "Enable or disable OpenColorIO color management transform."
    },

    # Category: Review & Compare
    {
        "category": "Review & Compare",
        "key": "Tab",
        "action": "A/B Compare Toggle",
        "desc": "Quick-switch between primary (A) and secondary (B) comparison media."
    },
    {
        "category": "Review & Compare",
        "key": "W",
        "action": "Wipe Compare",
        "desc": "Toggle interactive split wipe line with mouse positioning."
    },
    {
        "category": "Review & Compare",
        "key": "S",
        "action": "Side-by-Side Compare",
        "desc": "Display primary and secondary media side-by-side simultaneously."
    },
    {
        "category": "Review & Compare",
        "key": "Ctrl+Alt+1",
        "action": "1-Up Layout",
        "desc": "Single primary viewport layout."
    },
    {
        "category": "Review & Compare",
        "key": "Ctrl+Alt+2",
        "action": "2-Up Layout",
        "desc": "Dual side-by-side viewport grid."
    },
    {
        "category": "Review & Compare",
        "key": "Ctrl+Alt+4",
        "action": "4-Up Layout",
        "desc": "Quad 2x2 grid viewports for simultaneous multi-shot review."
    },
    {
        "category": "Review & Compare",
        "key": "Ctrl+Alt+6",
        "action": "6-Up Layout",
        "desc": "Six-tile 2x3 multi-viewport review grid."
    },
    {
        "category": "Review & Compare",
        "key": "Ctrl+Alt+C",
        "action": "Compare Previous Version",
        "desc": "Automatically load previous iteration into B track and activate Wipe."
    },

    # Category: Annotations & Review Notes
    {
        "category": "Annotations & Review Notes",
        "key": "N / Alt+A",
        "action": "Annotation Mode",
        "desc": "Toggle drawing toolbar and interactive annotation mode on canvas."
    },
    {
        "category": "Annotations & Review Notes",
        "key": "Ctrl+Z",
        "action": "Undo Stroke",
        "desc": "Undo last drawn annotation stroke on the current frame."
    },
    {
        "category": "Annotations & Review Notes",
        "key": "Ctrl+Shift+Z",
        "action": "Redo Stroke",
        "desc": "Redo previously undone stroke."
    },
    {
        "category": "Annotations & Review Notes",
        "key": "Ctrl+Shift+E",
        "action": "Export Annotated Frames",
        "desc": "Batch export all frames containing drawings as image files."
    },
    {
        "category": "Annotations & Review Notes",
        "key": "Ctrl+S",
        "action": "Save Review Sidecar",
        "desc": "Save drawings, bookmarks, and In/Out ranges to .review.json sidecar."
    },

    # Category: Versions & Studio (Kitsu)
    {
        "category": "Versions & Studio",
        "key": "PageUp",
        "action": "Previous Shot",
        "desc": "Jump to previous shot in playlist."
    },
    {
        "category": "Versions & Studio",
        "key": "PageDown",
        "action": "Next Shot",
        "desc": "Jump to next shot in playlist."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+L",
        "action": "Playlist Drawer",
        "desc": "Show or hide multi-shot playlist and shot browser panel."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+K",
        "action": "Open in Kitsu",
        "desc": "Open the currently loaded shot or task in Kitsu web dashboard."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Alt+P",
        "action": "Publish Kitsu Review",
        "desc": "Submit review note, status change, and annotated snapshot to Kitsu."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Up",
        "action": "Next Version",
        "desc": "Switch to next detected shot iteration (e.g. v001 -> v002)."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Down",
        "action": "Previous Version",
        "desc": "Switch to previous detected shot iteration (e.g. v002 -> v001)."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Shift+Up",
        "action": "Latest Version",
        "desc": "Switch immediately to the latest available shot version."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Alt+Right",
        "action": "Next Task Render",
        "desc": "Cycle forward to next department task (Edit -> Lighting -> Comp)."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Alt+Left",
        "action": "Previous Task Render",
        "desc": "Cycle backward to previous department task (Comp -> Lighting -> Edit)."
    },
    {
        "category": "Versions & Studio",
        "key": "Ctrl+Alt+V",
        "action": "Versions & Tasks Dialog",
        "desc": "Open shot iterations matrix to inspect and compare all department tasks."
    },

    # Category: File & Application
    {
        "category": "File & Application",
        "key": "Ctrl+O",
        "action": "Open Media...",
        "desc": "Open image sequence (EXR, DPX, TIFF) or video file (ProRes, H.264)."
    },
    {
        "category": "File & Application",
        "key": "Ctrl+Shift+O",
        "action": "Open Compare Media...",
        "desc": "Open secondary media file for A/B, Wipe, or Side-by-Side review."
    },
    {
        "category": "File & Application",
        "key": "Ctrl+E",
        "action": "Export / Transcode...",
        "desc": "Open export dialog to render ProRes, DNxHR, MP4 with slates & burn-ins."
    },
    {
        "category": "File & Application",
        "key": "Ctrl+Shift+S",
        "action": "Save Current Frame...",
        "desc": "Save uncompressed snapshot of the current frame to disk."
    },
    {
        "category": "File & Application",
        "key": "Ctrl+Q",
        "action": "Exit",
        "desc": "Quit VFX Review Player."
    },
    {
        "category": "File & Application",
        "key": "F1",
        "action": "Keyboard Shortcuts",
        "desc": "Open this keyboard shortcuts and hotkey reference guide."
    },

    # Category: Mouse & Gesture Controls
    {
        "category": "Mouse & Gestures",
        "key": "Left-Click Drag",
        "action": "Pan Canvas",
        "desc": "Pan the image smoothly across the viewport."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Mouse Wheel",
        "action": "Zoom at Cursor",
        "desc": "Continuously zoom in or out centered at cursor position."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Single Left-Click",
        "action": "Play / Pause Toggle",
        "desc": "Single-click on viewport canvas toggles playback state."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Double Left-Click",
        "action": "Fullscreen Toggle",
        "desc": "Double-click on viewport canvas toggles fullscreen display."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Middle-Click Drag",
        "action": "Interactive Scrub",
        "desc": "Drag with middle mouse button on timeline to scrub frames directly."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Right-Click",
        "action": "Viewport Context Menu",
        "desc": "Right-click viewport canvas to access transform, channel, and layout tools."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Shift+Drag Puck",
        "action": "Fine Color Wheel Tuning",
        "desc": "Hold Shift while dragging grading puck for ultra-fine micro-adjustments."
    },
    {
        "category": "Mouse & Gestures",
        "key": "Double-Click Puck",
        "action": "Reset Color Wheel",
        "desc": "Double-click color wheel puck to reset Lift/Gamma/Gain to neutral (0.0)."
    },
]


class ShortcutsDialog(QtWidgets.QDialog):
    """Nuke-style Keyboard Shortcuts and Hotkey Reference dialog with search and categories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts & Hotkey Reference")
        self.resize(880, 640)
        self.setMinimumSize(700, 480)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

        # Base paths & Icon
        if getattr(sys, 'frozen', False):
            app_root = os.path.dirname(sys.executable)
        else:
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        icon_path = os.path.join(app_root, "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # Overall Styling
        self.setStyleSheet("""
            QDialog {
                background-color: #141416;
                color: #e5e5ea;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "SF Pro Text", sans-serif;
            }
            QLabel {
                color: #e5e5ea;
            }
            QLineEdit {
                background-color: #1e1e22;
                color: #ffffff;
                border: 1px solid #36363c;
                border-radius: 6px;
                padding: 7px 12px;
                font-size: 13px;
                selection-background-color: #0a84ff;
            }
            QLineEdit:focus {
                border-color: #0a84ff;
                background-color: #242428;
            }
            QTabWidget::pane {
                border: 1px solid #28282c;
                background-color: #18181a;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #18181b;
                color: #8e8e93;
                padding: 6px 11px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 11.5px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #242428;
                color: #ffffff;
                border-bottom: 2px solid #0a84ff;
            }
            QTabBar::tab:hover:!selected {
                background: #1f1f23;
                color: #d1d1d6;
            }
            QTableWidget {
                background-color: #18181a;
                color: #d1d1d6;
                gridline-color: #242428;
                border: none;
                font-size: 12px;
                selection-background-color: #222a36;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #202024;
            }
            QHeaderView::section {
                background-color: #1e1e22;
                color: #8e8e93;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                border: none;
                border-bottom: 1px solid #2c2c30;
                padding: 6px 10px;
            }
            QScrollBar:vertical {
                background: #141416;
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
            QPushButton {
                background-color: #222226;
                color: #f0f0f3;
                border: 1px solid #36363a;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2c2c32;
                border-color: #0a84ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0a84ff;
                color: #ffffff;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # 1. Header with Title & Subtitle
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(4)

        title_lbl = QtWidgets.QLabel("Keyboard Shortcuts & Hotkey Reference")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #ffffff;")
        header_layout.addWidget(title_lbl)

        sub_lbl = QtWidgets.QLabel("Comprehensive guide to hotkeys, playback navigation, grading, and review controls.")
        sub_lbl.setStyleSheet("font-size: 12px; color: #8e8e93;")
        header_layout.addWidget(sub_lbl)

        layout.addLayout(header_layout)

        # 2. Search Box
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.setSpacing(8)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search shortcuts (e.g. play, zoom, grade, wipe, kitsu, bookmark)...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self.search_input)

        layout.addLayout(search_layout)

        # 3. Category Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.categories = [
            "All Shortcuts",
            "Playback & Transport",
            "Display & Viewport",
            "Color & Channels",
            "Review & Compare",
            "Annotations & Review Notes",
            "Versions & Studio",
            "File & Application",
            "Mouse & Gestures"
        ]

        self.tab_tables = {}
        for cat in self.categories:
            table = self._create_shortcuts_table()
            self.tab_tables[cat] = table
            
            tab_widget = QtWidgets.QWidget()
            tab_layout = QtWidgets.QVBoxLayout(tab_widget)
            tab_layout.setContentsMargins(0, 0, 0, 0)
            tab_layout.addWidget(table)
            
            # Short tab title
            short_name = cat.replace("Shortcuts", "").strip() or "All"
            self.tabs.addTab(tab_widget, short_name)

        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

        # 4. Bottom status & Close button
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)

        self.lbl_count = QtWidgets.QLabel()
        self.lbl_count.setStyleSheet("color: #8e8e93; font-size: 12px; font-weight: 500;")
        bottom_layout.addWidget(self.lbl_count)

        bottom_layout.addStretch()

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

        # Populate tables
        self._populate_all_tables()
        self._update_status_count()

    def _create_shortcuts_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Key / Shortcut", "Action", "Category", "Description"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        return table

    def _populate_all_tables(self):
        for cat, table in self.tab_tables.items():
            filtered = SHORTCUTS_DATA if cat == "All Shortcuts" else [item for item in SHORTCUTS_DATA if item["category"] == cat]
            self._fill_table(table, filtered)

    def _fill_table(self, table: QtWidgets.QTableWidget, items: list):
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            # Column 0: Keycap Styled Label
            key_widget = QtWidgets.QWidget()
            key_layout = QtWidgets.QHBoxLayout(key_widget)
            key_layout.setContentsMargins(6, 3, 6, 3)
            key_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

            key_badge = QtWidgets.QLabel(item["key"])
            key_badge.setStyleSheet("""
                QLabel {
                    background-color: #202026;
                    color: #38a2ff;
                    border: 1px solid #3c3c46;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-family: Consolas, "SF Mono", "Segoe UI Semibold", monospace;
                    font-size: 11px;
                    font-weight: 700;
                }
            """)
            key_layout.addWidget(key_badge)
            table.setCellWidget(row, 0, key_widget)

            # Column 1: Action
            action_item = QtWidgets.QTableWidgetItem(item["action"])
            action_item.setForeground(QtGui.QColor("#ffffff"))
            action_font = action_item.font()
            action_font.setBold(True)
            action_item.setFont(action_font)
            table.setItem(row, 1, action_item)

            # Column 2: Category
            cat_item = QtWidgets.QTableWidgetItem(item["category"])
            cat_item.setForeground(QtGui.QColor("#8e8e93"))
            table.setItem(row, 2, cat_item)

            # Column 3: Description
            desc_item = QtWidgets.QTableWidgetItem(item["desc"])
            desc_item.setForeground(QtGui.QColor("#b0b0b8"))
            table.setItem(row, 3, desc_item)

            table.setRowHeight(row, 36)

    def _apply_filter(self):
        search_text = self.search_input.text().strip().lower()
        curr_cat = self.categories[self.tabs.currentIndex()]
        table = self.tab_tables[curr_cat]

        visible_count = 0
        total_in_tab = table.rowCount()
        terms = search_text.split() if search_text else []

        for row in range(total_in_tab):
            if not terms:
                table.setRowHidden(row, False)
                visible_count += 1
                continue

            # Check text matches
            key_widget = table.cellWidget(row, 0)
            key_text = ""
            if key_widget:
                badge = key_widget.findChild(QtWidgets.QLabel)
                if badge:
                    key_text = badge.text().lower()

            action_text = (table.item(row, 1).text() if table.item(row, 1) else "").lower()
            cat_text = (table.item(row, 2).text() if table.item(row, 2) else "").lower()
            desc_text = (table.item(row, 3).text() if table.item(row, 3) else "").lower()
            combined = f"{key_text} {action_text} {cat_text} {desc_text}"

            # All search terms must match
            match = all(term in combined for term in terms)
            table.setRowHidden(row, not match)
            if match:
                visible_count += 1

        self.lbl_count.setText(f"Showing {visible_count} of {total_in_tab} shortcuts")

    def _on_tab_changed(self, index: int):
        self._apply_filter()

    def _update_status_count(self):
        curr_cat = self.categories[self.tabs.currentIndex()]
        table = self.tab_tables[curr_cat]
        self.lbl_count.setText(f"Showing {table.rowCount()} of {table.rowCount()} shortcuts")
