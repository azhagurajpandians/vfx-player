import os
import json
from PyQt6 import QtWidgets, QtCore, QtGui

class MetadataDialog(QtWidgets.QDialog):
    """
    Modeless dialog showing detailed metadata for the current frame/media.
    Supports real-time search, dynamic updating on frame changes, copying selection,
    and exporting metadata.
    """
    def __init__(self, parent, core):
        super().__init__(parent)
        self.core = core
        self.setWindowTitle("Media Metadata Viewer")
        self.resize(550, 600)
        self.setMinimumSize(400, 300)
        
        # Make modeless so user can work in player while dialog is open
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        
        # Stylesheet matching player dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #aaa;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #222;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ddd;
                selection-background-color: #0078d4;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
            QCheckBox {
                color: #ccc;
                spacing: 8px;
            }
            QTableWidget {
                background-color: #1a1a1a;
                color: #ddd;
                gridline-color: #2a2a2a;
                border: 1px solid #333;
                border-radius: 4px;
                selection-background-color: #264f78;
                selection-color: #fff;
            }
            QHeaderView::section {
                background-color: #262626;
                color: #aaa;
                padding: 6px;
                border: 1px solid #333;
                font-weight: bold;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 14px;
                color: #e0e0e0;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #383838;
                border-color: #555;
            }
            QPushButton:pressed {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(12)

        # Header info
        self.info_lbl = QtWidgets.QLabel("Showing metadata for current frame.")
        self.info_lbl.setStyleSheet("color: #0078d4; font-weight: bold;")
        self.layout.addWidget(self.info_lbl)

        # Search Bar & Dynamic check row
        controls_layout = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search keys or values...")
        self.search_input.textChanged.connect(self.filter_table)
        controls_layout.addWidget(self.search_input)

        self.dynamic_update_checkbox = QtWidgets.QCheckBox("Follow playhead")
        self.dynamic_update_checkbox.setChecked(True)
        self.dynamic_update_checkbox.setToolTip("Automatically refresh metadata when changing frames.")
        controls_layout.addWidget(self.dynamic_update_checkbox)
        self.layout.addLayout(controls_layout)

        # Table Widget
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 200)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        
        # Grid lines styling
        self.table.setShowGrid(True)
        self.layout.addWidget(self.table)

        # Bottom Actions row
        btn_layout = QtWidgets.QHBoxLayout()
        
        self.copy_sel_btn = QtWidgets.QPushButton("Copy Selection")
        self.copy_sel_btn.clicked.connect(self.copy_selection)
        btn_layout.addWidget(self.copy_sel_btn)

        self.copy_all_btn = QtWidgets.QPushButton("Copy All (JSON)")
        self.copy_all_btn.clicked.connect(self.copy_all)
        btn_layout.addWidget(self.copy_all_btn)

        self.export_btn = QtWidgets.QPushButton("Export TXT...")
        self.export_btn.clicked.connect(self.export_txt)
        btn_layout.addWidget(self.export_btn)

        btn_layout.addStretch()

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)

        self.layout.addLayout(btn_layout)

        # Keep current metadata storage
        self.current_metadata = {}
        self.current_index = -1

    def update_metadata(self, frame_index: int):
        """Fetch and populate metadata for the given frame index."""
        if not self.core.media:
            self.table.setRowCount(0)
            self.current_metadata = {}
            self.info_lbl.setText("No media loaded.")
            return
            
        self.current_index = frame_index
        metadata = self.core.get_metadata_for_frame(frame_index)
        self.current_metadata = metadata

        if self.core.media.type == 'sequence':
            filename = os.path.basename(self.core.sequence[frame_index])
            self.info_lbl.setText(f"Frame {frame_index + 1} | File: {filename}")
        else:
            filename = os.path.basename(self.core.media.path)
            self.info_lbl.setText(f"Video file: {filename}")

        # Temporarily disable sorting while loading to prevent row mismatches
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(metadata))
        
        for row, (k, v) in enumerate(sorted(metadata.items())):
            # Key cell
            key_item = QtWidgets.QTableWidgetItem(k)
            key_item.setFont(QtGui.QFont("Consolas", 9))
            key_item.setForeground(QtGui.QColor("#888" if k.startswith("oiio:") or k.startswith("openexr:") else "#e0e0e0"))
            
            # Value cell
            val_str = str(v)
            val_item = QtWidgets.QTableWidgetItem(val_str)
            val_item.setFont(QtGui.QFont("Consolas", 9))
            val_item.setToolTip(val_str)
            
            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, val_item)
            
        self.table.setSortingEnabled(True)
        self.filter_table()

    def filter_table(self):
        """Filters the rows in the table based on the search query."""
        query = self.search_input.text().lower().strip()
        for r in range(self.table.rowCount()):
            k_item = self.table.item(r, 0)
            v_item = self.table.item(r, 1)
            if not k_item or not v_item:
                continue
            
            match = (query in k_item.text().lower()) or (query in v_item.text().lower())
            self.table.setRowHidden(r, not match)

    def copy_selection(self):
        """Copy selected rows to clipboard as tab-separated values."""
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            return
            
        clipboard_text = []
        for r in range(self.table.rowCount()):
            # Must check if row is selected and not hidden by filter
            if self.table.isRowHidden(r):
                continue
            
            is_selected = False
            for ran in selected_ranges:
                if ran.topRow() <= r <= ran.bottomRow():
                    is_selected = True
                    break
                    
            if is_selected:
                k = self.table.item(r, 0).text()
                v = self.table.item(r, 1).text()
                clipboard_text.append(f"{k}\t{v}")
                
        if clipboard_text:
            QtWidgets.QApplication.clipboard().setText("\n".join(clipboard_text))

    def copy_all(self):
        """Copy all metadata as formatted JSON to the clipboard."""
        if self.current_metadata:
            json_str = json.dumps(self.current_metadata, indent=4)
            QtWidgets.QApplication.clipboard().setText(json_str)

    def export_txt(self):
        """Export all current metadata to a text file."""
        if not self.current_metadata:
            return
            
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Metadata", "", "Text Files (*.txt);;JSON Files (*.json)"
        )
        if not path:
            return
            
        try:
            with open(path, 'w', encoding='utf-8') as f:
                if path.endswith('.json'):
                    json.dump(self.current_metadata, f, indent=4)
                else:
                    f.write(f"Metadata Export from VFXPlayer\n")
                    f.write(f"================================\n")
                    if self.core.media.type == 'sequence':
                        f.write(f"Frame Index: {self.current_index}\n")
                        f.write(f"Source File: {self.core.sequence[self.current_index]}\n\n")
                    else:
                        f.write(f"Source Video: {self.core.media.path}\n\n")
                        
                    for k, v in sorted(self.current_metadata.items()):
                        f.write(f"{k}: {v}\n")
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Metadata saved to:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export Error", f"Failed to save file: {e}")
