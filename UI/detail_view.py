"""Game detail page: hero banner, metadata, actions, screenshots, and system requirements."""
from __future__ import annotations

import re
import shutil
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from Core.logger import get_logger
from Core.sources import CatalogItem
from . import actions
from .common import (FlowLayout, chip, draw_badge, draw_pixmap_cover, fmt_ago,
                     fmt_playtime, fmt_size, muted, paint_placeholder,
                     rounded_path, run_async, theme_color)

log = get_logger(__name__)


def _sanitize_title(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[\s\W_]+", "", text.lower())


class ScreenshotViewer(QDialog):
    """Enlarged screenshot popup modal."""

    def __init__(self, ctx, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Screenshot Preview")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignCenter)
        self.img_lbl.setText("Loading image…")
        layout.addWidget(self.img_lbl)

        dpr = self.devicePixelRatioF()
        target_size = QSize(int(980 * dpr), int(630 * dpr))
        pm = ctx.images.get(url, target_size, crop=False)
        self.ctx = ctx
        self._on_ready_cb = None
        if pm and not pm.isNull():
            self.img_lbl.setPixmap(pm)
        else:
            def on_ready(key: str):
                if url in key:
                    try:
                        p = ctx.images.get(url, target_size, crop=False)
                        if p and not p.isNull() and not self.img_lbl.isHidden():
                            self.img_lbl.setPixmap(p)
                    except (RuntimeError, ReferenceError):
                        pass
            self._on_ready_cb = on_ready
            ctx.images.image_ready.connect(on_ready)

    def closeEvent(self, e):
        if self._on_ready_cb:
            try:
                self.ctx.images.image_ready.disconnect(self._on_ready_cb)
            except Exception:
                pass
        super().closeEvent(e)


class InstallDialog(QDialog):
    """Steam-style installation dialog: choose download provider/source and install folder."""

    def __init__(self, ctx, initial_item: CatalogItem, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.item = initial_item
        self.selected_item = initial_item
        self.selected_source_id = initial_item.source

        self.setWindowTitle(f"Install — {initial_item.title}")
        self.resize(520, 480)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header: Steam Game Header
        header = QHBoxLayout()
        header.setSpacing(16)

        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(60, 90)
        self.cover_lbl.setObjectName("Card")
        self.cover_lbl.setAlignment(Qt.AlignCenter)
        dpr = self.devicePixelRatioF()
        if initial_item.cover_url:
            pm = ctx.images.get(initial_item.cover_url, QSize(int(60 * dpr), int(90 * dpr)))
            if pm and not pm.isNull():
                self.cover_lbl.setPixmap(pm)
            else:
                self.cover_lbl.setText("Cover")
        else:
            self.cover_lbl.setText("Cover")
        header.addWidget(self.cover_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        title_lbl = QLabel(initial_item.title)
        title_lbl.setStyleSheet("font-size: 14pt; font-weight: 800; color: #ffffff;")
        info_col.addWidget(title_lbl)

        sub_parts = []
        if initial_item.version:
            sub_parts.append(initial_item.version)
        if initial_item.release_date:
            sub_parts.append(initial_item.release_date)
        meta_lbl = QLabel("  ·  ".join(sub_parts) or "Ready to install")
        meta_lbl.setObjectName("Muted")
        info_col.addWidget(meta_lbl)
        info_col.addStretch(1)
        header.addLayout(info_col, 1)
        layout.addLayout(header)

        # Separator
        sep1 = QFrame()
        sep1.setObjectName("Separator")
        layout.addWidget(sep1)

        # Source / Provider Selection Box
        src_box = QGroupBox("DOWNLOAD SOURCE")
        src_layout = QVBoxLayout(src_box)
        src_layout.setSpacing(8)

        self.source_combo = QComboBox()
        self.source_combo.setMinimumHeight(32)
        src_layout.addWidget(self.source_combo)

        self.mirror_combo = QComboBox()
        self.mirror_combo.setMinimumHeight(28)
        self.mirror_combo.setVisible(False)
        src_layout.addWidget(self.mirror_combo)

        self.source_desc_lbl = QLabel()
        self.source_desc_lbl.setObjectName("Muted")
        self.source_desc_lbl.setWordWrap(True)
        src_layout.addWidget(self.source_desc_lbl)
        layout.addWidget(src_box)

        # Install Location Box
        loc_box = QGroupBox("INSTALL LOCATION")
        loc_layout = QVBoxLayout(loc_box)
        loc_layout.setSpacing(8)

        loc_row = QHBoxLayout()
        loc_row.setSpacing(8)
        default_dir = str(ctx.config.games_dir)
        self.dir_edit = QLineEdit(default_dir)
        self.dir_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._browse_dir)
        loc_row.addWidget(self.dir_edit, 1)
        loc_row.addWidget(self.browse_btn)
        loc_layout.addLayout(loc_row)

        self.space_lbl = QLabel()
        self.space_lbl.setObjectName("Muted")
        loc_layout.addWidget(self.space_lbl)
        layout.addWidget(loc_box)

        layout.addStretch(1)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.install_btn = QPushButton("INSTALL")
        self.install_btn.setObjectName("Play")
        self.install_btn.setMinimumWidth(120)
        self.install_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.install_btn)
        layout.addLayout(btn_row)

        self._load_sources()
        self.source_combo.currentIndexChanged.connect(self._on_source_selected)
        self._update_space_info()

    def _load_sources(self):
        self.source_combo.blockSignals(True)
        self.source_combo.clear()

        # Primary option: the current catalog item
        curr_src = self.ctx.sources.get(self.item.source)
        curr_name = curr_src.name if curr_src else self.item.source
        curr_sz = fmt_size(self.item.size_bytes)
        display_label = f"{curr_name} — {curr_sz}" if self.item.size_bytes else curr_name
        self.source_combo.addItem(f"● {display_label} (Current)", (self.item.source, self.item))

        # Check other downloadable sources
        for s in self.ctx.sources.all():
            if s.id != self.item.source and s.can_download:
                self.source_combo.addItem(f"⏳ Searching {s.name}…", (s.id, None))

        self.source_combo.blockSignals(False)
        self._on_source_selected(0)

        # Try to resolve or search matching items from other sources in background
        title = self.item.title
        clean_title = _sanitize_title(title)

        def search_others():
            results = {}
            for s in self.ctx.sources.all():
                if s.id != self.item.source and s.can_download:
                    try:
                        sp = s.search(query=title, page=1, page_size=6)
                        for it in sp.items:
                            clean_it = _sanitize_title(it.title)
                            if clean_it == clean_title or clean_title in clean_it or clean_it in clean_target:
                                results[s.id] = it
                                break
                    except Exception as exc:
                        log.debug("Provider search failed for %s: %s", s.id, exc)
            return results

        def on_others_found(found_dict):
            for i in range(self.source_combo.count()):
                data = self.source_combo.itemData(i)
                if not data:
                    continue
                s_id, existing_item = data
                if s_id == self.item.source:
                    continue
                s_name = self.ctx.sources.display_name(s_id)
                if s_id in found_dict:
                    matched_item = found_dict[s_id]
                    sz = fmt_size(matched_item.size_bytes)
                    txt = f"● {s_name} — {sz}"
                    self.source_combo.setItemText(i, txt)
                    self.source_combo.setItemData(i, (s_id, matched_item))
                else:
                    self.source_combo.setItemText(i, f"✕ {s_name} (Not available)")
                    self.source_combo.setItemData(i, (s_id, None))
            self._on_source_selected(self.source_combo.currentIndex())

        clean_target = clean_title
        run_async(search_others, on_others_found, context=self)

    def _on_source_selected(self, idx: int):
        data = self.source_combo.itemData(idx)
        if not data:
            return
        src_id, item = data
        self.selected_source_id = src_id
        src_name = self.ctx.sources.display_name(self.selected_source_id)

        if item is not None:
            self.selected_item = item
            self.install_btn.setEnabled(True)
            sz_str = fmt_size(self.selected_item.size_bytes)
            self.source_desc_lbl.setText(f"Provider: {src_name}  ·  Estimated download size: {sz_str}")
            self.source_desc_lbl.setStyleSheet("")

            # Populate mirror links if provider offers multiple mirrors/links
            links = (self.selected_item.extra.get("links") or self.selected_item.extra.get("mirrors")) if self.selected_item.extra else None
            if links and isinstance(links, list) and len(links) > 1:
                self.mirror_combo.blockSignals(True)
                self.mirror_combo.clear()
                for lk in links:
                    lbl = lk.get("name") or lk.get("link") if isinstance(lk, dict) else str(lk)
                    self.mirror_combo.addItem(f"Mirror: {lbl}", lk)
                self.mirror_combo.blockSignals(False)
                self.mirror_combo.setVisible(True)
            else:
                self.mirror_combo.setVisible(False)
        else:
            self.selected_item = None
            self.install_btn.setEnabled(False)
            self.source_desc_lbl.setText(f"Provider: {src_name}  ·  Game is not available from this provider.")
            self.source_desc_lbl.setStyleSheet("color: #e5a100; font-weight: bold;")
            self.mirror_combo.setVisible(False)

        self._update_space_info()

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose Installation Folder", self.dir_edit.text())
        if chosen:
            self.dir_edit.setText(chosen)
            self._update_space_info()

    def _update_space_info(self):
        path_str = self.dir_edit.text()
        req_bytes = self.selected_item.size_bytes if self.selected_item else 0
        try:
            drive_path = Path(path_str).anchor or path_str
            usage = shutil.disk_usage(drive_path)
            free_bytes = usage.free
            req_str = fmt_size(req_bytes) if req_bytes else "Unknown"
            free_str = fmt_size(free_bytes)
            if req_bytes and free_bytes < req_bytes:
                self.space_lbl.setText(f"⚠ Low Disk Space! Required: {req_str}  ·  Available: {free_str}")
                self.space_lbl.setStyleSheet("color: #e5a100; font-weight: bold;")
            else:
                self.space_lbl.setText(f"Disk Space Required: {req_str}  ·  Available: {free_str} on {drive_path}")
                self.space_lbl.setStyleSheet("")
        except Exception:
            self.space_lbl.setText("Space required: " + (fmt_size(req_bytes) if req_bytes else "—"))

    def get_result(self) -> tuple[str, CatalogItem, str]:
        item = self.selected_item or self.item
        if self.mirror_combo.isVisible() and self.mirror_combo.currentData():
            item.extra["selected_mirror"] = self.mirror_combo.currentData()
        return self.selected_source_id, item, self.dir_edit.text()


class HeroBanner(QWidget):
    """Pre-rendered cached hero banner for 60 FPS zero-overhead rendering."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.hero_url = ""
        self.cover_url = ""
        self.title_text = ""
        self._cached_pixmap: QPixmap | None = None
        self.setFixedHeight(240)

    def set_data(self, hero_url: str, cover_url: str, title: str):
        self.hero_url = hero_url
        self.cover_url = cover_url
        self.title_text = title
        self._render_cache()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render_cache()

    def _render_cache(self, trigger_update: bool = True):
        w, h = max(1, self.width()), max(1, self.height())
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("#171a21"))

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRect(0, 0, w, h)

        pm_hero = None
        if self.hero_url:
            pm_hero = self.ctx.images.get(self.hero_url, QSize(int(w * dpr), int(h * dpr)), crop=True)

        if pm_hero and not pm_hero.isNull():
            draw_pixmap_cover(p, r, pm_hero)
        else:
            paint_placeholder(p, r, self.title_text, font_px=36)

        # Steam dark gradient blend into background
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(23, 26, 33, 90))
        grad.setColorAt(0.5, QColor(23, 26, 33, 160))
        grad.setColorAt(1, QColor(23, 26, 33, 255))
        p.fillRect(r, grad)
        p.end()

        self._cached_pixmap = pm
        if trigger_update:
            self.update()

    def paintEvent(self, e):
        dpr = self.devicePixelRatioF()
        target_w = int(max(1, self.width()) * dpr)
        if not self._cached_pixmap or self._cached_pixmap.isNull() or self._cached_pixmap.width() != target_w:
            self._render_cache(trigger_update=False)

        if self._cached_pixmap and not self._cached_pixmap.isNull():
            p = QPainter(self)
            p.drawPixmap(0, 0, self._cached_pixmap)


class GameDetailView(QWidget):
    back_requested = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self.game_id: int | None = None
        self.catalog_item: CatalogItem | None = None

        self._curr_cover = ""
        self._curr_hero = ""
        self._screenshot_urls: list[str] = []
        self._screenshot_labels: list[QLabel] = []
        self._pending_img_update = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Back navigation bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(20, 14, 20, 10)
        self.back_btn = QPushButton("◀  BACK")
        self.back_btn.setObjectName("NavButton")
        self.back_btn.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.back_btn)
        top_bar.addStretch(1)
        main_layout.addLayout(top_bar)

        # Scroll Area for page content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll_body = QWidget()
        self.scroll_body.setObjectName("ScrollBody")
        self.body_layout = QVBoxLayout(self.scroll_body)
        self.body_layout.setContentsMargins(32, 0, 32, 32)
        self.body_layout.setSpacing(18)
        self.scroll.setWidget(self.scroll_body)
        main_layout.addWidget(self.scroll)

        # Hero Banner
        self.hero = HeroBanner(ctx)
        self.body_layout.addWidget(self.hero)

        # Header info (Cover + Details + Actions)
        header_row = QHBoxLayout()
        header_row.setSpacing(24)

        # Cover Thumbnail
        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(140, 210)
        self.cover_lbl.setObjectName("Card")
        self.cover_lbl.setAlignment(Qt.AlignCenter)
        header_row.addWidget(self.cover_lbl)

        # Middle Info
        mid_col = QVBoxLayout()
        mid_col.setSpacing(8)

        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("HeroTitle")
        mid_col.addWidget(self.title_lbl)

        self.meta_lbl = QLabel()
        self.meta_lbl.setObjectName("HeroSub")
        mid_col.addWidget(self.meta_lbl)

        self.genres_container = QWidget()
        self.genres_layout = FlowLayout(self.genres_container, spacing=6)
        mid_col.addWidget(self.genres_container)
        mid_col.addStretch(1)

        # Source Selector row on detail page
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        src_tag_lbl = QLabel("Source:")
        src_tag_lbl.setObjectName("Muted")
        self.source_selector = QComboBox()
        self.source_selector.setMinimumWidth(180)
        self.source_selector.currentIndexChanged.connect(self._on_detail_source_changed)
        source_row.addWidget(src_tag_lbl)
        source_row.addWidget(self.source_selector)
        source_row.addStretch(1)
        mid_col.addLayout(source_row)

        # Action Buttons row
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(10)
        mid_col.addLayout(self.actions_row)

        self._active_dl_id: str | None = None
        self.btn_status = QPushButton()
        self.btn_status.setEnabled(False)
        self.btn_status.setVisible(False)
        self.actions_row.addWidget(self.btn_status)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel_download)
        self.actions_row.addWidget(self.btn_cancel)

        self.btn_play = QPushButton("▶  Play Game")
        self.btn_play.setObjectName("Play")
        self.btn_play.setVisible(False)
        self.btn_play.clicked.connect(self._on_play_game)
        self.actions_row.addWidget(self.btn_play)

        self.btn_install = QPushButton("⤓  Install Game")
        self.btn_install.setObjectName("Play")
        self.btn_install.setVisible(False)
        self.btn_install.clicked.connect(self._start_download)
        self.actions_row.addWidget(self.btn_install)

        self.btn_favorite = QPushButton("☆ Favorite")
        self.btn_favorite.setVisible(False)
        self.btn_favorite.clicked.connect(self._on_toggle_favorite)
        self.actions_row.addWidget(self.btn_favorite)

        self.btn_uninstall = QPushButton("Uninstall")
        self.btn_uninstall.setObjectName("Danger")
        self.btn_uninstall.setVisible(False)
        self.btn_uninstall.clicked.connect(self._uninstall)
        self.actions_row.addWidget(self.btn_uninstall)

        self.btn_store = QPushButton("↗  View Store Page")
        self.btn_store.setObjectName("Primary")
        self.btn_store.setVisible(False)
        self.btn_store.clicked.connect(self._open_store_page)
        self.actions_row.addWidget(self.btn_store)

        self.btn_steamdb = QPushButton("↗  SteamDB")
        self.btn_steamdb.setToolTip("View game stats, updates, and info on SteamDB")
        self.btn_steamdb.clicked.connect(self._open_steamdb)
        self.actions_row.addWidget(self.btn_steamdb)

        header_row.addLayout(mid_col, 1)
        self.body_layout.addLayout(header_row)

        # Separator
        sep = QFrame()
        sep.setObjectName("Separator")
        self.body_layout.addWidget(sep)

        # Metadata cards grid (Playtime, Last played, Size, Location, Version)
        self.stats_grid = QHBoxLayout()
        self.stats_grid.setSpacing(16)
        self.card_playtime = self._create_stat_card("PLAYTIME", "0 h")
        self.card_last_played = self._create_stat_card("LAST PLAYED", "Never")
        self.card_size = self._create_stat_card("SIZE", "—")
        self.card_source = self._create_stat_card("SOURCE", "—")
        self.stats_grid.addWidget(self.card_playtime)
        self.stats_grid.addWidget(self.card_last_played)
        self.stats_grid.addWidget(self.card_size)
        self.stats_grid.addWidget(self.card_source)
        self.body_layout.addLayout(self.stats_grid)

        # Location box
        self.loc_box = QFrame()
        self.loc_box.setObjectName("Card")
        loc_l = QHBoxLayout(self.loc_box)
        loc_l.setContentsMargins(14, 10, 14, 10)
        self.loc_lbl = QLabel("Install Folder: —")
        self.open_folder_btn = QPushButton("Browse Folder")
        self.open_folder_btn.clicked.connect(self._open_install_folder)
        self.change_exe_btn = QPushButton("Set Executable…")
        self.change_exe_btn.clicked.connect(self._change_exe)
        loc_l.addWidget(self.loc_lbl, 1)
        loc_l.addWidget(self.change_exe_btn)
        loc_l.addWidget(self.open_folder_btn)
        self.body_layout.addWidget(self.loc_box)

        # Description Section
        desc_sec = QLabel("About this game")
        desc_sec.setObjectName("SectionTitle")
        self.body_layout.addWidget(desc_sec)
        self.desc_lbl = QLabel()
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body_layout.addWidget(self.desc_lbl)

        # Screenshots Gallery
        self.screen_sec = QLabel("Screenshots")
        self.screen_sec.setObjectName("SectionTitle")
        self.body_layout.addWidget(self.screen_sec)

        self.screen_scroll = QScrollArea()
        self.screen_scroll.setFixedHeight(170)
        self.screen_scroll.setWidgetResizable(True)
        self.screen_scroll.setFrameShape(QFrame.NoFrame)
        self.screen_container = QWidget()
        self.screen_row = QHBoxLayout(self.screen_container)
        self.screen_row.setContentsMargins(0, 0, 0, 0)
        self.screen_row.setSpacing(12)
        self.screen_scroll.setWidget(self.screen_container)
        self.body_layout.addWidget(self.screen_scroll)

        # System Requirements Section
        self.req_sec = QLabel("System Requirements")
        self.req_sec.setObjectName("SectionTitle")
        self.body_layout.addWidget(self.req_sec)
        self.req_lbl = QLabel()
        self.req_lbl.setWordWrap(True)
        self.req_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body_layout.addWidget(self.req_lbl)

        # Debounced image update timer to prevent UI thread stuttering
        self._img_debounce = QTimer(self, singleShot=True, interval=50, timeout=self._update_images)

        # Update hooks
        ctx.images.image_ready.connect(self._on_image_ready)
        ctx.library.game_updated.connect(self._on_game_updated)
        ctx.library.running_changed.connect(lambda *_: self._refresh_actions())
        ctx.downloads.task_updated.connect(lambda *_: self._refresh_actions())

    def _create_stat_card(self, title: str, val: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        l = QVBoxLayout(card)
        l.setContentsMargins(14, 12, 14, 12)
        l.setSpacing(4)
        lbl_t = QLabel(title)
        lbl_t.setObjectName("Muted")
        f = lbl_t.font()
        f.setPixelSize(10)
        f.setBold(True)
        lbl_t.setFont(f)
        lbl_v = QLabel(val)
        fv = lbl_v.font()
        fv.setPixelSize(13)
        fv.setBold(True)
        lbl_v.setFont(fv)
        l.addWidget(lbl_t)
        l.addWidget(lbl_v)
        card.setProperty("val_lbl", lbl_v)
        return card

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_pending_img_update", False):
            self._pending_img_update = False
            self.hero._render_cache()
            self._update_images()

    def _on_image_ready(self, key: str) -> None:
        if not self.isVisible():
            self._pending_img_update = True
            return
        rel_hero = bool(self._curr_hero and self._curr_hero in key)
        rel_cover = bool(self._curr_cover and self._curr_cover in key)
        rel_shots = any(u in key for u in self._screenshot_urls)
        if rel_hero:
            self.hero._render_cache()
        if rel_cover or rel_shots:
            self._img_debounce.start()

    def load_library_game(self, game_id: int):
        self.scroll.verticalScrollBar().setValue(0)
        self.game_id = game_id
        self.catalog_item = None
        g = self.ctx.library.game(game_id)
        if not g:
            return
        self._populate(
            title=g["title"],
            cover_url=g.get("cover_url", ""),
            hero_url=g.get("hero_url", ""),
            developer=g.get("developer", ""),
            publisher=g.get("publisher", ""),
            release_date=g.get("release_date", ""),
            genres=g.get("genres") or [],
            description=g.get("description", ""),
            sys_reqs=g.get("system_requirements", ""),
            screenshots=g.get("screenshots") or [],
            source=g.get("source", "manual"),
            version=g.get("version", ""),
            size_bytes=g.get("size_bytes", 0),
            install_dir=g.get("install_dir", ""),
            playtime=g.get("playtime_seconds", 0),
            last_played=g.get("last_played", 0),
            installed=bool(g.get("installed")),
            favorite=bool(g.get("favorite")),
            store_url=g.get("launch_uri", ""),
        )

    def load_catalog_item(self, item: CatalogItem):
        self.scroll.verticalScrollBar().setValue(0)
        self.catalog_item = item
        existing = self.ctx.library.find(item.source, item.id)
        self.game_id = existing["id"] if existing else None

        # Fetch detailed data asynchronously from the source
        src = self.ctx.sources.get(item.source)
        if src:
            def fetch():
                return src.details(item)

            def on_done(detailed: CatalogItem):
                if self.catalog_item == item:
                    if not detailed.genres and item.genres:
                        detailed.genres = list(item.genres)
                    if not detailed.cover_url and item.cover_url:
                        detailed.cover_url = item.cover_url
                    if not detailed.hero_url and item.hero_url:
                        detailed.hero_url = item.hero_url
                    self.catalog_item = detailed
                    self._populate_from_item(detailed, existing)

            run_async(fetch, on_done, context=self)

        self._populate_from_item(item, existing)

    def _populate_from_item(self, item: CatalogItem, existing: dict | None):
        g = existing or {}
        self._populate(
            title=item.title,
            cover_url=item.cover_url or g.get("cover_url", ""),
            hero_url=item.hero_url or g.get("hero_url", ""),
            developer=item.developer or g.get("developer", ""),
            publisher=item.publisher or g.get("publisher", ""),
            release_date=item.release_date or g.get("release_date", ""),
            genres=item.genres or g.get("genres") or [],
            description=item.description or item.short_description or g.get("description", ""),
            sys_reqs=item.system_requirements or g.get("system_requirements", ""),
            screenshots=item.screenshots or g.get("screenshots") or [],
            source=item.source,
            version=item.version or g.get("version", ""),
            size_bytes=item.size_bytes or g.get("size_bytes", 0),
            install_dir=g.get("install_dir", ""),
            playtime=g.get("playtime_seconds", 0),
            last_played=g.get("last_played", 0),
            installed=bool(g.get("installed")),
            favorite=bool(g.get("favorite")),
            store_url=item.store_url,
        )

    def _populate(self, title: str, cover_url: str, hero_url: str, developer: str, publisher: str,
                  release_date: str, genres: list[str], description: str, sys_reqs: str,
                  screenshots: list[str], source: str, version: str, size_bytes: int,
                  install_dir: str, playtime: int, last_played: int, installed: bool,
                  favorite: bool, store_url: str):
        self._curr_cover = cover_url
        self._curr_hero = hero_url
        self.hero.set_data(hero_url, cover_url, title)

        self.title_lbl.setText(title)
        meta_parts = []
        if developer:
            meta_parts.append(f"Developer: {developer}")
        if publisher and publisher != developer:
            meta_parts.append(f"Publisher: {publisher}")
        if release_date:
            meta_parts.append(f"Released: {release_date}")
        if version:
            meta_parts.append(version)
        self.meta_lbl.setText("  ·  ".join(meta_parts))

        # Update genres
        while self.genres_layout.count():
            item = self.genres_layout.takeAt(0)
            if item and item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
        for gn in genres:
            self.genres_layout.addWidget(chip(gn, self.genres_container))

        # Update source selector
        self.source_selector.blockSignals(True)
        self.source_selector.clear()
        target_idx = 0
        for i, s in enumerate(self.ctx.sources.all()):
            self.source_selector.addItem(s.name, s.id)
            if s.id == source:
                target_idx = i
        self.source_selector.setCurrentIndex(target_idx)
        self.source_selector.blockSignals(False)

        # Update Stats Cards
        self.card_playtime.property("val_lbl").setText(fmt_playtime(playtime))
        self.card_last_played.property("val_lbl").setText(fmt_ago(last_played))
        self.card_size.property("val_lbl").setText(fmt_size(size_bytes))
        self.card_source.property("val_lbl").setText(self.ctx.sources.display_name(source))

        # Install location box
        if installed and install_dir:
            self.loc_lbl.setText(f"Install Folder: {install_dir}")
            self.loc_box.setVisible(True)
            self.change_exe_btn.setVisible(source != "steam")
        else:
            self.loc_box.setVisible(False)

        # Description
        self.desc_lbl.setText(description or "No description provided.")

        # Re-use screenshot labels to prevent widget thrashing
        self._screenshot_urls = screenshots or []
        if self._screenshot_urls:
            self.screen_sec.setVisible(True)
            self.screen_scroll.setVisible(True)
            while len(self._screenshot_labels) < len(self._screenshot_urls):
                thumb = QLabel()
                thumb.setFixedSize(220, 130)
                thumb.setObjectName("Card")
                thumb.setAlignment(Qt.AlignCenter)
                thumb.setCursor(Qt.PointingHandCursor)
                self._screenshot_labels.append(thumb)
                self.screen_row.addWidget(thumb)

            for i, s_url in enumerate(self._screenshot_urls):
                lbl = self._screenshot_labels[i]
                lbl.setVisible(True)
                lbl.mousePressEvent = lambda e, u=s_url: self._view_screenshot(u)

            for i in range(len(self._screenshot_urls), len(self._screenshot_labels)):
                self._screenshot_labels[i].setVisible(False)
        else:
            self.screen_sec.setVisible(False)
            self.screen_scroll.setVisible(False)
            for lbl in self._screenshot_labels:
                lbl.setVisible(False)

        # System Requirements
        if sys_reqs:
            self.req_sec.setVisible(True)
            self.req_lbl.setVisible(True)
            self.req_lbl.setText(sys_reqs)
        else:
            self.req_sec.setVisible(False)
            self.req_lbl.setVisible(False)

        self._refresh_actions()
        self._update_images()

    def _on_detail_source_changed(self, idx: int):
        new_source_id = self.source_selector.itemData(idx)
        if not new_source_id or not self.catalog_item:
            return
        if self.catalog_item.source == new_source_id:
            return

        target_source = self.ctx.sources.get(new_source_id)
        if not target_source:
            return

        title = self.catalog_item.title
        clean_target = _sanitize_title(title)

        def search_source():
            try:
                sp = target_source.search(query=title, page=1, page_size=6)
                for it in sp.items:
                    clean_it = _sanitize_title(it.title)
                    if clean_it == clean_target or clean_target in clean_it or clean_it in clean_target:
                        return it
            except Exception as exc:
                log.warning("Source switch search failed for %s: %s", new_source_id, exc)
            return None

        def on_search_done(matched: CatalogItem | None):
            if matched:
                self.load_catalog_item(matched)
                self.ctx.toast(f"Switched source to {target_source.name}")
            else:
                self.ctx.toast(f"'{title}' is not available on {target_source.name}")
                # Reset source selector combo back to current item's source
                self.source_selector.blockSignals(True)
                for i in range(self.source_selector.count()):
                    if self.source_selector.itemData(i) == self.catalog_item.source:
                        self.source_selector.setCurrentIndex(i)
                        break
                self.source_selector.blockSignals(False)

        run_async(search_source, on_search_done, context=self)

    def _on_cancel_download(self):
        if self._active_dl_id:
            self.ctx.downloads.cancel(self._active_dl_id)

    def _on_play_game(self):
        if self.game_id:
            actions.launch_game(self.ctx, self.game_id, self)

    def _on_toggle_favorite(self):
        if self.game_id:
            actions.toggle_favorite(self.ctx, self.game_id)
            self._refresh_actions()

    def _refresh_actions(self):
        self.btn_status.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_play.setVisible(False)
        self.btn_install.setVisible(False)
        self.btn_store.setVisible(False)
        self.btn_favorite.setVisible(False)
        self.btn_uninstall.setVisible(False)
        self.btn_steamdb.setVisible(True)

        gid = self.game_id
        g = self.ctx.library.game(gid) if gid else None
        item = self.catalog_item
        source_id = g["source"] if g else (item.source if item else "ankergames")
        item_id = g["source_id"] if g else (item.id if item else "")
        active_dl = self.ctx.downloads.find_active(source_id, item_id)

        if active_dl:
            self._active_dl_id = active_dl.id
            self.btn_status.setText(f"⏳ {active_dl.status.value} ({int(active_dl.progress * 100)}%)")
            self.btn_status.setVisible(True)
            self.btn_cancel.setVisible(True)
            return

        self._active_dl_id = None

        if g and g.get("installed"):
            running = self.ctx.library.is_running(gid)
            self.btn_play.setText("● Running…" if running else "▶  Play Game")
            self.btn_play.setEnabled(not running)
            self.btn_play.setVisible(True)

            self.btn_favorite.setText("★ Favorited" if g.get("favorite") else "☆ Favorite")
            self.btn_favorite.setVisible(True)

            self.btn_uninstall.setVisible(actions.can_uninstall(g))
        else:
            src = self.ctx.sources.get(source_id)
            if src and src.can_download:
                self.btn_install.setVisible(True)
            else:
                self.btn_store.setVisible(True)

    def _update_images(self):
        dpr = self.devicePixelRatioF()
        w, h = 140, 210
        pm = None
        if hasattr(self, "_curr_cover") and self._curr_cover:
            pm = self.ctx.images.get(self._curr_cover, QSize(int(w * dpr), int(h * dpr)), crop=True)

        if pm and not pm.isNull():
            self.cover_lbl.setPixmap(pm)
        else:
            title = self.title_lbl.text() or "Game"
            ph_pm = QPixmap(int(w * dpr), int(h * dpr))
            ph_pm.setDevicePixelRatio(dpr)
            ph_pm.fill(Qt.transparent)
            p = QPainter(ph_pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            paint_placeholder(p, QRect(0, 0, w, h), title, font_px=22)
            p.end()
            self.cover_lbl.setPixmap(ph_pm)

        # Load screenshots in gallery
        for i, s_url in enumerate(self._screenshot_urls):
            if i < len(self._screenshot_labels):
                lbl = self._screenshot_labels[i]
                pm = self.ctx.images.get(s_url, QSize(int(220 * dpr), int(130 * dpr)))
                if pm and not pm.isNull():
                    lbl.setPixmap(pm)

    def _start_download(self):
        item = self.catalog_item
        if not item and self.game_id:
            g = self.ctx.library.game(self.game_id)
            item = CatalogItem(
                source=g["source"], id=g["source_id"], title=g["title"],
                cover_url=g.get("cover_url", ""), size_bytes=g.get("size_bytes", 0),
            )
        if not item:
            return

        # Open Steam-style install dialog allowing source & location selection
        dlg = InstallDialog(self.ctx, item, self)
        if dlg.exec() == QDialog.Accepted:
            src_id, dl_item, dest_dir = dlg.get_result()
            try:
                self.ctx.downloads.enqueue(src_id, dl_item, install_dir=dest_dir)
                self.ctx.toast(f"Starting installation of {dl_item.title}…")
                QTimer.singleShot(50, self._refresh_actions)
            except Exception as exc:
                QMessageBox.warning(self, "Download error", str(exc))

    def _uninstall(self):
        if self.game_id:
            if actions.uninstall_game(self.ctx, self.game_id, self):
                self.load_library_game(self.game_id)

    def _open_store_page(self):
        url = ""
        if self.catalog_item and self.catalog_item.store_url:
            url = self.catalog_item.store_url
        elif self.game_id:
            g = self.ctx.library.game(self.game_id)
            url = g.get("launch_uri", "")
        if url:
            webbrowser.open(url)

    def _open_steamdb(self):
        title = ""
        appid = ""
        if self.game_id:
            g = self.ctx.library.game(self.game_id)
            if g:
                title = g.get("title", "")
                if g.get("source") == "steam" and g.get("source_id"):
                    appid = str(g.get("source_id")).strip()
                elif "steam://rungameid/" in g.get("launch_uri", ""):
                    m = re.search(r"steam://rungameid/(\d+)", g["launch_uri"])
                    if m:
                        appid = m.group(1)
        elif self.catalog_item:
            title = self.catalog_item.title
            if self.catalog_item.source == "steam" and self.catalog_item.id:
                appid = str(self.catalog_item.id).strip()
            elif self.catalog_item.extra and self.catalog_item.extra.get("steam_appid"):
                appid = str(self.catalog_item.extra.get("steam_appid")).strip()

        if appid and appid.isdigit():
            url = f"https://steamdb.info/app/{appid}/"
        elif title:
            # Clean title (e.g. remove [size], tags, edition, free download, v1.0) for clean search
            clean = re.sub(r"\[.*?\]", "", title)
            clean = re.sub(r"\s*\(.*?\)", "", clean)
            clean = re.sub(r"\s*Free Download.*$", "", clean, flags=re.I)
            clean = re.sub(r"\s*[-:]\s*(Complete|Deluxe|Ultimate|Standard|GOTY|Game of the Year)\s+Edition.*$", "", clean, flags=re.I).strip()
            query = urllib.parse.quote_plus(clean or title)
            url = f"https://steamdb.info/search/?a=app&q={query}"
        else:
            url = "https://steamdb.info/"

        webbrowser.open(url)
        self.ctx.toast(f"Opening SteamDB for {title or 'game'}…")

    def _open_install_folder(self):
        if self.game_id:
            g = self.ctx.library.game(self.game_id)
            if g and g.get("install_dir"):
                actions.open_folder(g["install_dir"], self)

    def _change_exe(self):
        if self.game_id:
            if actions.pick_executable(self.ctx, self.game_id, self):
                self.load_library_game(self.game_id)

    def _view_screenshot(self, url: str):
        dlg = ScreenshotViewer(self.ctx, url, self)
        dlg.exec()

    def _on_game_updated(self, gid: int):
        if self.game_id == gid:
            self.load_library_game(gid)
