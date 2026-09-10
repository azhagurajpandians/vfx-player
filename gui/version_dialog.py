# gui/version_dialog.py
"""
VFX Studio Shot Versions & Tasks Comparison Dialog for VFXPlayer.
Allows inspecting and comparing all versions across different tasks (Edit, Comp, Lighting, Anim, Plate)
from Kitsu or local disk in Wipe, Side-by-Side, or Split comparison mode.
"""

import os
from typing import Optional, List, Dict, Any
from PyQt6 import QtWidgets, QtCore, QtGui
from core.kitsu_service import kitsu_client


class VersionCompareDialog(QtWidgets.QDialog):
    """
    Dialog to view, select, play, or compare different versions across tasks for a shot.
    Supports Kitsu task previews (Edit, Comp, Lighting, etc.) and local disk versions.
    """

    # mode: 'play', 'wipe', 'side-by-side', 'split'
    version_action_triggered = QtCore.pyqtSignal(dict, str)

    def __init__(
        self,
        shot_name: str,
        versions: List[Dict[str, Any]],
        current_version_label: str = "",
        parent: Optional[QtWidgets.QWidget] = None
    ):
        super().__init__(parent)
        self.shot_name = shot_name
        self.all_versions = versions
        self.filtered_versions = list(versions)
        self.current_version_label = current_version_label
        self.selected_action = None  # (version_dict, mode)

        self.setWindowTitle(f"Versions & Tasks — {shot_name}")
        self.resize(680, 520)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                color: #e4e4e7;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QLabel {
                color: #e4e4e7;
            }
            QListWidget {
                background-color: #121214;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                background-color: #1e1e24;
                border: 1px solid #2e2e38;
                border-radius: 6px;
                margin-bottom: 4px;
                padding: 4px;
            }
            QListWidget::item:hover {
                background-color: #272732;
                border: 1px solid #3b82f6;
            }
            QListWidget::item:selected {
                background-color: #1e293b;
                border: 1.5px solid #38bdf8;
            }
            QPushButton {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton#btnWipe {
                background-color: #0284c7;
                border-color: #0369a1;
                color: #ffffff;
            }
            QPushButton#btnWipe:hover {
                background-color: #0369a1;
            }
            QPushButton#btnPlay {
                background-color: #16a34a;
                border-color: #15803d;
                color: #ffffff;
            }
            QPushButton#btnPlay:hover {
                background-color: #15803d;
            }
            QComboBox {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 4px 8px;
                color: #f4f4f5;
                font-size: 11px;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header Title
        hdr_row = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel(f"Shot Versions: <b style='color:#38bdf8;'>{self.shot_name}</b>")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch()

        # Task filter dropdown
        task_names = sorted(list({v.get("task_name", "General") for v in self.all_versions if v.get("task_name")}))
        if task_names:
            hdr_row.addWidget(QtWidgets.QLabel("Filter Task:"))
            self.task_filter = QtWidgets.QComboBox()
            self.task_filter.addItem("All Tasks")
            for t in task_names:
                self.task_filter.addItem(t)
            self.task_filter.currentIndexChanged.connect(self._on_filter_changed)
            hdr_row.addWidget(self.task_filter)

        layout.addLayout(hdr_row)

        # Versions List Widget
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setIconSize(QtCore.QSize(64, 36))
        self.list_widget.itemDoubleClicked.connect(lambda: self._trigger_action("wipe"))
        layout.addWidget(self.list_widget, stretch=1)

        self._populate_list()

        # Selection info readout
        self.lbl_info = QtWidgets.QLabel("Select a version above to play or compare with current playback.")
        self.lbl_info.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        layout.addWidget(self.lbl_info)

        # Action Buttons
        btn_box = QtWidgets.QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_play = QtWidgets.QPushButton("▶ Play Version")
        self.btn_play.setObjectName("btnPlay")
        self.btn_play.setToolTip("Load this version into the main player (Track A)")
        self.btn_play.clicked.connect(lambda: self._trigger_action("play"))
        btn_box.addWidget(self.btn_play)

        self.btn_wipe = QtWidgets.QPushButton("🔀 Compare in Wipe Mode")
        self.btn_wipe.setObjectName("btnWipe")
        self.btn_wipe.setToolTip("Load this version into Track B and activate real-time Wipe comparison")
        self.btn_wipe.clicked.connect(lambda: self._trigger_action("wipe"))
        btn_box.addWidget(self.btn_wipe)

        self.btn_side = QtWidgets.QPushButton("⚏ Compare Side-by-Side")
        self.btn_side.setToolTip("Load this version into Track B and switch to 2-Up Side-by-Side comparison")
        self.btn_side.clicked.connect(lambda: self._trigger_action("side-by-side"))
        btn_box.addWidget(self.btn_side)

        self.btn_split = QtWidgets.QPushButton("⚡ Split Mode")
        self.btn_split.setToolTip("Load this version into Track B and activate split comparison")
        self.btn_split.clicked.connect(lambda: self._trigger_action("split"))
        btn_box.addWidget(self.btn_split)

        btn_box.addStretch()

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)

    def _on_filter_changed(self):
        selected_task = self.task_filter.currentText()
        if selected_task == "All Tasks":
            self.filtered_versions = list(self.all_versions)
        else:
            self.filtered_versions = [v for v in self.all_versions if v.get("task_name") == selected_task]
        self._populate_list()

    def _populate_list(self):
        self.list_widget.clear()
        if not self.filtered_versions:
            item = QtWidgets.QListWidgetItem("No versions found for this task.")
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            return

        # Task badge colors
        task_colors = {
            "edit": ("#06b6d4", "#164e63"),
            "comp": ("#3b82f6", "#1e3a8a"),
            "compositing": ("#3b82f6", "#1e3a8a"),
            "lighting": ("#f59e0b", "#78350f"),
            "anim": ("#a855f7", "#581c87"),
            "animation": ("#a855f7", "#581c87"),
            "fx": ("#ec4899", "#831843"),
            "plate": ("#10b981", "#064e3b"),
        }

        for v in self.filtered_versions:
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(10)

            # Thumbnail preview
            lbl_thumb = QtWidgets.QLabel()
            lbl_thumb.setFixedSize(64, 36)
            lbl_thumb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl_thumb.setStyleSheet("background-color: #09090b; border: 1px solid #27272a; border-radius: 4px; color: #52525b;")
            lbl_thumb.setText("🎬")

            # Try loading cached thumbnail or local media
            p_id = v.get("preview_file_id")
            media_p = v.get("media_path")
            if p_id:
                thumb_p = kitsu_client.download_thumbnail(p_id)
                if thumb_p and os.path.exists(thumb_p):
                    pix = QtGui.QPixmap(thumb_p).scaled(64, 36, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation)
                    lbl_thumb.setPixmap(pix)
            elif media_p and os.path.exists(media_p):
                # Local image / video
                pix = QtGui.QPixmap(media_p)
                if not pix.isNull():
                    lbl_thumb.setPixmap(pix.scaled(64, 36, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation))

            row_layout.addWidget(lbl_thumb)

            # Info column
            info_box = QtWidgets.QVBoxLayout()
            info_box.setSpacing(2)
            info_box.setContentsMargins(0, 0, 0, 0)

            # Version label row
            v_title = v.get("version_label") or f"{v.get('task_name', 'Task')} v{v.get('version_num', 1):03d}"
            lbl_v = QtWidgets.QLabel(f"<b>{v_title}</b>")
            lbl_v.setStyleSheet("font-size: 12px; color: #f4f4f5;")
            info_box.addWidget(lbl_v)

            # Sub meta: Author, Date, Comment
            meta_str = []
            if v.get("author"):
                meta_str.append(v["author"])
            if v.get("created_at"):
                meta_str.append(v["created_at"])
            if v.get("comment"):
                meta_str.append(f'"{v["comment"]}"')
            lbl_meta = QtWidgets.QLabel(" • ".join(meta_str) if meta_str else "No comment")
            lbl_meta.setStyleSheet("font-size: 10px; color: #a1a1aa;")
            info_box.addWidget(lbl_meta)
            row_layout.addLayout(info_box, stretch=1)

            # Task tag pill
            task_key = v.get("task_name", "").lower()
            fg, bg = task_colors.get(task_key, ("#94a3b8", "#1e293b"))
            lbl_task = QtWidgets.QLabel(v.get("task_name", "TASK").upper())
            lbl_task.setStyleSheet(f"background-color: {bg}; color: {fg}; font-size: 9px; font-weight: bold; padding: 2px 6px; border-radius: 4px;")
            row_layout.addWidget(lbl_task)

            # Status pill if available
            if v.get("status"):
                st = v["status"].lower()
                st_fg, st_bg = ("#10b981", "#064e3b") if "app" in st else ("#ef4444", "#7f1d1d") if "retake" in st or "rev" in st else ("#3b82f6", "#1e3a8a")
                lbl_st = QtWidgets.QLabel(v["status"].upper())
                lbl_st.setStyleSheet(f"background-color: {st_bg}; color: {st_fg}; font-size: 9px; font-weight: bold; padding: 2px 6px; border-radius: 4px;")
                row_layout.addWidget(lbl_st)

            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(0, 48))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, v)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _trigger_action(self, mode: str):
        item = self.list_widget.currentItem()
        if not item:
            QtWidgets.QMessageBox.warning(self, "Selection Required", "Please select a version to compare or play.")
            return
        v_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not v_data:
            return
        self.selected_action = (v_data, mode)
        self.version_action_triggered.emit(v_data, mode)
        self.accept()
