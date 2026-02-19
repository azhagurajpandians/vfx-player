
from PyQt6 import QtWidgets, QtCore

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent, prefs: dict, color_manager):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(500, 400)
        self.prefs = prefs.copy() # Work on valid copy
        self.cm = color_manager
        
        self.layout = QtWidgets.QVBoxLayout(self)
        
        # Tabs for categories
        self.tabs = QtWidgets.QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # --- General / Cache Tab ---
        self.gen_tab = QtWidgets.QWidget()
        self.gen_layout = QtWidgets.QVBoxLayout(self.gen_tab)
        self.tabs.addTab(self.gen_tab, "General")
        
        # Cache
        cache_group = QtWidgets.QGroupBox("Cache")
        cg_layout = QtWidgets.QFormLayout(cache_group)
        self.cache_spin = QtWidgets.QSpinBox()
        self.cache_spin.setRange(50, 10000)
        self.cache_spin.setSingleStep(50)
        self.cache_spin.setValue(self.prefs.get('cache_size', 500))
        self.cache_spin.setSuffix(" frames")
        cg_layout.addRow("Capacity:", self.cache_spin)
        cg_layout.addRow("Capacity:", self.cache_spin)
        self.gen_layout.addWidget(cache_group)
        
        # OCIO Config
        ocio_group = QtWidgets.QGroupBox("OpenColorIO Configuration")
        ocio_layout = QtWidgets.QHBoxLayout(ocio_group)
        
        self.ocio_path_edit = QtWidgets.QLineEdit()
        # Load from prefs or env
        current_ocio = self.prefs.get('ocio_config', "")
        if not current_ocio and 'OCIO' in QtCore.QProcessEnvironment.systemEnvironment().keys():
             import os
             current_ocio = os.environ.get('OCIO', "")
        self.ocio_path_edit.setText(current_ocio)
        self.ocio_path_edit.setPlaceholderText("Path to config.ocio (leave empty to use env)")
        
        self.ocio_browse_btn = QtWidgets.QPushButton("Browse...")
        self.ocio_browse_btn.clicked.connect(self._browse_ocio)
        
        ocio_layout.addWidget(self.ocio_path_edit)
        ocio_layout.addWidget(self.ocio_browse_btn)
        
        self.gen_layout.addWidget(ocio_group)
        self.gen_layout.addStretch()
        
        # --- Defaults Tab ---
        self.def_tab = QtWidgets.QWidget()
        self.def_layout = QtWidgets.QVBoxLayout(self.def_tab)
        self.tabs.addTab(self.def_tab, "Defaults")
        
        # EXR Defaults
        exr_group = QtWidgets.QGroupBox("EXR / Image Sequence Defaults")
        exr_layout = QtWidgets.QFormLayout(exr_group)
        
        self.exr_in_combo = QtWidgets.QComboBox()
        self.exr_in_combo.addItem("Use Last Used", None)
        self.exr_in_combo.addItems(self.cm.input_choices)
        
        self.exr_out_combo = QtWidgets.QComboBox()
        self.exr_out_combo.addItem("Use Last Used", None)
        self.exr_out_combo.addItems(self.cm.output_choices)
        
        # Set current values
        exr_defs = self.prefs.get('defaults', {}).get('exr', {})
        self._set_combo(self.exr_in_combo, exr_defs.get('input'))
        self._set_combo(self.exr_out_combo, exr_defs.get('output'))
        
        exr_layout.addRow("Input Transform:", self.exr_in_combo)
        exr_layout.addRow("Output Transform:", self.exr_out_combo)
        self.def_layout.addWidget(exr_group)
        
        # MOV Defaults
        mov_group = QtWidgets.QGroupBox("MOV / Video Defaults")
        mov_layout = QtWidgets.QFormLayout(mov_group)
        
        self.mov_in_combo = QtWidgets.QComboBox()
        self.mov_in_combo.addItem("Use Last Used", None)
        self.mov_in_combo.addItems(self.cm.input_choices)
        
        self.mov_out_combo = QtWidgets.QComboBox()
        self.mov_out_combo.addItem("Use Last Used", None)
        self.mov_out_combo.addItems(self.cm.output_choices)
        
        mov_defs = self.prefs.get('defaults', {}).get('mov', {})
        self._set_combo(self.mov_in_combo, mov_defs.get('input'))
        self._set_combo(self.mov_out_combo, mov_defs.get('output'))
        
        mov_layout.addRow("Input Transform:", self.mov_in_combo)
        mov_layout.addRow("Output Transform:", self.mov_out_combo)
        self.def_layout.addWidget(mov_group)
        self.def_layout.addStretch()
        
        # --- Buttons ---
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | 
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self.layout.addWidget(btns)
        
    def _browse_ocio(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select OCIO Config", "", "OCIO Files (*.ocio);;All Files (*.*)"
        )
        if path:
            self.ocio_path_edit.setText(path)

    def _set_combo(self, combo, value):
        if value and value in self.cm.input_choices + self.cm.output_choices:
            combo.setCurrentText(value)
        else:
            combo.setCurrentIndex(0)
            
    def get_prefs(self):
        # Update prefs dict from UI
        self.prefs['cache_size'] = self.cache_spin.value()
        self.prefs['ocio_config'] = self.ocio_path_edit.text().strip()
        
        if 'defaults' not in self.prefs:
            self.prefs['defaults'] = {}
            
        self.prefs['defaults']['exr'] = {
            'input': self.exr_in_combo.currentText() if self.exr_in_combo.currentIndex() > 0 else None,
            'output': self.exr_out_combo.currentText() if self.exr_out_combo.currentIndex() > 0 else None
        }
        
        self.prefs['defaults']['mov'] = {
            'input': self.mov_in_combo.currentText() if self.mov_in_combo.currentIndex() > 0 else None,
            'output': self.mov_out_combo.currentText() if self.mov_out_combo.currentIndex() > 0 else None
        }
        
        return self.prefs
