# gui/playlist_widget.py
"""
VFX Studio Multi-Shot Playlist and Shot Browser Widget.
Matches Section 65 Left Dock / Media Browser specification with Kitsu integration.
"""

import os, cv2
from PyQt6 import QtWidgets, QtCore, QtGui
from typing import Optional, List, Dict
from core.playlist_service import PlaylistService, PlaylistItem
from core.kitsu_service import kitsu_client

_THUMB_CACHE: Dict[str, QtGui.QPixmap] = {}


class ThumbnailWorker(QtCore.QRunnable):
    """Background worker to extract or download thumbnail image without blocking UI."""

    def __init__(self, item: PlaylistItem, on_ready_callback):
        super().__init__()
        self.item = item
        self.callback = on_ready_callback

    def run(self):
        pix = None
        try:
            # 1. Check Kitsu preview ID
            if self.item.kitsu_preview_id:
                thumb_file = kitsu_client.download_thumbnail(self.item.kitsu_preview_id)
                if thumb_file and os.path.exists(thumb_file):
                    qimg = QtGui.QImage(thumb_file)
                    if not qimg.isNull():
                        pix = QtGui.QPixmap.fromImage(qimg.scaled(60, 34, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation))

            # 2. Check local media file
            if pix is None and self.item.media_path and os.path.exists(self.item.media_path):
                ext = os.path.splitext(self.item.media_path)[1].lower()
                if ext in ('.mp4', '.mov', '.avi', '.mkv', '.mxf', '.webm'):
                    cap = cv2.VideoCapture(self.item.media_path)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        cap.release()
                        if ret and frame is not None:
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            h, w, ch = rgb.shape
                            qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format.Format_RGB888)
                            pix = QtGui.QPixmap.fromImage(qimg.scaled(60, 34, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation))
                elif ext in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'):
                    qimg = QtGui.QImage(self.item.media_path)
                    if not qimg.isNull():
                        pix = QtGui.QPixmap.fromImage(qimg.scaled(60, 34, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation))

            if pix is not None:
                key = self.item.kitsu_preview_id or self.item.media_path or self.item.id
                _THUMB_CACHE[key] = pix
                self.callback(pix)
        except Exception:
            pass


class PlaylistItemWidget(QtWidgets.QWidget):
    """Custom row widget for playlist items with shot details, thumbnail, task status and duration."""

    def __init__(self, item: PlaylistItem, index: int, parent=None):
        super().__init__(parent)
        self.item = item
        self.index = index
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Index badge
        self.lbl_index = QtWidgets.QLabel(f"{self.index + 1:02d}")
        self.lbl_index.setStyleSheet("color: #777; font-weight: bold; font-family: monospace; font-size: 11px;")
        self.lbl_index.setFixedWidth(22)
        layout.addWidget(self.lbl_index)

        # Thumbnail preview
        self.lbl_thumb = QtWidgets.QLabel()
        self.lbl_thumb.setFixedSize(60, 34)
        self.lbl_thumb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet("""
            background-color: #121214;
            border: 1px solid #2e2e34;
            border-radius: 4px;
            color: #555;
            font-size: 13px;
        """)
        self.lbl_thumb.setText("🎬")
        layout.addWidget(self.lbl_thumb)

        # Load thumbnail
        cache_key = self.item.kitsu_preview_id or self.item.media_path or self.item.id
        if cache_key in _THUMB_CACHE:
            self.lbl_thumb.setPixmap(_THUMB_CACHE[cache_key])
        else:
            worker = ThumbnailWorker(self.item, self._on_thumb_loaded)
            QtCore.QThreadPool.globalInstance().start(worker)

        # Info column (Shot name / Seq, task & frames)
        info_vbox = QtWidgets.QVBoxLayout()
        info_vbox.setSpacing(2)
        info_vbox.setContentsMargins(0, 0, 0, 0)

        title_text = self.item.shot_name or self.item.name
        if self.item.sequence_name:
            title_text = f"{self.item.sequence_name} / {title_text}"

        self.lbl_title = QtWidgets.QLabel(title_text)
        self.lbl_title.setStyleSheet("color: #eaeaea; font-weight: 600; font-size: 12px;")
        info_vbox.addWidget(self.lbl_title)

        meta_parts = []
        if self.item.task_name:
            task_str = self.item.task_name
            if self.item.version:
                task_str += f" ({self.item.version})"
            meta_parts.append(task_str)
        if self.item.frame_count > 0:
            meta_parts.append(f"{self.item.frame_count} f")
        if self.item.fps > 0:
            meta_parts.append(f"{self.item.fps:.1f} fps")

        sub_text = " • ".join(meta_parts) if meta_parts else self.item.media_path
        self.lbl_sub = QtWidgets.QLabel(sub_text)
        self.lbl_sub.setStyleSheet("color: #888; font-size: 10px;")
        info_vbox.addWidget(self.lbl_sub)

        layout.addLayout(info_vbox, stretch=1)

        # Status badge if available
        if self.item.status:
            status_colors = {
                "approved": ("#10b981", "#064e3b"),
                "wtg": ("#f59e0b", "#78350f"),
                "retake": ("#ef4444", "#7f1d1d"),
                "wip": ("#3b82f6", "#1e3a8a"),
            }
            fg, bg = status_colors.get(self.item.status.lower(), ("#a3a3a3", "#262626"))
            self.badge = QtWidgets.QLabel(self.item.status.upper())
            self.badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    color: {fg};
                    font-size: 9px;
                    font-weight: bold;
                    padding: 2px 6px;
                    border-radius: 4px;
                }}
            """)
            layout.addWidget(self.badge)

    def _on_thumb_loaded(self, pixmap: QtGui.QPixmap):
        if hasattr(self, 'lbl_thumb') and pixmap and not pixmap.isNull():
            QtCore.QTimer.singleShot(0, lambda: self.lbl_thumb.setPixmap(pixmap))

    def set_active(self, is_active: bool):
        if is_active:
            self.lbl_index.setStyleSheet("color: #3b82f6; font-weight: bold; font-family: monospace; font-size: 11px;")
            self.lbl_title.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 12px;")
        else:
            self.lbl_index.setStyleSheet("color: #777; font-weight: bold; font-family: monospace; font-size: 11px;")
            self.lbl_title.setStyleSheet("color: #eaeaea; font-weight: 600; font-size: 12px;")


class ReorderablePlaylistListWidget(QtWidgets.QListWidget):
    """QListWidget supporting multiple selection, key shortcuts, and drag-drop reordering."""
    item_reordered = QtCore.pyqtSignal(int, int)  # from_row, to_row
    delete_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self._drag_start_row = -1

    def startDrag(self, supportedActions):
        self._drag_start_row = self.currentRow()
        super().startDrag(supportedActions)

    def dropEvent(self, event: QtGui.QDropEvent):
        if event.source() == self:
            drop_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            target_item = self.itemAt(drop_pos)
            target_row = self.row(target_item) if target_item else self.count() - 1
            source_row = self._drag_start_row
            event.accept()
            if source_row >= 0 and target_row >= 0 and source_row != target_row:
                self.item_reordered.emit(source_row, target_row)
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            self.delete_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class PlaylistWidget(QtWidgets.QWidget):
    """
    Left-dock collapsible playlist drawer.
    Provides shot list, multi-shot queue, next/previous navigation, and direct Kitsu synchronization.
    """

    shot_selected = QtCore.pyqtSignal(object)  # PlaylistItem
    load_kitsu_requested = QtCore.pyqtSignal()
    publish_kitsu_requested = QtCore.pyqtSignal(object)  # PlaylistItem
    version_compare_requested = QtCore.pyqtSignal(object)  # PlaylistItem
    compare_prev_version_requested = QtCore.pyqtSignal(object)  # PlaylistItem
    open_kitsu_requested = QtCore.pyqtSignal(object)  # PlaylistItem
    add_media_requested = QtCore.pyqtSignal()
    add_folder_requested = QtCore.pyqtSignal()
    files_dropped = QtCore.pyqtSignal(list)
    playlist_cleared = QtCore.pyqtSignal()

    def __init__(self, playlist_service: PlaylistService, parent=None):
        super().__init__(parent)
        self.service = playlist_service
        self.setAcceptDrops(True)
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #d1d5db;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            QListWidget {
                background-color: #161616;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
                padding: 2px;
                outline: none;
            }
            QListWidget::item {
                background-color: #1e1e1e;
                border: 1px solid #262626;
                border-radius: 4px;
                margin-bottom: 3px;
            }
            QListWidget::item:hover {
                background-color: #262626;
                border: 1px solid #3b82f6;
            }
            QListWidget::item:selected {
                background-color: #1e293b;
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 500;
                font-size: 11px;
                color: #e5e7eb;
            }
            QPushButton:hover {
                background-color: #383838;
                border-color: #4b5563;
            }
            QPushButton:pressed {
                background-color: #1f2937;
            }
            QPushButton#kitsuBtn {
                background-color: #1e3a8a;
                border: 1px solid #2563eb;
                color: #93c5fd;
                font-weight: 600;
            }
            QPushButton#kitsuBtn:hover {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header Title and Shot Counter
        header_hbox = QtWidgets.QHBoxLayout()
        header_title = QtWidgets.QLabel("PLAYLIST / SHOT BROWSER")
        header_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #9ca3af; letter-spacing: 1px;")
        header_hbox.addWidget(header_title)

        header_hbox.addStretch()

        self.lbl_count = QtWidgets.QLabel("0 shots")
        self.lbl_count.setStyleSheet("font-size: 11px; color: #6b7280; font-weight: 600;")
        header_hbox.addWidget(self.lbl_count)

        layout.addLayout(header_hbox)

        # Action Buttons Row 1 (Add Media Files, Add Folder, Kitsu Import)
        btn_layout1 = QtWidgets.QHBoxLayout()
        btn_layout1.setSpacing(6)

        self.btn_add = QtWidgets.QPushButton("+ Add Files...")
        self.btn_add.setToolTip("Select multiple media files or sequences to add to the playlist")
        self.btn_add.clicked.connect(self.add_media_requested.emit)
        btn_layout1.addWidget(self.btn_add)

        self.btn_add_folder = QtWidgets.QPushButton("+ Folder...")
        self.btn_add_folder.setToolTip("Add all media files or image sequences in a directory")
        self.btn_add_folder.clicked.connect(self.add_folder_requested.emit)
        btn_layout1.addWidget(self.btn_add_folder)

        self.btn_kitsu_import = QtWidgets.QPushButton("Kitsu...")
        self.btn_kitsu_import.setObjectName("kitsuBtn")
        self.btn_kitsu_import.setToolTip("Connect to Kitsu and load review playlist")
        self.btn_kitsu_import.clicked.connect(self.load_kitsu_requested.emit)
        btn_layout1.addWidget(self.btn_kitsu_import)

        layout.addLayout(btn_layout1)

        # Action Buttons Row 2 (Reorder & Remove)
        btn_layout2 = QtWidgets.QHBoxLayout()
        btn_layout2.setSpacing(6)

        self.btn_move_up = QtWidgets.QPushButton("▲ Up")
        self.btn_move_up.setToolTip("Move selected shot up in order (Alt+Up)")
        self.btn_move_up.clicked.connect(self.move_selected_up)
        btn_layout2.addWidget(self.btn_move_up)

        self.btn_move_down = QtWidgets.QPushButton("▼ Down")
        self.btn_move_down.setToolTip("Move selected shot down in order (Alt+Down)")
        self.btn_move_down.clicked.connect(self.move_selected_down)
        btn_layout2.addWidget(self.btn_move_down)

        self.btn_remove = QtWidgets.QPushButton("✖ Remove")
        self.btn_remove.setToolTip("Remove selected shot(s) from playlist (Delete)")
        self.btn_remove.clicked.connect(self.remove_selected)
        btn_layout2.addWidget(self.btn_remove)

        layout.addLayout(btn_layout2)

        # List Widget
        self.list_widget = ReorderablePlaylistListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.item_reordered.connect(self._on_item_reordered)
        self.list_widget.delete_requested.connect(self.remove_selected)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget, stretch=1)

        # Bottom Bar: Loop checkbox & Prev / Next buttons
        bottom_hbox = QtWidgets.QHBoxLayout()
        bottom_hbox.setSpacing(6)

        self.chk_loop = QtWidgets.QCheckBox("Loop All")
        self.chk_loop.setChecked(self.service.loop)
        self.chk_loop.setStyleSheet("font-size: 11px; color: #9ca3af;")
        self.chk_loop.toggled.connect(self._on_loop_toggled)
        bottom_hbox.addWidget(self.chk_loop)

        bottom_hbox.addStretch()

        self.btn_prev = QtWidgets.QPushButton("◀ Prev")
        self.btn_prev.setToolTip("Previous shot in playlist (PageUp)")
        self.btn_prev.clicked.connect(self.select_prev)
        bottom_hbox.addWidget(self.btn_prev)

        self.btn_next = QtWidgets.QPushButton("Next ▶")
        self.btn_next.setToolTip("Next shot in playlist (PageDown)")
        self.btn_next.clicked.connect(self.select_next)
        bottom_hbox.addWidget(self.btn_next)

        self.btn_clear = QtWidgets.QPushButton("Clear")
        self.btn_clear.setToolTip("Clear all items from playlist")
        self.btn_clear.clicked.connect(self.clear_playlist)
        bottom_hbox.addWidget(self.btn_clear)

        layout.addLayout(bottom_hbox)

    def _on_loop_toggled(self, checked: bool):
        self.service.loop = checked

    def refresh(self):
        """Re-populates the QListWidget from self.service.items."""
        self.list_widget.clear()
        count = len(self.service.items)
        self.lbl_count.setText(f"{count} {'shot' if count == 1 else 'shots'}")

        for i, item in enumerate(self.service.items):
            list_item = QtWidgets.QListWidgetItem(self.list_widget)
            custom_widget = PlaylistItemWidget(item, i)
            is_active = (i == self.service.current_index)
            custom_widget.set_active(is_active)
            list_item.setSizeHint(custom_widget.sizeHint())
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, custom_widget)
            if is_active:
                self.list_widget.setCurrentItem(list_item)

    def set_current_index(self, index: int):
        """Updates the highlighted current active shot."""
        self.service.set_current_index(index)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, PlaylistItemWidget):
                widget.set_active(i == index)
        if 0 <= index < self.list_widget.count():
            self.list_widget.setCurrentRow(index)

    def _on_item_double_clicked(self, list_item: QtWidgets.QListWidgetItem):
        idx = self.list_widget.row(list_item)
        item = self.service.set_current_index(idx)
        if item:
            self.set_current_index(idx)
            self.shot_selected.emit(item)

    def select_next(self):
        item = self.service.next_item()
        if item:
            self.set_current_index(self.service.current_index)
            self.shot_selected.emit(item)

    def select_prev(self):
        item = self.service.prev_item()
        if item:
            self.set_current_index(self.service.current_index)
            self.shot_selected.emit(item)

    def clear_playlist(self):
        self.service.clear()
        self.refresh()
        self.playlist_cleared.emit()

    def remove_selected(self):
        """Remove all currently selected items from the playlist."""
        selected_rows = [self.list_widget.row(item) for item in self.list_widget.selectedItems()]
        if not selected_rows:
            return
        self.service.remove_indices(selected_rows)
        self.refresh()

    def move_selected_up(self):
        """Move selected item(s) up in the playlist order."""
        selected_rows = sorted([self.list_widget.row(item) for item in self.list_widget.selectedItems()])
        if not selected_rows or selected_rows[0] == 0:
            return
        for r in selected_rows:
            self.service.move_item(r, r - 1)
        self.refresh()
        for r in selected_rows:
            item = self.list_widget.item(r - 1)
            if item:
                item.setSelected(True)

    def move_selected_down(self):
        """Move selected item(s) down in the playlist order."""
        selected_rows = sorted([self.list_widget.row(item) for item in self.list_widget.selectedItems()], reverse=True)
        if not selected_rows or selected_rows[0] >= len(self.service.items) - 1:
            return
        for r in selected_rows:
            self.service.move_item(r, r + 1)
        self.refresh()
        for r in selected_rows:
            item = self.list_widget.item(r + 1)
            if item:
                item.setSelected(True)

    def _on_item_reordered(self, from_row: int, to_row: int):
        """Handle internal drag-and-drop row move."""
        self.service.move_item(from_row, to_row)
        self.refresh()
        item = self.list_widget.item(to_row)
        if item:
            item.setSelected(True)

    def _show_context_menu(self, pos: QtCore.QPoint):
        item = self.list_widget.itemAt(pos)
        if not item:
            return

        row = self.list_widget.row(item)
        playlist_item = self.service.get_item(row)
        if not playlist_item:
            return

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #222;
                color: #eee;
                border: 1px solid #444;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: white;
            }
        """)

        act_play = menu.addAction("Play Shot")
        act_versions = menu.addAction("Versions & Tasks for this Shot... (Ctrl+Alt+V)")
        act_compare_prev = menu.addAction("Compare with Previous Version (Wipe) (Ctrl+Alt+C)")
        menu.addSeparator()
        act_move_up = menu.addAction("Move Up (Alt+Up)")
        act_move_down = menu.addAction("Move Down (Alt+Down)")
        menu.addSeparator()
        act_kitsu_open = menu.addAction("Open Shot in Kitsu Browser (Ctrl+K)")
        act_publish = menu.addAction("Publish Review Note to Kitsu... (Ctrl+Alt+P)")
        menu.addSeparator()
        act_copy = menu.addAction("Copy Path")
        act_remove = menu.addAction("Remove Selected from Playlist (Delete)")

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == act_play:
            self.service.set_current_index(row)
            self.set_current_index(row)
            self.shot_selected.emit(playlist_item)
        elif action == act_versions:
            self.version_compare_requested.emit(playlist_item)
        elif action == act_compare_prev:
            self.compare_prev_version_requested.emit(playlist_item)
        elif action == act_move_up:
            self.move_selected_up()
        elif action == act_move_down:
            self.move_selected_down()
        elif action == act_kitsu_open:
            self._open_shot_in_kitsu(playlist_item)
        elif action == act_publish:
            self.publish_kitsu_requested.emit(playlist_item)
        elif action == act_copy:
            QtWidgets.QApplication.clipboard().setText(playlist_item.media_path)
        elif action == act_remove:
            self.remove_selected()

    def _open_shot_in_kitsu(self, item: PlaylistItem):
        import webbrowser
        from core.kitsu_service import kitsu_client
        url = item.kitsu_url
        if not url and item.kitsu_shot_id:
            url = kitsu_client.build_shot_url(item.kitsu_shot_id, item.kitsu_project_id)
        if not url and kitsu_client.is_authenticated():
            try:
                s_name = item.shot or item.name
                s_data = kitsu_client.get_shot_by_name(s_name)
                if s_data and s_data.get("id"):
                    url = kitsu_client.build_shot_url(s_data["id"], s_data.get("project_id"))
            except Exception:
                pass
        if not url:
            host = getattr(kitsu_client, "host_url", None)
            if host:
                url = f"{host.rstrip('/')}/productions"
        if url:
            webbrowser.open(url)
            self.open_kitsu_requested.emit(item)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent):
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if local_path:
                    paths.append(local_path)
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)
