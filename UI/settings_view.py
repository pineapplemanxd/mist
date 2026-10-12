"""Settings page: directories, theme, downloads, steam scanner, cache management."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from Core import steam_scanner
from Core.controller import ControllerManager
from Core.paths import IMAGE_CACHE_DIR, SCRIPTS_DIR
from . import theme
from .actions import import_existing_folders, open_folder
from .common import fmt_size, theme_color


class SettingsView(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 22, 28, 20)
        main_layout.setSpacing(14)

        title = QLabel("SETTINGS")
        title.setObjectName("PageTitle")
        main_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_body = QWidget()
        scroll_body.setObjectName("ScrollBody")
        body = QVBoxLayout(scroll_body)
        body.setContentsMargins(0, 0, 10, 20)
        body.setSpacing(18)
        scroll.setWidget(scroll_body)
        main_layout.addWidget(scroll, 1)

        # 1. DIRECTORIES ----------------------------------------------------
        gb_dirs = QGroupBox("Directories & Storage")
        gl1 = QVBoxLayout(gb_dirs)
        gl1.setSpacing(10)

        gl1.addWidget(QLabel("Default Games Installation Directory:"))
        r1 = QHBoxLayout()
        self.games_dir_edit = QLineEdit(str(ctx.config.games_dir))
        self.games_dir_edit.setReadOnly(True)
        b_change_games = QPushButton("Change…")
        b_change_games.clicked.connect(self._change_games_dir)
        b_open_games = QPushButton("Open Folder")
        b_open_games.clicked.connect(lambda: open_folder(str(ctx.config.games_dir), self))
        r1.addWidget(self.games_dir_edit, 1)
        r1.addWidget(b_change_games)
        r1.addWidget(b_open_games)
        gl1.addLayout(r1)

        gl1.addWidget(QLabel("Temporary Downloads Directory:"))
        r2 = QHBoxLayout()
        self.temp_dir_edit = QLineEdit(str(ctx.config.temp_dir))
        self.temp_dir_edit.setReadOnly(True)
        b_change_temp = QPushButton("Change…")
        b_change_temp.clicked.connect(self._change_temp_dir)
        b_open_temp = QPushButton("Open Folder")
        b_open_temp.clicked.connect(lambda: open_folder(str(ctx.config.temp_dir), self))
        r2.addWidget(self.temp_dir_edit, 1)
        r2.addWidget(b_change_temp)
        r2.addWidget(b_open_temp)
        gl1.addLayout(r2)

        self.cb_delete_archive = QCheckBox("Delete temporary ZIP archive after successful extraction")
        self.cb_delete_archive.setChecked(bool(ctx.config.get("delete_archive_after_install", True)))
        self.cb_delete_archive.toggled.connect(lambda v: ctx.config.set("delete_archive_after_install", v))
        gl1.addWidget(self.cb_delete_archive)

        b_scan_games = QPushButton("Scan Games Folder for Existing Installations")
        b_scan_games.clicked.connect(self._scan_games_folder)
        gl1.addWidget(b_scan_games)
        body.addWidget(gb_dirs)

        # 2. STORE & DOWNLOADS ----------------------------------------------
        gb_dl = QGroupBox("Downloads & Store Sources")
        gl2 = QVBoxLayout(gb_dl)
        gl2.setSpacing(12)

        # Default source combo
        r_src = QHBoxLayout()
        r_src.addWidget(QLabel("Default Store Source:"))
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(180)
        for s in ctx.sources.all():
            self.source_combo.addItem(s.name, s.id)
        idx = self.source_combo.findData(ctx.config.get("default_source", "ankergames"))
        self.source_combo.setCurrentIndex(max(0, idx))
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        r_src.addWidget(self.source_combo)
        r_src.addStretch(1)
        gl2.addLayout(r_src)

        # Max concurrent downloads
        r_conc = QHBoxLayout()
        r_conc.addWidget(QLabel("Maximum Concurrent Downloads:"))
        self.spin_conc = QSpinBox()
        self.spin_conc.setRange(1, 10)
        self.spin_conc.setValue(int(ctx.config.get("max_concurrent_downloads", 2)))
        self.spin_conc.valueChanged.connect(lambda v: ctx.config.set("max_concurrent_downloads", v))
        r_conc.addWidget(self.spin_conc)
        r_conc.addStretch(1)
        gl2.addLayout(r_conc)

        # Bandwidth limit
        r_limit = QHBoxLayout()
        r_limit.addWidget(QLabel("Bandwidth Limit (KiB/s, 0 = unlimited):"))
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(0, 500000)
        self.spin_limit.setSingleStep(500)
        self.spin_limit.setValue(int(ctx.config.get("bandwidth_limit_kbps", 0)))
        self.spin_limit.valueChanged.connect(self._on_bandwidth_changed)
        r_limit.addWidget(self.spin_limit)
        r_limit.addStretch(1)
        gl2.addLayout(r_limit)

        # Open Scripts folder
        r_scripts = QHBoxLayout()
        b_open_scripts = QPushButton("Open Scripts Folder (add/edit download sources)")
        b_open_scripts.clicked.connect(lambda: open_folder(str(SCRIPTS_DIR), self))
        r_scripts.addWidget(b_open_scripts)
        r_scripts.addStretch(1)
        gl2.addLayout(r_scripts)
        body.addWidget(gb_dl)

        # 3. STEAM INTEGRATION ---------------------------------------------
        gb_steam = QGroupBox("Steam Integration (Read-Only)")
        gl3 = QVBoxLayout(gb_steam)
        gl3.setSpacing(10)

        self.cb_steam_auto = QCheckBox("Automatically detect and import Steam library games on startup")
        self.cb_steam_auto.setChecked(bool(ctx.config.get("auto_scan_steam", True)))
        self.cb_steam_auto.toggled.connect(lambda v: ctx.config.set("auto_scan_steam", v))
        gl3.addWidget(self.cb_steam_auto)

        r_steam_btn = QHBoxLayout()
        b_scan_steam = QPushButton("Scan Steam Library Now")
        b_scan_steam.clicked.connect(self._scan_steam_now)
        self.steam_status = QLabel()
        self.steam_status.setObjectName("Muted")
        r_steam_btn.addWidget(b_scan_steam)
        r_steam_btn.addWidget(self.steam_status)
        r_steam_btn.addStretch(1)
        gl3.addLayout(r_steam_btn)
        body.addWidget(gb_steam)

        # 4. APPEARANCE, THEMES & LAYOUT -----------------------------------
        gb_app = QGroupBox("Appearance, Themes & Layout")
        gl4 = QVBoxLayout(gb_app)
        gl4.setSpacing(12)

        # Quick Theme Preset Selector Buttons (1-click preview and switch)
        gl4.addWidget(QLabel("Quick Theme Switcher:"))
        self.preset_cards_layout = QHBoxLayout()
        self.preset_cards_layout.setSpacing(8)
        self.preset_buttons: dict[str, QPushButton] = {}
        for p in theme.list_presets():
            btn_p = QPushButton(p["name"])
            btn_p.setToolTip(p.get("tagline", p.get("name")))
            btn_p.setCheckable(True)
            btn_p.clicked.connect(lambda _, pid=p["id"]: self._select_preset_card(pid))
            self.preset_buttons[p["id"]] = btn_p
            self.preset_cards_layout.addWidget(btn_p)
        gl4.addLayout(self.preset_cards_layout)

        # Theme preset selection row
        r_theme = QHBoxLayout()
        r_theme.addWidget(QLabel("Theme Preset:"))
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(260)
        for p in theme.list_presets():
            self.theme_combo.addItem(p["name"], p["id"])
        curr_preset = self.ctx.config.get_theme_preset()
        resolved_preset = theme.get_preset(curr_preset)["id"]
        idx_preset = self.theme_combo.findData(resolved_preset)
        if idx_preset >= 0:
            self.theme_combo.setCurrentIndex(idx_preset)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        r_theme.addWidget(self.theme_combo)
        r_theme.addStretch(1)
        gl4.addLayout(r_theme)

        # Navigation layout selector row
        r_layout = QHBoxLayout()
        r_layout.addWidget(QLabel("Navigation Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.setMinimumWidth(260)
        self.layout_combo.addItem("Preset Default (Auto)", "preset")
        self.layout_combo.addItem("Top Navigation Bar (Horizontal Tabs)", "top_nav")
        self.layout_combo.addItem("Left Sidebar (Vertical Drawer)", "sidebar")
        curr_layout = self.ctx.config.get("layout_mode", "preset")
        idx_layout = self.layout_combo.findData(curr_layout)
        if idx_layout >= 0:
            self.layout_combo.setCurrentIndex(idx_layout)
        self.layout_combo.currentIndexChanged.connect(self._on_layout_mode_changed)
        r_layout.addWidget(self.layout_combo)
        r_layout.addStretch(1)
        gl4.addLayout(r_layout)

        # Theme Preview & Highlights Card
        self.preview_card = QFrame()
        self.preview_card.setObjectName("Card")
        prev_layout = QVBoxLayout(self.preview_card)
        prev_layout.setContentsMargins(14, 12, 14, 12)
        prev_layout.setSpacing(10)

        self.lbl_preset_desc = QLabel()
        self.lbl_preset_desc.setWordWrap(True)
        self.lbl_preset_desc.setObjectName("Muted")
        prev_layout.addWidget(self.lbl_preset_desc)

        # Palette color swatches
        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        self.swatch_bg = QLabel("BG")
        self.swatch_surface = QLabel("Card")
        self.swatch_accent = QLabel("Accent")
        self.swatch_success = QLabel("Action")
        for lbl in (self.swatch_bg, self.swatch_surface, self.swatch_accent, self.swatch_success):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedHeight(26)
            lbl.setMinimumWidth(84)
            swatches_row.addWidget(lbl)
        swatches_row.addStretch(1)
        prev_layout.addLayout(swatches_row)

        self.lbl_preset_layout_info = QLabel()
        self.lbl_preset_layout_info.setObjectName("Muted")
        prev_layout.addWidget(self.lbl_preset_layout_info)

        gl4.addWidget(self.preview_card)
        self._refresh_theme_preview()

        r_cache = QHBoxLayout()
        self.cache_lbl = QLabel(f"Image Cache: {self._get_cache_size()}")
        b_clear_cache = QPushButton("Clear Image Cache")
        b_clear_cache.clicked.connect(self._clear_cache)
        r_cache.addWidget(self.cache_lbl)
        r_cache.addWidget(b_clear_cache)
        r_cache.addStretch(1)
        gl4.addLayout(r_cache)

        r_wiz = QHBoxLayout()
        b_rerun_wiz = QPushButton("Run Setup Wizard Again…")
        b_rerun_wiz.clicked.connect(self._rerun_wizard)
        r_wiz.addWidget(b_rerun_wiz)
        r_wiz.addStretch(1)
        gl4.addLayout(r_wiz)
        body.addWidget(gb_app)

        # 5. CONTROLLER & BIG PICTURE MODE ----------------------------------
        gb_ctrl = QGroupBox("Controller & Big Picture Mode")
        gl5 = QVBoxLayout(gb_ctrl)
        gl5.setSpacing(12)

        r_bp_style = QHBoxLayout()
        r_bp_style.addWidget(QLabel("Big Picture GUI Style:"))
        self.bp_style_combo = QComboBox()
        self.bp_style_combo.addItem("Classic (Steam Big Picture)", "classic")
        self.bp_style_combo.addItem("Console (PlayStation 5)", "console")
        curr_bp = ctx.config.get("big_picture_style", "classic")
        self.bp_style_combo.setCurrentIndex(1 if curr_bp == "console" else 0)
        self.bp_style_combo.currentIndexChanged.connect(self._on_bp_style_changed)
        r_bp_style.addWidget(self.bp_style_combo)
        r_bp_style.addStretch(1)
        gl5.addLayout(r_bp_style)

        # Controller connection status
        r_ctrl_stat = QHBoxLayout()
        cm = ControllerManager.get_instance()
        self.lbl_ctrl_stat = QLabel(cm.get_status_text())
        self.lbl_ctrl_stat.setObjectName("Muted")
        cm.signals.connected.connect(lambda *_: self._refresh_ctrl_status())
        cm.signals.disconnected.connect(lambda *_: self._refresh_ctrl_status())
        r_ctrl_stat.addWidget(QLabel("Gamepad Status:"))
        r_ctrl_stat.addWidget(self.lbl_ctrl_stat)
        r_ctrl_stat.addStretch(1)
        gl5.addLayout(r_ctrl_stat)

        r_bp_btn = QHBoxLayout()
        b_open_bp = QPushButton("Launch Big Picture Mode (or press Guide / Xbox / PS button)")
        b_open_bp.setObjectName("Play")
        b_open_bp.clicked.connect(self._open_big_picture)
        r_bp_btn.addWidget(b_open_bp)
        r_bp_btn.addStretch(1)
        gl5.addLayout(r_bp_btn)

        lbl_bp_hint = QLabel("When a controller is connected, pressing the main Guide/Xbox/PS button or Back+Start opens Big Picture Mode.")
        lbl_bp_hint.setObjectName("Muted")
        gl5.addWidget(lbl_bp_hint)
        body.addWidget(gb_ctrl)

    def _change_games_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Games Installation Directory", str(self.ctx.config.games_dir))
        if d:
            p = os.path.normpath(d)
            self.ctx.config.set("games_dir", p)
            self.games_dir_edit.setText(p)
            self.ctx.toast("Games installation directory updated")

    def _change_temp_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Temporary Downloads Directory", str(self.ctx.config.temp_dir))
        if d:
            p = os.path.normpath(d)
            self.ctx.config.set("temp_dir", p)
            self.temp_dir_edit.setText(p)
            self.ctx.toast("Temporary downloads directory updated")

    def _on_source_changed(self):
        src_id = self.source_combo.currentData()
        self.ctx.config.set("default_source", src_id)
        self.ctx.toast("Default source updated")

    def _on_bandwidth_changed(self, val: int):
        self.ctx.config.set("bandwidth_limit_kbps", val)
        self.ctx.downloads.set_bandwidth_limit(val)

    def _select_preset_card(self, pid: str) -> None:
        """Select a preset via one-click quick preset card buttons."""
        idx = self.theme_combo.findData(pid)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

    def _refresh_theme_preview(self):
        preset_id = self.theme_combo.currentData() if hasattr(self, "theme_combo") and self.theme_combo else "steam_modern"
        p = theme.get_preset(preset_id or "steam_modern")
        pal = p.get("palette", theme.DARK)
        self.lbl_preset_desc.setText(p.get("description", ""))

        # Sync active state on quick preset buttons
        for pid, btn in getattr(self, "preset_buttons", {}).items():
            is_active = (pid == p["id"])
            btn.setChecked(is_active)

        def _style_swatch(lbl: QLabel, bg_color: str, text: str):
            lbl.setText(f"{text}: {bg_color}")
            c = theme.QColor(bg_color)
            fg = "#111111" if c.lightness() > 140 else "#ffffff"
            border = "border: 1px solid rgba(0, 0, 0, 0.25);" if c.lightness() > 140 else "border: 1px solid rgba(255, 255, 255, 0.15);"
            lbl.setStyleSheet(f"background: {bg_color}; color: {fg}; {border} border-radius: 3px; font-size: 8pt; font-weight: bold; padding: 2px 4px;")

        _style_swatch(self.swatch_bg, pal.get("bg", "#000000"), "BG")
        _style_swatch(self.swatch_surface, pal.get("surface", "#222222"), "Card")
        _style_swatch(self.swatch_accent, pal.get("accent", "#3399ff"), "Accent")
        _style_swatch(self.swatch_success, pal.get("success", "#16a34a"), "Play")

        layout_choice = self.layout_combo.currentData() if hasattr(self, "layout_combo") else "preset"
        if layout_choice == "top_nav":
            eff_layout = "Top Navigation Bar (Horizontal Tabs)"
        elif layout_choice == "sidebar":
            eff_layout = "Left Sidebar (Vertical Drawer)"
        else:
            eff_layout = "Top Navigation Bar" if p.get("layout_mode") == "top_nav" else "Left Sidebar"
            eff_layout += " (Preset Default)"
        self.lbl_preset_layout_info.setText(f"Active Navigation Layout: {eff_layout}")

    def _on_theme_changed(self):
        preset_id = self.theme_combo.currentData() or "steam_modern"
        layout_mode = self.layout_combo.currentData() if hasattr(self, "layout_combo") else "preset"
        self._refresh_theme_preview()

        if self.ctx.window and hasattr(self.ctx.window, "set_theme"):
            self.ctx.window.set_theme(preset_id, layout_mode)
        else:
            self.ctx.config.update({"theme_preset": preset_id, "theme": preset_id})
            if hasattr(self, "layout_combo"):
                self.ctx.config.set("layout_mode", layout_mode)
            app = QApplication.instance()
            if app:
                theme.apply_theme(app, preset_id)

        p = theme.get_preset(preset_id)
        self.ctx.toast(f"Theme switched to {p['name']}")

    def _on_layout_mode_changed(self):
        layout_mode = self.layout_combo.currentData()
        self.ctx.config.set("layout_mode", layout_mode)
        preset_id = self.theme_combo.currentData() or "steam_modern"
        if self.ctx.window and hasattr(self.ctx.window, "set_theme"):
            self.ctx.window.set_theme(preset_id, layout_mode)
        self._refresh_theme_preview()
        self.ctx.toast(f"Layout mode set to {self.layout_combo.currentText()}")

    def on_theme_updated(self):
        """Called when theme is updated externally or on window refresh."""
        curr_preset = self.ctx.config.get_theme_preset()
        idx_preset = self.theme_combo.findData(curr_preset)
        if idx_preset >= 0 and self.theme_combo.currentIndex() != idx_preset:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(idx_preset)
            self.theme_combo.blockSignals(False)
        self._refresh_theme_preview()

    def _scan_steam_now(self):
        self.steam_status.setText("Scanning Steam libraries…")
        try:
            games = steam_scanner.scan_steam()
            added, stale = self.ctx.library.import_steam(games)
            self.steam_status.setText(f"Found {len(games)} games ({added} synced).")
            self.ctx.toast(f"Steam scan complete: {len(games)} games detected")
        except Exception as exc:
            self.steam_status.setText("Scan failed")
            QMessageBox.warning(self, "Steam Scan Error", str(exc))

    def _scan_games_folder(self):
        games_dir = self.ctx.config.games_dir
        if not games_dir.is_dir():
            QMessageBox.information(self, "Scan folder", "Games directory does not exist yet.")
            return
        added = import_existing_folders(self.ctx, games_dir)
        self.ctx.toast(f"Games folder scan finished: {added} new game(s) imported")

    def _get_cache_size(self) -> str:
        sz = 0
        if IMAGE_CACHE_DIR.exists():
            for f in IMAGE_CACHE_DIR.iterdir():
                try:
                    sz += f.stat().st_size
                except OSError:
                    pass
        return fmt_size(sz)

    def _clear_cache(self):
        removed = self.ctx.images.clear_disk_cache()
        self.cache_lbl.setText(f"Image Cache: {self._get_cache_size()}")
        self.ctx.toast(f"Cleared {fmt_size(removed)} of cached images")

    def _rerun_wizard(self):
        from .wizard import SetupWizardDialog
        dlg = SetupWizardDialog(self.ctx, self)
        if dlg.exec():
            self.games_dir_edit.setText(str(self.ctx.config.games_dir))
            self.temp_dir_edit.setText(str(self.ctx.config.temp_dir))
            idx = self.source_combo.findData(self.ctx.config.get("default_source"))
            self.source_combo.setCurrentIndex(max(0, idx))
            self.cb_steam_auto.setChecked(bool(self.ctx.config.get("auto_scan_steam", True)))
            self.ctx.toast("Configuration updated")

    def _on_bp_style_changed(self):
        style = self.bp_style_combo.currentData()
        self.ctx.config.set("big_picture_style", style)
        if self.ctx.window and hasattr(self.ctx.window, "bp_window") and self.ctx.window.bp_window and self.ctx.window.bp_window.isVisible():
            self.ctx.window.bp_window._set_style(style)
        disp = "PlayStation 5" if style == "console" else "Steam Big Picture"
        self.ctx.toast(f"Big Picture style set to {disp}")

    def _refresh_ctrl_status(self):
        self.lbl_ctrl_stat.setText(ControllerManager.get_instance().get_status_text())

    def _open_big_picture(self):
        if self.ctx.window and hasattr(self.ctx.window, "open_big_picture"):
            self.ctx.window.open_big_picture()
