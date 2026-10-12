"""First-launch setup wizard."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QRadioButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from Core import steam_scanner
from .actions import import_existing_folders


class SetupWizardDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Welcome to Mist — First Launch Setup")
        self.setFixedSize(620, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        # Wizard header
        self.header_title = QLabel("Initial Configuration")
        self.header_title.setObjectName("PageTitle")
        self.header_sub = QLabel("Configure your games directory and default sources to get started.")
        self.header_sub.setObjectName("Muted")
        layout.addWidget(self.header_title)
        layout.addWidget(self.header_sub)

        # Stack of steps
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Step 1: Folders
        self.step_folders = QWidget()
        sf_layout = QVBoxLayout(self.step_folders)
        sf_layout.setSpacing(14)
        sf_layout.addWidget(QLabel("<b>1. Game Library Folders</b>"))

        sf_layout.addWidget(QLabel("Main Games Directory (where downloaded games are installed):"))
        f_row1 = QHBoxLayout()
        self.games_dir_edit = QLineEdit(str(self.ctx.config.games_dir))
        browse1 = QPushButton("Browse…")
        browse1.clicked.connect(self._browse_games_dir)
        f_row1.addWidget(self.games_dir_edit, 1)
        f_row1.addWidget(browse1)
        sf_layout.addLayout(f_row1)

        sf_layout.addWidget(QLabel("Temporary Download Directory (archives are unpacked here):"))
        f_row2 = QHBoxLayout()
        self.temp_dir_edit = QLineEdit(str(self.ctx.config.temp_dir))
        browse2 = QPushButton("Browse…")
        browse2.clicked.connect(self._browse_temp_dir)
        f_row2.addWidget(self.temp_dir_edit, 1)
        f_row2.addWidget(browse2)
        sf_layout.addLayout(f_row2)
        sf_layout.addStretch(1)
        self.stack.addWidget(self.step_folders)

        # Step 2: Store source
        self.step_source = QWidget()
        ss_layout = QVBoxLayout(self.step_source)
        ss_layout.setSpacing(12)
        ss_layout.addWidget(QLabel("<b>2. Default Store Source</b>"))
        ss_layout.addWidget(QLabel("Select your preferred primary catalog source:"))

        self.source_group = QButtonGroup(self)
        self.rb_anker = QRadioButton("Anker Games (Direct catalog & fast downloads)")
        self.rb_steamrip = QRadioButton("SteamRip (Pre-installed Steam games & direct mirrors)")

        self.source_group.addButton(self.rb_anker, 1)
        self.source_group.addButton(self.rb_steamrip, 2)

        default_src = self.ctx.config.get("default_source", "ankergames")
        if default_src == "steamrip":
            self.rb_steamrip.setChecked(True)
        else:
            self.rb_anker.setChecked(True)

        ss_layout.addWidget(self.rb_anker)
        ss_layout.addWidget(self.rb_steamrip)
        ss_layout.addStretch(1)
        self.stack.addWidget(self.step_source)

        # Step 3: Steam integration & Initial scan
        self.step_scan = QWidget()
        sc_layout = QVBoxLayout(self.step_scan)
        sc_layout.setSpacing(14)
        sc_layout.addWidget(QLabel("<b>3. Library Scanning & Integrations</b>"))

        self.cb_steam = QCheckBox("Automatically detect and import installed Steam games (read-only)")
        self.cb_steam.setChecked(bool(self.ctx.config.get("auto_scan_steam", True)))
        sc_layout.addWidget(self.cb_steam)

        self.cb_scan_games = QCheckBox("Scan games install folder for existing installations")
        self.cb_scan_games.setChecked(True)
        sc_layout.addWidget(self.cb_scan_games)

        self.scan_status = QLabel("Ready to configure your library.")
        self.scan_status.setObjectName("Muted")
        sc_layout.addWidget(self.scan_status)
        sc_layout.addStretch(1)
        self.stack.addWidget(self.step_scan)

        # Navigation buttons
        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Back")
        self.prev_btn.clicked.connect(self._prev_step)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(self._next_step)
        nav_row.addWidget(self.prev_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.next_btn)
        layout.addLayout(nav_row)

        self._update_nav()

    def _browse_games_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose Games Directory", self.games_dir_edit.text())
        if d:
            self.games_dir_edit.setText(os.path.normpath(d))

    def _browse_temp_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose Temp Directory", self.temp_dir_edit.text())
        if d:
            self.temp_dir_edit.setText(os.path.normpath(d))

    def _update_nav(self):
        idx = self.stack.currentIndex()
        self.prev_btn.setEnabled(idx > 0)
        if idx == self.stack.count() - 1:
            self.next_btn.setText("Finish Setup ✔")
        else:
            self.next_btn.setText("Next ▶")

    def _prev_step(self):
        if self.stack.currentIndex() > 0:
            self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
            self._update_nav()

    def _next_step(self):
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._update_nav()
        else:
            self._finish()

    def _finish(self):
        g_dir = Path(self.games_dir_edit.text().strip())
        t_dir = Path(self.temp_dir_edit.text().strip())
        g_dir.mkdir(parents=True, exist_ok=True)
        t_dir.mkdir(parents=True, exist_ok=True)

        chosen_source = "ankergames"
        if self.rb_steamrip.isChecked():
            chosen_source = "steamrip"

        self.ctx.config.update({
            "first_run_complete": True,
            "games_dir": str(g_dir),
            "temp_dir": str(t_dir),
            "default_source": chosen_source,
            "auto_scan_steam": self.cb_steam.isChecked(),
        })

        # Run scans if enabled
        if self.cb_steam.isChecked():
            try:
                steam_games = steam_scanner.scan_steam()
                self.ctx.library.import_steam(steam_games)
            except Exception:
                pass

        if self.cb_scan_games.isChecked() and g_dir.is_dir():
            try:
                import_existing_folders(self.ctx, g_dir)
            except Exception:
                pass

        self.accept()
