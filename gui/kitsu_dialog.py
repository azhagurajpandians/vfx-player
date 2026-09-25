from __future__ import annotations

import os
from typing import Optional, List, Dict, Any
from PyQt6 import QtCore, QtGui, QtWidgets
from core.kitsu_service import kitsu_client, KitsuService
from core.playlist_service import PlaylistItem


class KitsuConnectDialog(QtWidgets.QDialog):
    """Dialog to authenticate with Kitsu and import review playlists into VFX Player."""

    playlist_selected = QtCore.pyqtSignal(list, str)  # (list of PlaylistItem, playlist_name)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, prefs: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Kitsu Studio")
        self.resize(520, 500)

        # Load preferences and persistent QSettings
        self.prefs = prefs if prefs is not None else (getattr(parent, "prefs", {}) if parent else {})
        self.qsettings = QtCore.QSettings("VFXPlayer", "Kitsu")

        # Remember credentials flag
        saved_remember = self.qsettings.value("remember", True)
        if isinstance(saved_remember, str):
            saved_remember = saved_remember.lower() in ("true", "1", "yes")
        elif not isinstance(saved_remember, bool):
            saved_remember = bool(saved_remember)
        if "kitsu_remember" in self.prefs:
            saved_remember = bool(self.prefs.get("kitsu_remember", True))

        # Retrieve stored credentials
        stored_host = (
            self.prefs.get("kitsu_host")
            or self.qsettings.value("host", "")
            or getattr(kitsu_client, "host_url", "")
            or "http://localhost:8080"
        )
        stored_email = (
            self.prefs.get("kitsu_email")
            or self.qsettings.value("email", "")
        )
        stored_pwd = (
            self.prefs.get("kitsu_password")
            or self.qsettings.value("password", "")
        )
        stored_token = (
            self.prefs.get("kitsu_token")
            or self.qsettings.value("token", "")
            or getattr(kitsu_client, "auth_token", "")
        )

        self._selected_items: List[PlaylistItem] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # Connection Box
        conn_group = QtWidgets.QGroupBox("Kitsu Server Connection")
        conn_layout = QtWidgets.QGridLayout(conn_group)
        conn_layout.setSpacing(8)

        conn_layout.addWidget(QtWidgets.QLabel("Host URL:"), 0, 0)
        self.host_edit = QtWidgets.QLineEdit()
        self.host_edit.setText(stored_host)
        self.host_edit.setPlaceholderText("http://10.10.6.82 or https://kitsu.mystudio.com")
        conn_layout.addWidget(self.host_edit, 0, 1)

        conn_layout.addWidget(QtWidgets.QLabel("Email:"), 1, 0)
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setText(stored_email)
        self.email_edit.setPlaceholderText("artist@studio.com")
        conn_layout.addWidget(self.email_edit, 1, 1)

        conn_layout.addWidget(QtWidgets.QLabel("Password:"), 2, 0)
        self.pass_edit = QtWidgets.QLineEdit()
        self.pass_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.pass_edit.setText(stored_pwd if saved_remember else "")
        conn_layout.addWidget(self.pass_edit, 2, 1)

        # Remember credentials checkbox
        self.chk_remember = QtWidgets.QCheckBox("Remember login credentials")
        self.chk_remember.setChecked(saved_remember)
        conn_layout.addWidget(self.chk_remember, 3, 1)

        # Clear cache on exit checkbox
        saved_clear_cache = bool(self.prefs.get("clear_kitsu_cache_on_exit", False))
        self.chk_clear_cache_exit = QtWidgets.QCheckBox("Clear Kitsu media cache on exit")
        self.chk_clear_cache_exit.setChecked(saved_clear_cache)
        self.chk_clear_cache_exit.toggled.connect(self._on_clear_cache_exit_toggled)
        conn_layout.addWidget(self.chk_clear_cache_exit, 4, 1)

        # Cache size & Clear Cache Now button
        cache_row = QtWidgets.QHBoxLayout()
        self.lbl_cache_info = QtWidgets.QLabel()
        self._refresh_cache_size_label()
        cache_row.addWidget(self.lbl_cache_info)
        cache_row.addStretch()

        self.btn_clear_cache_now = QtWidgets.QPushButton("Clear Cache Now")
        self.btn_clear_cache_now.setStyleSheet("background-color: #2c2c2e; color: #ff453a; font-size: 11px; padding: 3px 8px; border: 1px solid #444; border-radius: 3px;")
        self.btn_clear_cache_now.clicked.connect(self._on_clear_cache_now_clicked)
        cache_row.addWidget(self.btn_clear_cache_now)
        conn_layout.addLayout(cache_row, 5, 0, 1, 2)

        self.btn_connect = QtWidgets.QPushButton("Connect to Kitsu")
        self.btn_connect.setStyleSheet("background-color: #0a84ff; color: white; font-weight: bold; padding: 6px;")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        conn_layout.addWidget(self.btn_connect, 6, 0, 1, 2)

        layout.addWidget(conn_group)

        # Playlist Explorer Box
        exp_group = QtWidgets.QGroupBox("Kitsu Playlists")
        exp_layout = QtWidgets.QVBoxLayout(exp_group)
        exp_layout.setSpacing(8)

        proj_row = QtWidgets.QHBoxLayout()
        proj_row.addWidget(QtWidgets.QLabel("Project:"))
        self.combo_project = QtWidgets.QComboBox()
        self.combo_project.currentIndexChanged.connect(self._on_project_changed)
        proj_row.addWidget(self.combo_project, stretch=1)
        exp_layout.addLayout(proj_row)

        pl_row = QtWidgets.QHBoxLayout()
        pl_row.addWidget(QtWidgets.QLabel("Playlist:"))
        self.combo_playlist = QtWidgets.QComboBox()
        self.combo_playlist.currentIndexChanged.connect(self._on_playlist_changed)
        pl_row.addWidget(self.combo_playlist, stretch=1)
        exp_layout.addLayout(pl_row)

        self.shot_list = QtWidgets.QListWidget()
        self.shot_list.setStyleSheet("background-color: #1a1a1e; color: #ddd; font-size: 11px;")
        exp_layout.addWidget(self.shot_list, stretch=1)

        layout.addWidget(exp_group, stretch=1)

        # Actions
        btn_box = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Not connected")
        self.status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        btn_box.addWidget(self.status_lbl)
        btn_box.addStretch()

        self.btn_import = QtWidgets.QPushButton("Load Playlist into Player")
        self.btn_import.setEnabled(False)
        self.btn_import.setStyleSheet("background-color: #30d158; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_import.clicked.connect(self._on_import_clicked)
        btn_box.addWidget(self.btn_import)

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)

        self._token: Optional[str] = stored_token or getattr(kitsu_client, "auth_token", None)
        self._projects_data: List[Dict[str, Any]] = []
        self._playlists_data: List[Dict[str, Any]] = []
        self._current_shots_data: List[Dict[str, Any]] = []

        if stored_host:
            kitsu_client.host_url = stored_host

        if self._token:
            kitsu_client.auth_token = self._token
            self.status_lbl.setText("Previously authenticated")
            self.status_lbl.setStyleSheet("color: #30d158; font-size: 11px;")
            self._load_projects()
        elif stored_host and stored_email and stored_pwd and saved_remember:
            QtCore.QTimer.singleShot(150, self._on_connect_clicked)

    def _refresh_cache_size_label(self):
        sz_bytes = kitsu_client.get_cache_size()
        if sz_bytes >= 1024 * 1024 * 1024:
            sz_str = f"{sz_bytes / (1024 * 1024 * 1024):.2f} GB"
        elif sz_bytes >= 1024 * 1024:
            sz_str = f"{sz_bytes / (1024 * 1024):.1f} MB"
        elif sz_bytes > 0:
            sz_str = f"{sz_bytes / 1024:.0f} KB"
        else:
            sz_str = "0 KB"
        self.lbl_cache_info.setText(f"Cache usage: {sz_str}")
        self.lbl_cache_info.setStyleSheet("color: #888; font-size: 11px;")

    def _on_clear_cache_exit_toggled(self, checked: bool):
        if isinstance(self.prefs, dict):
            self.prefs["clear_kitsu_cache_on_exit"] = checked
            if self.parent() and hasattr(self.parent(), "_save_prefs"):
                self.parent()._save_prefs()

    def _on_clear_cache_now_clicked(self):
        files_rem, bytes_freed = kitsu_client.clear_cache()
        if bytes_freed >= 1024 * 1024:
            freed_str = f"{bytes_freed / (1024 * 1024):.1f} MB"
        else:
            freed_str = f"{bytes_freed / 1024:.0f} KB"
        self._refresh_cache_size_label()
        QtWidgets.QMessageBox.information(
            self, "Cache Cleared",
            f"Kitsu cache successfully cleaned!\nRemoved {files_rem} files ({freed_str} freed)."
        )

    def _on_connect_clicked(self):
        host = self.host_edit.text().strip()
        email = self.email_edit.text().strip()
        pwd = self.pass_edit.text().strip()
        if not host or not email:
            QtWidgets.QMessageBox.warning(self, "Input Required", "Please provide Kitsu Host URL and Email.")
            return

        self.status_lbl.setText("Connecting...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            auth_res = kitsu_client.login(host, email, pwd)
            token = auth_res.get("access_token") or auth_res.get("token") or kitsu_client.auth_token
            self._token = token
            self.status_lbl.setText("Connected successfully!")
            self.status_lbl.setStyleSheet("color: #30d158; font-size: 11px;")
            
            remember = self.chk_remember.isChecked()

            # Save in persistent QSettings
            self.qsettings.setValue("host", host)
            self.qsettings.setValue("email", email)
            self.qsettings.setValue("remember", remember)
            if remember:
                self.qsettings.setValue("password", pwd)
                self.qsettings.setValue("token", token or "")
            else:
                self.qsettings.remove("password")
                self.qsettings.remove("token")

            # Save in application prefs dict
            if isinstance(self.prefs, dict):
                self.prefs["kitsu_host"] = host
                self.prefs["kitsu_email"] = email
                self.prefs["kitsu_remember"] = remember
                if remember:
                    self.prefs["kitsu_password"] = pwd
                    self.prefs["kitsu_token"] = token or ""
                else:
                    self.prefs.pop("kitsu_password", None)
                    self.prefs.pop("kitsu_token", None)

                if self.parent() and hasattr(self.parent(), "_save_prefs"):
                    self.parent()._save_prefs()

            # Load projects
            self._load_projects()
        except Exception as e:
            self.status_lbl.setText("Connection failed")
            self.status_lbl.setStyleSheet("color: #ff453a; font-size: 11px;")
            QtWidgets.QMessageBox.critical(self, "Kitsu Error", str(e))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _load_projects(self):
        host = self.host_edit.text().strip()
        self.combo_project.blockSignals(True)
        self.combo_project.clear()
        try:
            self._projects_data = kitsu_client.get_projects(host=host, token=self._token)
            for p in self._projects_data:
                self.combo_project.addItem(p.get("name", "Unknown Project"), p.get("id"))
        except Exception as e:
            err_msg = str(e)
            email = self.email_edit.text().strip()
            pwd = self.pass_edit.text().strip()
            # If token expired/unauthorized and credentials present, attempt auto re-login
            if ("401" in err_msg or "Unauthorized" in err_msg) and email and pwd:
                try:
                    auth_res = kitsu_client.login(host, email, pwd)
                    self._token = auth_res.get("access_token") or auth_res.get("token") or kitsu_client.auth_token
                    self._projects_data = kitsu_client.get_projects(host=host, token=self._token)
                    for p in self._projects_data:
                        self.combo_project.addItem(p.get("name", "Unknown Project"), p.get("id"))
                except Exception as inner_e:
                    self.status_lbl.setText(f"Auth expired: {inner_e}")
                    self.status_lbl.setStyleSheet("color: #ff9500; font-size: 11px;")
            else:
                self.status_lbl.setText(f"Error loading projects: {e}")
                self.status_lbl.setStyleSheet("color: #ff453a; font-size: 11px;")
        finally:
            self.combo_project.blockSignals(False)

        if self._projects_data:
            self.status_lbl.setText(f"Loaded {len(self._projects_data)} project(s)")
            self.status_lbl.setStyleSheet("color: #30d158; font-size: 11px;")
            self._on_project_changed()

    def _on_project_changed(self):
        proj_id = self.combo_project.currentData()
        if not proj_id or not self._token:
            return
        host = self.host_edit.text().strip()
        self.combo_playlist.blockSignals(True)
        self.combo_playlist.clear()
        try:
            self._playlists_data = kitsu_client.get_playlists(project_id=proj_id, host=host, token=self._token)
            for pl in self._playlists_data:
                self.combo_playlist.addItem(pl.get("name", "Playlist"), pl.get("id"))
        finally:
            self.combo_playlist.blockSignals(False)

        if self._playlists_data:
            self._on_playlist_changed()
        else:
            self.shot_list.clear()
            self.btn_import.setEnabled(False)
            self.status_lbl.setText("No playlists found in project")

    def _on_playlist_changed(self):
        pl_id = self.combo_playlist.currentData()
        if not pl_id or not self._token:
            return
        host = self.host_edit.text().strip()
        self.shot_list.clear()
        try:
            self._current_shots_data = kitsu_client.get_playlist_shots(playlist_id=pl_id, host=host, token=self._token)
            for idx, s in enumerate(self._current_shots_data):
                name = s.get("name") or s.get("entity_name") or f"Shot {idx+1}"
                seq = s.get("sequence_name", "")
                task = s.get("task_name", "")
                text = f"{seq} / {name} ({task})" if seq and task else f"{seq} / {name}" if seq else f"{name} ({task})" if task else name
                self.shot_list.addItem(text)
            self.btn_import.setEnabled(len(self._current_shots_data) > 0)
            if self._current_shots_data:
                self.status_lbl.setText(f"Found {len(self._current_shots_data)} shot(s)")
                self.status_lbl.setStyleSheet("color: #30d158; font-size: 11px;")
            else:
                self.status_lbl.setText("Playlist is empty")
                self.status_lbl.setStyleSheet("color: #ff9500; font-size: 11px;")
        except Exception as e:
            self.btn_import.setEnabled(False)
            self.status_lbl.setText(f"Error loading playlist: {e}")
            self.status_lbl.setStyleSheet("color: #ff453a; font-size: 11px;")

    def _on_import_clicked(self):
        host = self.host_edit.text().strip()
        proj_id = self.combo_project.currentData()
        items: List[PlaylistItem] = []
        for idx, s in enumerate(self._current_shots_data):
            name = s.get("name") or s.get("entity_name") or f"Shot {idx+1}"
            seq = s.get("sequence_name", "")
            task = s.get("task_name", "")
            preview_file_id = s.get("preview_file_id")
            preview_url = s.get("preview_file_url", "")
            if not preview_url and preview_file_id:
                preview_url = f"{host.rstrip('/')}/api/movies/originals/preview-files/{preview_file_id}.mp4"
            elif preview_url and not preview_url.startswith("http"):
                preview_url = f"{host.rstrip('/')}{preview_url}"

            media_path = preview_url or s.get("file_path", "")
            if not media_path and isinstance(s.get("data"), dict):
                media_path = s["data"].get("file_path", "")

            shot_id = s.get("id") or s.get("entity_id")
            kitsu_url = kitsu_client.build_shot_url(shot_id=shot_id, project_id=proj_id)

            item = PlaylistItem(
                name=f"{seq}_{name}" if seq else name,
                media_path=media_path,
                sequence=seq,
                shot=name,
                task=task,
                kitsu_project_id=proj_id,
                kitsu_shot_id=shot_id,
                kitsu_task_id=s.get("task_id"),
                kitsu_preview_url=preview_url,
                kitsu_preview_id=preview_file_id,
                kitsu_url=kitsu_url,
            )
            items.append(item)

        self._selected_items = items
        pl_name = self.combo_playlist.currentText()
        self.playlist_selected.emit(items, pl_name)
        self.accept()

    def get_selected_playlist_items(self) -> List[PlaylistItem]:
        """Returns the list of PlaylistItem instances chosen by user."""
        return getattr(self, "_selected_items", [])


class KitsuPublishDialog(QtWidgets.QDialog):
    """Dialog to submit a supervisor review note, status update, and annotated snapshot to Kitsu."""

    def __init__(
        self,
        task_id: Optional[str] = None,
        shot_id: Optional[str] = None,
        shot_name: str = "Shot",
        preview_image_path: Optional[str] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        shot_context: Optional[dict] = None,
        annotated_image_path: Optional[str] = None,
        prefs: Optional[dict] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Publish Review to Kitsu")
        self.resize(500, 480)
        self.task_id = task_id
        self.shot_id = shot_id
        self.annotated_image_path = preview_image_path or annotated_image_path
        self.shot_context = shot_context or {}
        if "shot" not in self.shot_context:
            self.shot_context["shot"] = shot_name
        self.prefs = prefs or {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # Context Header
        hdr = QtWidgets.QFrame()
        hdr.setStyleSheet("background-color: #1e1e22; border-radius: 4px; padding: 6px;")
        hdr_layout = QtWidgets.QGridLayout(hdr)
        hdr_layout.addWidget(QtWidgets.QLabel("<b>Shot:</b>"), 0, 0)
        hdr_layout.addWidget(QtWidgets.QLabel(self.shot_context.get("shot", shot_name)), 0, 1)
        hdr_layout.addWidget(QtWidgets.QLabel("<b>Sequence:</b>"), 0, 2)
        hdr_layout.addWidget(QtWidgets.QLabel(self.shot_context.get("sequence", "—")), 0, 3)

        hdr_layout.addWidget(QtWidgets.QLabel("<b>Task:</b>"), 1, 0)
        hdr_layout.addWidget(QtWidgets.QLabel(self.shot_context.get("task", "comp")), 1, 1)
        hdr_layout.addWidget(QtWidgets.QLabel("<b>Version:</b>"), 1, 2)
        hdr_layout.addWidget(QtWidgets.QLabel(self.shot_context.get("version", "—")), 1, 3)
        layout.addWidget(hdr)

        # Task Selection Row
        task_row = QtWidgets.QHBoxLayout()
        task_row.addWidget(QtWidgets.QLabel("Target Task:"))
        self.task_combo = QtWidgets.QComboBox()

        # Fetch tasks for shot if available
        tasks = []
        if self.shot_id and kitsu_client.is_authenticated():
            try:
                tasks = kitsu_client.get_tasks_for_shot(self.shot_id)
            except Exception:
                tasks = []

        if tasks:
            for t in tasks:
                t_id = t.get("id")
                t_name = t.get("task_type_name") or t.get("name", "Task")
                t_status = t.get("task_status_name", "")
                lbl = f"{t_name} ({t_status})" if t_status else t_name
                self.task_combo.addItem(lbl, t_id)
                if self.task_id and t_id == self.task_id:
                    self.task_combo.setCurrentIndex(self.task_combo.count() - 1)
        else:
            default_name = self.shot_context.get("task", "comp")
            self.task_combo.addItem(f"{default_name} (Current Task)", self.task_id)

        task_row.addWidget(self.task_combo, stretch=1)
        layout.addLayout(task_row)

        # Status row
        status_row = QtWidgets.QHBoxLayout()
        status_row.addWidget(QtWidgets.QLabel("Status:"))
        self.status_combo = QtWidgets.QComboBox()

        statuses = []
        if kitsu_client.is_authenticated():
            try:
                statuses = kitsu_client.get_task_statuses()
            except Exception:
                statuses = []

        if statuses:
            for s in statuses:
                self.status_combo.addItem(s.get("name", "Status"), s.get("id"))
        else:
            self.status_combo.addItem("Approved", None)
            self.status_combo.addItem("Revise / Retake", None)
            self.status_combo.addItem("Work In Progress", None)
            self.status_combo.addItem("On Hold", None)
            self.status_combo.addItem("Comment Only", None)

        status_row.addWidget(self.status_combo, stretch=1)
        layout.addLayout(status_row)

        # Review Note
        layout.addWidget(QtWidgets.QLabel("Supervisor Review Note:"))
        self.note_edit = QtWidgets.QTextEdit()
        self.note_edit.setPlaceholderText("Enter review feedback, notes, or instructions for artist...")
        layout.addWidget(self.note_edit, stretch=1)

        # Attachment Indicator with Thumbnail
        if self.annotated_image_path and os.path.exists(self.annotated_image_path):
            att_box = QtWidgets.QHBoxLayout()
            att_thumb = QtWidgets.QLabel()
            att_thumb.setFixedSize(64, 36)
            att_thumb.setStyleSheet("border: 1px solid #3b82f6; border-radius: 3px;")
            pix = QtGui.QPixmap(self.annotated_image_path).scaled(64, 36, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation)
            att_thumb.setPixmap(pix)
            att_box.addWidget(att_thumb)

            att_lbl = QtWidgets.QLabel(f"Attached Annotated Frame Snapshot: {os.path.basename(self.annotated_image_path)}")
            att_lbl.setStyleSheet("color: #38bdf8; font-size: 11px;")
            att_box.addWidget(att_lbl)
            att_box.addStretch()
            layout.addLayout(att_box)

        # Buttons
        btn_box = QtWidgets.QHBoxLayout()
        btn_box.addStretch()

        self.btn_publish = QtWidgets.QPushButton("Publish to Kitsu")
        self.btn_publish.setStyleSheet("background-color: #0a84ff; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_publish.clicked.connect(self._on_publish_clicked)
        btn_box.addWidget(self.btn_publish)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        layout.addLayout(btn_box)

    def _on_publish_clicked(self):
        note = self.note_edit.toPlainText().strip()
        status_id = self.status_combo.currentData()
        target_task_id = self.task_combo.currentData() or self.task_id

        if not note:
            QtWidgets.QMessageBox.warning(self, "Note Required", "Please enter a review note before publishing.")
            return

        if not target_task_id:
            QtWidgets.QMessageBox.warning(self, "Task Required", "No valid task could be found to publish review note.")
            return

        if kitsu_client.is_authenticated():
            # Prevent double-click or duplicate publish submissions
            self.btn_publish.setEnabled(False)
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            preview_uploaded = False
            has_attachment = bool(self.annotated_image_path and os.path.exists(self.annotated_image_path))
            try:
                # post_task_comment automatically handles uploading and attaching the annotated snapshot once
                res = kitsu_client.post_task_comment(
                    target_task_id,
                    note,
                    task_status_id=status_id,
                    attachment_path=self.annotated_image_path if has_attachment else None
                )
                if isinstance(res, dict) and res.get("preview_file"):
                    preview_uploaded = True
            except Exception as e:
                self.btn_publish.setEnabled(True)
                QtWidgets.QApplication.restoreOverrideCursor()
                QtWidgets.QMessageBox.critical(self, "Publish Error", f"Failed to post comment to Kitsu:\n{e}")
                return
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

            if has_attachment and not preview_uploaded:
                print(f"[Kitsu] Notice: Review note posted, preview attachment may not have been accepted by server.")

        self.accept()

    def get_review_data(self) -> dict:
        return {
            "note": self.note_edit.toPlainText().strip(),
            "status": self.status_combo.currentText(),
            "status_id": self.status_combo.currentData(),
            "task_id": self.task_combo.currentData() or self.task_id,
            "image_path": self.annotated_image_path
        }
