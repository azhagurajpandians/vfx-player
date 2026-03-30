
from PyQt6 import QtWidgets, QtCore
from core.player_core import PlaybackStrategy

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
        
        # Cache (DJV-style Memory Cache)
        cache_group = QtWidgets.QGroupBox("Memory Cache")
        cg_layout = QtWidgets.QVBoxLayout(cache_group)
        
        cache_desc = QtWidgets.QLabel(
            "The memory cache stores decoded frames in RAM for instant playback.\n"
            "When disabled, frames are streamed directly from disk."
        )
        cache_desc.setWordWrap(True)
        cache_desc.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 6px;")
        cg_layout.addWidget(cache_desc)
        
        self.cache_enable_chk = QtWidgets.QCheckBox("Enable the memory cache")
        self.cache_enable_chk.setChecked(self.prefs.get('cache_enabled', True))
        cg_layout.addWidget(self.cache_enable_chk)
        
        gb_row = QtWidgets.QHBoxLayout()
        gb_label = QtWidgets.QLabel("Cache size (gigabytes):")
        self.cache_gb_spin = QtWidgets.QDoubleSpinBox()
        self.cache_gb_spin.setRange(0.5, 64.0)
        self.cache_gb_spin.setSingleStep(0.5)
        self.cache_gb_spin.setDecimals(2)
        self.cache_gb_spin.setValue(self.prefs.get('cache_gb', 4.0))
        self.cache_gb_spin.setSuffix(" GB")
        gb_row.addWidget(gb_label)
        gb_row.addWidget(self.cache_gb_spin)
        gb_row.addStretch()
        cg_layout.addLayout(gb_row)
        
        self.preload_chk = QtWidgets.QCheckBox("Pre-load cache frames")
        self.preload_chk.setChecked(self.prefs.get('preload_cache', True))
        self.preload_chk.setToolTip("When enabled, frames ahead of the playhead are loaded into cache automatically.")
        cg_layout.addWidget(self.preload_chk)
        
        self.show_cached_chk = QtWidgets.QCheckBox("Display cached frames in timeline")
        self.show_cached_chk.setChecked(self.prefs.get('show_cached_timeline', True))
        self.show_cached_chk.setToolTip("Shows a green indicator on the timeline for frames that are currently cached in memory.")
        cg_layout.addWidget(self.show_cached_chk)

        strat_row = QtWidgets.QHBoxLayout()
        strat_lbl = QtWidgets.QLabel("Default Playback Strategy:")
        self.strategy_combo = QtWidgets.QComboBox()
        self.strategy_combo.addItems([
            "Performance (Full Cache)",
            "Progressive (Sequential)",
            "Stream Only (No RAM Cache)",
            "Read-behind Buffer"
        ])
        
        # Mapping for setting initial value
        strat_map = {
            PlaybackStrategy.PERFORMANCE: 0,
            PlaybackStrategy.PROGRESSIVE: 1,
            PlaybackStrategy.STREAM: 2,
            PlaybackStrategy.READ_BEHIND: 3
        }
        current_val = self.prefs.get('playback_strategy', 'performance')
        try:
            current_enum = PlaybackStrategy(current_val)
            self.strategy_combo.setCurrentIndex(strat_map.get(current_enum, 0))
        except ValueError:
            self.strategy_combo.setCurrentIndex(0)
            
        strat_row.addWidget(strat_lbl)
        strat_row.addWidget(self.strategy_combo)
        strat_row.addStretch()
        cg_layout.addLayout(strat_row)

        
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
        self.prefs['cache_enabled'] = self.cache_enable_chk.isChecked()
        self.prefs['cache_gb'] = self.cache_gb_spin.value()
        self.prefs['preload_cache'] = self.preload_chk.isChecked()
        self.prefs['show_cached_timeline'] = self.show_cached_chk.isChecked()
        # Map back to string value
        strat_opts = ['performance', 'progressive', 'stream', 'readbehind']
        self.prefs['playback_strategy'] = strat_opts[self.strategy_combo.currentIndex()]
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
