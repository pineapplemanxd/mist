"""Big Picture Mode with custom GUI (Steam Big Picture & PS5 Console styles).

Supports gamepad navigation (Steam Input style) and keyboard navigation.
Offers two distinct styles selectable in settings:
1. 'classic': Valve Steam Big Picture (dark navy gradient, Steam carousel, Steam button glyphs).
2. 'console': PlayStation 5 style (sleek obsidian UI, dynamic hero background, PS5 pill typography & button glyphs).
"""
from __future__ import annotations

import datetime
import html
import os
import re
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QKeySequence,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QShortcut)
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout,
                               QWidget)

from Core.controller import ControllerManager
from Core.logger import get_logger
from Core.sources import CatalogItem
from . import actions
from .common import Toast, app_icon, draw_pixmap_cover, fmt_playtime, fmt_size, theme_color
from .detail_view import InstallDialog

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# STYLESHEETS
# ---------------------------------------------------------------------------

STEAM_CLASSIC_CSS = """
QWidget#BigPictureRoot {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0b1118, stop:0.4 #101a26, stop:1 #0c1219);
    color: #e5edf5;
    font-family: "Segoe UI", "Motiva Sans", sans-serif;
}
QLabel#BpHeaderTitle {
    color: #66c0f4;
    font-size: 16pt;
    font-weight: 900;
    letter-spacing: 2px;
}
QPushButton#BpTabBtn {
    background: transparent;
    color: #8f98a0;
    border: none;
    border-bottom: 3px solid transparent;
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 1.5px;
    padding: 10px 22px;
}
QPushButton#BpTabBtn:checked, QPushButton#BpTabBtn[focused="true"] {
    color: #ffffff;
    border-bottom: 3px solid #66c0f4;
    background: rgba(102, 192, 244, 0.12);
}
QLabel#BpHudTime {
    color: #c7d5e0;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#BpBadge {
    background: rgba(42, 71, 94, 0.7);
    color: #8ed6ff;
    border: 1px solid #2a475e;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 10pt;
    font-weight: 700;
}
QLabel#BpGameTitle {
    color: #ffffff;
    font-size: 26pt;
    font-weight: 900;
    letter-spacing: 0.5px;
}
QLabel#BpGameSub {
    color: #8f98a0;
    font-size: 11pt;
}
QPushButton#BpActionPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5c7e10, stop:1 #759c14);
    color: #ffffff;
    border: 2px solid #8ac81c;
    border-radius: 4px;
    font-size: 13pt;
    font-weight: 800;
    padding: 12px 28px;
    letter-spacing: 1px;
}
QPushButton#BpActionPrimary:focus, QPushButton#BpActionPrimary[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #759c14, stop:1 #92c418);
    border: 3px solid #ffffff;
}
QPushButton#BpActionSecondary {
    background: rgba(30, 47, 66, 0.8);
    color: #c7d5e0;
    border: 1px solid #2a475e;
    border-radius: 4px;
    font-size: 11pt;
    font-weight: 700;
    padding: 10px 20px;
}
QPushButton#BpActionSecondary:focus, QPushButton#BpActionSecondary[active="true"] {
    background: #2a475e;
    color: #ffffff;
    border: 2px solid #66c0f4;
}
QFrame#BpBottomHud {
    background: rgba(14, 20, 27, 0.95);
    border-top: 1px solid #1b2838;
}
QLabel#BpHudLegend {
    color: #8f98a0;
    font-size: 11pt;
    font-weight: 600;
}
QLabel#BpShelfTitle {
    color: #66c0f4;
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 1.5px;
    padding: 2px 0px;
}
QLabel#BpStoreHeroTag {
    color: #8ed6ff;
    font-size: 10pt;
    font-weight: 800;
    letter-spacing: 1.5px;
}
"""

PS5_CONSOLE_CSS = """
QWidget#BigPictureRoot {
    background: #08090d;
    color: #f3f4f6;
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
}
QLabel#BpHeaderTitle {
    color: #ffffff;
    font-size: 14pt;
    font-weight: 700;
    letter-spacing: 3px;
}
QPushButton#BpTabBtn {
    background: transparent;
    color: #6b7280;
    border: none;
    border-radius: 18px;
    font-size: 13pt;
    font-weight: 700;
    padding: 8px 20px;
}
QPushButton#BpTabBtn:checked, QPushButton#BpTabBtn[focused="true"] {
    color: #ffffff;
    background: rgba(255, 255, 255, 0.15);
}
QLabel#BpHudTime {
    color: #9ca3af;
    font-size: 13pt;
    font-weight: 500;
}
QLabel#BpBadge {
    background: rgba(255, 255, 255, 0.1);
    color: #ffffff;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#BpGameTitle {
    color: #ffffff;
    font-size: 32pt;
    font-weight: 900;
    letter-spacing: -0.5px;
}
QLabel#BpGameSub {
    color: #9ca3af;
    font-size: 11pt;
}
QPushButton#BpActionPrimary {
    background: #ffffff;
    color: #000000;
    border: 2px solid #ffffff;
    border-radius: 22px;
    font-size: 13pt;
    font-weight: 800;
    padding: 12px 34px;
}
QPushButton#BpActionPrimary:focus, QPushButton#BpActionPrimary[active="true"] {
    background: #38bdf8;
    color: #000000;
    border: 3px solid #ffffff;
}
QPushButton#BpActionSecondary {
    background: rgba(255, 255, 255, 0.1);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 20px;
    font-size: 11pt;
    font-weight: 600;
    padding: 10px 22px;
}
QPushButton#BpActionSecondary:focus, QPushButton#BpActionSecondary[active="true"] {
    background: rgba(255, 255, 255, 0.25);
    border: 2px solid #ffffff;
}
QFrame#BpBottomHud {
    background: rgba(8, 9, 13, 0.9);
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}
QLabel#BpHudLegend {
    color: #9ca3af;
    font-size: 11pt;
    font-weight: 600;
}
QLabel#BpShelfTitle {
    color: #ffffff;
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 2px;
    padding: 2px 0px;
}
QLabel#BpStoreHeroTag {
    color: #38bdf8;
    font-size: 10pt;
    font-weight: 800;
    letter-spacing: 2px;
}
"""


# ---------------------------------------------------------------------------
# GAME CAROUSEL CARD
# ---------------------------------------------------------------------------

class BpGameCard(QFrame):
    """Horizontal shelf game tile with dynamic focus glow."""

    def __init__(self, item_data: dict[str, Any], is_console_style: bool = False, parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.is_console_style = is_console_style
        self.focused = False

        self.w = 170 if is_console_style else 160
        self.h = 240 if is_console_style else 230
        self.setFixedSize(self.w, self.h)
        self.setCursor(Qt.PointingHandCursor)

    def set_focused(self, focused: bool):
        if self.focused != focused:
            self.focused = focused
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect().adjusted(4, 4, -4, -4)
        radius = 12 if self.is_console_style else 6

        # Draw card cover pixmap or placeholder
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(path)

        pm = self.item_data.get("_pixmap")
        if pm and not pm.isNull():
            p.drawPixmap(rect, pm)
        else:
            p.fillRect(rect, QColor("#1e293b" if self.is_console_style else "#1b2838"))
            p.setPen(QColor("#ffffff"))
            f = p.font()
            f.setPixelSize(12)
            f.setBold(True)
            p.setFont(f)
            p.drawText(rect.adjusted(8, 8, -8, -8), Qt.AlignCenter | Qt.TextWordWrap, self.item_data.get("title", ""))

        # Badges on card
        src = self.item_data.get("source")
        if src:
            src_str = src.upper()
            f = QFont(p.font())
            f.setPixelSize(9)
            f.setBold(True)
            p.setFont(f)
            sw = p.fontMetrics().horizontalAdvance(src_str) + 10
            badge_r = QRect(rect.x() + 6, rect.y() + 6, sw, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 175))
            p.drawRoundedRect(badge_r, 4, 4)
            p.setPen(QColor("#ffffff" if self.is_console_style else "#8ed6ff"))
            p.drawText(badge_r, Qt.AlignCenter, src_str)

        # Free / Get badge for store cards
        if not self.item_data.get("installed", False):
            f = QFont(p.font())
            f.setPixelSize(9)
            f.setBold(True)
            p.setFont(f)
            free_r = QRect(rect.right() - 42, rect.y() + 6, 36, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(16, 185, 129, 210) if self.is_console_style else QColor(92, 126, 16, 210))
            p.drawRoundedRect(free_r, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(free_r, Qt.AlignCenter, "FREE")

        p.restore()

        # Focus highlight border
        if self.focused:
            p.save()
            if self.is_console_style:
                pen = QPen(QColor("#ffffff"), 3.5)
            else:
                pen = QPen(QColor("#66c0f4"), 3.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, radius, radius)
            p.restore()
        else:
            p.save()
            p.setPen(QPen(QColor(255, 255, 255, 30 if self.is_console_style else 50), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, radius, radius)
            p.restore()


# ---------------------------------------------------------------------------
# MAIN BIG PICTURE WINDOW
# ---------------------------------------------------------------------------

class BigPictureWindow(QWidget):
    """Fullscreen Gamepad-friendly Steam Big Picture & PS5 console GUI."""

    closed = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("BigPictureRoot")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("Mist — Big Picture Mode")
        self.setWindowIcon(app_icon())

        self.style_mode = self.ctx.config.get("big_picture_style", "classic")
        self.is_console = (self.style_mode == "console")

        # Navigation state
        self.active_tab = 0  # 0: Library, 1: Store, 2: Settings
        self.focus_zone = "carousel"  # "tabs", "carousel", "actions", "store", "settings"
        self.selected_game_index = 0
        self.selected_action_index = 0
        self.selected_setting_index = 0

        self.library_items: list[dict[str, Any]] = []
        self.store_items: list[dict[str, Any]] = []
        self.cards: list[BpGameCard] = []

        # Store shelves state (PlayStation Store experience)
        self.store_shelves_data: list[dict[str, Any]] = []
        self.store_shelf_index: int = 0
        self.store_card_indices: list[int] = []

        self._hero_pixmap: QPixmap | None = None
        self._hero_url: str = ""

        self._build_ui()
        self._apply_style()
        self._load_data()
        self._connect_controller()
        self._connect_shortcuts()

        if hasattr(self.ctx, "images") and self.ctx.images:
            self.ctx.images.image_ready.connect(self._on_image_ready)

        # Clock timer
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

    def toast(self, text: str):
        Toast(self, text)

    def _on_image_ready(self, key: str):
        dpr = self.devicePixelRatioF()
        # Refresh hero background if loaded
        if self._hero_url:
            sz = QSize(int(1920 * dpr), int(1080 * dpr))
            pm = self.ctx.images.get(self._hero_url, sz)
            if pm and not pm.isNull():
                self._hero_pixmap = pm
                self.update()

        # Refresh library cards covers
        for i, card in enumerate(self.cards):
            if i < len(self.library_items):
                it = self.library_items[i]
                if not it.get("_pixmap") or it["_pixmap"].isNull():
                    cov_url = it.get("cover_url", "")
                    if cov_url:
                        sz = QSize(int(170 * dpr), int(240 * dpr))
                        pm = self.ctx.images.get(cov_url, sz)
                        if pm and not pm.isNull():
                            it["_pixmap"] = pm
                            card.update()

        # Refresh store shelves cards covers
        for shelf in self.store_shelves_data:
            for card in shelf.get("cards", []):
                it = card.item_data
                if not it.get("_pixmap") or it["_pixmap"].isNull():
                    cov_url = it.get("cover_url", "")
                    if cov_url:
                        sz = QSize(int(170 * dpr), int(240 * dpr))
                        pm = self.ctx.images.get(cov_url, sz)
                        if pm and not pm.isNull():
                            it["_pixmap"] = pm
                            card.update()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. TOP HEADER (Branding, Navigation Tabs, HUD Clock & Status)
        self.header = QWidget()
        self.header.setFixedHeight(72)
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(36, 12, 36, 12)
        h_layout.setSpacing(24)

        # Brand / Logo
        self.lbl_brand = QLabel("MIST" if not self.is_console else "PLAYSTATION")
        self.lbl_brand.setObjectName("BpHeaderTitle")
        h_layout.addWidget(self.lbl_brand)
        h_layout.addSpacing(20)

        # Tab navigation
        self.btn_tab_lib = QPushButton("LIBRARY" if not self.is_console else "Games")
        self.btn_tab_lib.setObjectName("BpTabBtn")
        self.btn_tab_lib.setCheckable(True)
        self.btn_tab_lib.setChecked(True)
        self.btn_tab_lib.clicked.connect(lambda: self._switch_tab(0))

        self.btn_tab_store = QPushButton("STORE" if not self.is_console else "Store")
        self.btn_tab_store.setObjectName("BpTabBtn")
        self.btn_tab_store.setCheckable(True)
        self.btn_tab_store.clicked.connect(lambda: self._switch_tab(1))

        self.btn_tab_settings = QPushButton("SETTINGS" if not self.is_console else "Settings")
        self.btn_tab_settings.setObjectName("BpTabBtn")
        self.btn_tab_settings.setCheckable(True)
        self.btn_tab_settings.clicked.connect(lambda: self._switch_tab(2))

        self.tab_buttons = [self.btn_tab_lib, self.btn_tab_store, self.btn_tab_settings]
        h_layout.addWidget(self.btn_tab_lib)
        h_layout.addWidget(self.btn_tab_store)
        h_layout.addWidget(self.btn_tab_settings)
        h_layout.addStretch(1)

        # Right HUD (Controller icon, Clock, Exit button)
        self.lbl_controller = QLabel("🎮 CONNECTED" if ControllerManager.get_instance().is_connected() else "🎮 READY")
        self.lbl_controller.setObjectName("BpBadge")
        h_layout.addWidget(self.lbl_controller)

        self.lbl_time = QLabel("12:00 PM")
        self.lbl_time.setObjectName("BpHudTime")
        h_layout.addWidget(self.lbl_time)

        self.btn_exit_bp = QPushButton("✕" if self.is_console else "EXIT")
        self.btn_exit_bp.setObjectName("BpTabBtn")
        self.btn_exit_bp.setToolTip("Exit Big Picture Mode")
        self.btn_exit_bp.clicked.connect(self.close)
        h_layout.addWidget(self.btn_exit_bp)

        root_layout.addWidget(self.header)

        # 2. MAIN CONTENT STACK
        self.main_stack = QStackedWidget()
        root_layout.addWidget(self.main_stack, 1)

        # View 0: Game Shelf View (Used for Library)
        self.games_page = QWidget()
        gp_layout = QVBoxLayout(self.games_page)
        gp_layout.setContentsMargins(40, 20, 40, 20)
        gp_layout.setSpacing(16)

        # Game metadata header (Title, genres, developer, badges)
        self.meta_box = QWidget()
        mb_layout = QVBoxLayout(self.meta_box)
        mb_layout.setContentsMargins(0, 0, 0, 0)
        mb_layout.setSpacing(6)

        self.lbl_game_title = QLabel("No Games Available")
        self.lbl_game_title.setObjectName("BpGameTitle")
        self.lbl_game_sub = QLabel("")
        self.lbl_game_sub.setObjectName("BpGameSub")

        # Badges row (Source, Size, Status)
        self.badges_row = QHBoxLayout()
        self.badges_row.setSpacing(10)
        self.lbl_badge_src = QLabel("MIST")
        self.lbl_badge_src.setObjectName("BpBadge")
        self.lbl_badge_status = QLabel("INSTALLED")
        self.lbl_badge_status.setObjectName("BpBadge")
        self.lbl_badge_size = QLabel("")
        self.lbl_badge_size.setObjectName("BpBadge")
        self.badges_row.addWidget(self.lbl_badge_src)
        self.badges_row.addWidget(self.lbl_badge_status)
        self.badges_row.addWidget(self.lbl_badge_size)
        self.badges_row.addStretch(1)

        mb_layout.addWidget(self.lbl_game_title)
        mb_layout.addWidget(self.lbl_game_sub)
        mb_layout.addLayout(self.badges_row)
        gp_layout.addWidget(self.meta_box)

        # Horizontal Game Cards Carousel ScrollArea
        self.carousel_scroll = QScrollArea()
        self.carousel_scroll.setFixedHeight(270)
        self.carousel_scroll.setWidgetResizable(True)
        self.carousel_scroll.setFrameShape(QFrame.NoFrame)
        self.carousel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.carousel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.carousel_container = QWidget()
        self.carousel_layout = QHBoxLayout(self.carousel_container)
        self.carousel_layout.setContentsMargins(10, 10, 10, 10)
        self.carousel_layout.setSpacing(18)
        self.carousel_layout.addStretch(1)
        self.carousel_scroll.setWidget(self.carousel_container)
        gp_layout.addWidget(self.carousel_scroll)

        # Action Buttons row
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(16)

        self.btn_act_primary = QPushButton("▶  PLAY GAME")
        self.btn_act_primary.setObjectName("BpActionPrimary")
        self.btn_act_primary.clicked.connect(self._trigger_primary_action)

        self.btn_act_steamdb = QPushButton("↗  STEAMDB")
        self.btn_act_steamdb.setObjectName("BpActionSecondary")
        self.btn_act_steamdb.clicked.connect(self._open_steamdb_action)

        self.btn_act_details = QPushButton("ℹ  DETAILS")
        self.btn_act_details.setObjectName("BpActionSecondary")
        self.btn_act_details.clicked.connect(self._open_details_action)

        self.action_buttons = [self.btn_act_primary, self.btn_act_steamdb, self.btn_act_details]
        self.actions_row.addWidget(self.btn_act_primary)
        self.actions_row.addWidget(self.btn_act_steamdb)
        self.actions_row.addWidget(self.btn_act_details)
        self.actions_row.addStretch(1)
        gp_layout.addLayout(self.actions_row)
        gp_layout.addStretch(1)

        self.main_stack.addWidget(self.games_page)  # Index 0 (Library)

        # View 1: PS Store Page (PlayStation Store catalog layout)
        self.store_page = QWidget()
        store_l = QVBoxLayout(self.store_page)
        store_l.setContentsMargins(40, 16, 40, 16)
        store_l.setSpacing(12)

        # Store Hero Showcase Header
        self.store_hero_box = QWidget()
        sh_layout = QVBoxLayout(self.store_hero_box)
        sh_layout.setContentsMargins(0, 0, 0, 0)
        sh_layout.setSpacing(6)

        self.lbl_store_tag = QLabel("PLAYSTATION STORE" if self.is_console else "MIST STORE")
        self.lbl_store_tag.setObjectName("BpStoreHeroTag")
        sh_layout.addWidget(self.lbl_store_tag)

        self.lbl_store_title = QLabel("PlayStation Store")
        self.lbl_store_title.setObjectName("BpGameTitle")
        sh_layout.addWidget(self.lbl_store_title)

        self.lbl_store_sub = QLabel("Explore featured collections, new releases, and games.")
        self.lbl_store_sub.setObjectName("BpGameSub")
        sh_layout.addWidget(self.lbl_store_sub)

        # Badges row for store
        self.store_badges_row = QHBoxLayout()
        self.store_badges_row.setSpacing(10)
        self.lbl_store_src = QLabel("ALL SOURCES")
        self.lbl_store_src.setObjectName("BpBadge")
        self.lbl_store_status = QLabel("FREE TO DOWNLOAD")
        self.lbl_store_status.setObjectName("BpBadge")
        self.lbl_store_size = QLabel("")
        self.lbl_store_size.setObjectName("BpBadge")
        self.store_badges_row.addWidget(self.lbl_store_src)
        self.store_badges_row.addWidget(self.lbl_store_status)
        self.store_badges_row.addWidget(self.lbl_store_size)
        self.store_badges_row.addStretch(1)
        sh_layout.addLayout(self.store_badges_row)

        # Store action prompt buttons
        self.store_actions_row = QHBoxLayout()
        self.store_actions_row.setSpacing(14)
        self.btn_store_primary = QPushButton("✕  Get / Install" if self.is_console else "▶  INSTALL")
        self.btn_store_primary.setObjectName("BpActionPrimary")
        self.btn_store_primary.clicked.connect(self._trigger_store_install)

        self.btn_store_steamdb = QPushButton("□  SteamDB" if self.is_console else "↗  STEAMDB")
        self.btn_store_steamdb.setObjectName("BpActionSecondary")
        self.btn_store_steamdb.clicked.connect(self._open_steamdb_action)

        self.btn_store_details = QPushButton("△  Details" if self.is_console else "ℹ  DETAILS")
        self.btn_store_details.setObjectName("BpActionSecondary")
        self.btn_store_details.clicked.connect(self._open_details_action)

        self.store_actions_row.addWidget(self.btn_store_primary)
        self.store_actions_row.addWidget(self.btn_store_steamdb)
        self.store_actions_row.addWidget(self.btn_store_details)
        self.store_actions_row.addStretch(1)
        sh_layout.addLayout(self.store_actions_row)

        store_l.addWidget(self.store_hero_box)

        # Vertical ScrollArea for Shelves
        self.store_scroll = QScrollArea()
        self.store_scroll.setWidgetResizable(True)
        self.store_scroll.setFrameShape(QFrame.NoFrame)
        self.store_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.store_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.store_container = QWidget()
        self.store_shelves_layout = QVBoxLayout(self.store_container)
        self.store_shelves_layout.setContentsMargins(0, 4, 0, 24)
        self.store_shelves_layout.setSpacing(18)
        self.store_shelves_layout.addStretch(1)
        self.store_scroll.setWidget(self.store_container)
        store_l.addWidget(self.store_scroll, 1)

        self.main_stack.addWidget(self.store_page)  # Index 1 (PS Store)

        # View 2: Settings Page
        self.settings_page = QWidget()
        sp_layout = QVBoxLayout(self.settings_page)
        sp_layout.setContentsMargins(60, 40, 60, 40)
        sp_layout.setSpacing(24)

        lbl_set_title = QLabel("BIG PICTURE SETTINGS")
        lbl_set_title.setObjectName("BpGameTitle")
        sp_layout.addWidget(lbl_set_title)

        # Style switcher buttons
        lbl_style_desc = QLabel("Select Big Picture Mode Interface Style:")
        lbl_style_desc.setObjectName("BpGameSub")
        sp_layout.addWidget(lbl_style_desc)

        style_row = QHBoxLayout()
        style_row.setSpacing(16)
        self.btn_set_classic = QPushButton("Steam Big Picture (Classic)")
        self.btn_set_classic.setObjectName("BpActionPrimary" if not self.is_console else "BpActionSecondary")
        self.btn_set_classic.clicked.connect(lambda: self._set_style("classic"))

        self.btn_set_console = QPushButton("PlayStation 5 Console Style")
        self.btn_set_console.setObjectName("BpActionPrimary" if self.is_console else "BpActionSecondary")
        self.btn_set_console.clicked.connect(lambda: self._set_style("console"))

        style_row.addWidget(self.btn_set_classic)
        style_row.addWidget(self.btn_set_console)
        style_row.addStretch(1)
        sp_layout.addLayout(style_row)

        self.setting_buttons = [self.btn_set_classic, self.btn_set_console]

        # Controller info
        self.lbl_set_ctrl = QLabel(f"Controller: {ControllerManager.get_instance().get_status_text()}")
        self.lbl_set_ctrl.setObjectName("BpBadge")
        sp_layout.addWidget(self.lbl_set_ctrl)

        sp_layout.addStretch(1)
        self.main_stack.addWidget(self.settings_page)  # Index 1 (Settings)

        # 3. BOTTOM HUD (Controller legend prompts)
        self.bottom_hud = QFrame()
        self.bottom_hud.setObjectName("BpBottomHud")
        self.bottom_hud.setFixedHeight(54)
        hud_l = QHBoxLayout(self.bottom_hud)
        hud_l.setContentsMargins(36, 8, 36, 8)

        self.lbl_legend = QLabel()
        self.lbl_legend.setObjectName("BpHudLegend")
        hud_l.addWidget(self.lbl_legend)
        hud_l.addStretch(1)
        root_layout.addWidget(self.bottom_hud)

        self._update_legend()

    def _apply_style(self):
        self.is_console = (self.style_mode == "console")
        self.setStyleSheet(PS5_CONSOLE_CSS if self.is_console else STEAM_CLASSIC_CSS)

        self.lbl_brand.setText("PLAYSTATION" if self.is_console else "MIST")
        self.btn_tab_lib.setText("Games" if self.is_console else "LIBRARY")
        self.btn_tab_store.setText("Store" if self.is_console else "STORE")
        self.btn_tab_settings.setText("Settings" if self.is_console else "SETTINGS")
        self.btn_exit_bp.setText("✕" if self.is_console else "EXIT")

        self.btn_set_classic.setObjectName("BpActionSecondary" if self.is_console else "BpActionPrimary")
        self.btn_set_console.setObjectName("BpActionPrimary" if self.is_console else "BpActionSecondary")
        self.btn_set_classic.setStyle(self.btn_set_classic.style())
        self.btn_set_console.setStyle(self.btn_set_console.style())

        if self.is_console:
            self.btn_act_primary.setText("✕  Play Game")
            self.btn_act_steamdb.setText("□  SteamDB")
            self.btn_act_details.setText("△  Game Details")
            if hasattr(self, "lbl_store_tag"):
                self.lbl_store_tag.setText("PLAYSTATION STORE")
            if hasattr(self, "btn_store_primary"):
                self.btn_store_primary.setText("✕  Get / Install")
            if hasattr(self, "btn_store_steamdb"):
                self.btn_store_steamdb.setText("□  SteamDB")
            if hasattr(self, "btn_store_details"):
                self.btn_store_details.setText("△  Game Details")
        else:
            self.btn_act_primary.setText("▶  PLAY GAME")
            self.btn_act_steamdb.setText("↗  STEAMDB")
            self.btn_act_details.setText("ℹ  DETAILS")
            if hasattr(self, "lbl_store_tag"):
                self.lbl_store_tag.setText("MIST STORE")
            if hasattr(self, "btn_store_primary"):
                self.btn_store_primary.setText("▶  INSTALL")
            if hasattr(self, "btn_store_steamdb"):
                self.btn_store_steamdb.setText("↗  STEAMDB")
            if hasattr(self, "btn_store_details"):
                self.btn_store_details.setText("ℹ  DETAILS")

        self._update_legend()
        self.update()

    def _update_legend(self):
        if self.is_console:
            self.lbl_legend.setText("✕ Select    ○ Back    □ SteamDB    △ Details    L1 / R1 Categories    [PS] Exit")
        else:
            self.lbl_legend.setText("(A) SELECT    (B) BACK    (X) STEAMDB    (Y) DETAILS    (LB/RB) TABS    (Guide) EXIT")

    def _update_clock(self):
        now = datetime.datetime.now()
        self.lbl_time.setText(now.strftime("%I:%M %p"))

    def _set_style(self, style_name: str):
        self.style_mode = style_name
        self.ctx.config.set("big_picture_style", style_name)
        self._apply_style()
        self._refresh_carousel()
        if self.store_items:
            self._populate_store_shelves(self.store_items)

    def _switch_tab(self, tab_idx: int):
        self.active_tab = tab_idx
        for i, btn in enumerate(self.tab_buttons):
            btn.setChecked(i == tab_idx)

        if tab_idx == 0:
            self.main_stack.setCurrentIndex(0)
            self._refresh_carousel()
            self.focus_zone = "carousel"
            self._update_focus()
        elif tab_idx == 1:
            self.main_stack.setCurrentIndex(1)
            self.focus_zone = "store"
            self._update_store_focus()
        else:
            self.main_stack.setCurrentIndex(2)
            self.focus_zone = "settings"
            self.selected_setting_index = 0
            self._update_focus()

    def _load_data(self):
        # 1. Load library games
        lib_games = self.ctx.library.games()
        self.library_items = [dict(g) for g in lib_games]

        # 2. Load store items (from active sources AnkerGames, SteamRip)
        def fetch_store():
            items = []
            for s in self.ctx.sources.all():
                try:
                    res = s.search(page=1, page_size=20)
                    for it in res.items:
                        items.append({
                            "id": it.id,
                            "title": it.title,
                            "source": it.source,
                            "source_id": it.id,
                            "cover_url": it.cover_url,
                            "hero_url": it.hero_url,
                            "size_bytes": it.size_bytes,
                            "genres": it.genres,
                            "installed": False,
                            "_catalog_item": it,
                        })
                except Exception as exc:
                    log.warning("Big Picture store fetch error: %s", exc)
            return items

        from UI.common import run_async
        def on_store_loaded(items):
            self.store_items = items
            self._populate_store_shelves(items)
            if self.active_tab == 1:
                self._update_store_focus()

        run_async(fetch_store, on_store_loaded, context=self)
        self._refresh_carousel()

    def _current_item_list(self) -> list[dict[str, Any]]:
        return self.library_items if self.active_tab == 0 else self.store_items

    def _refresh_carousel(self):
        # Clear existing cards
        while self.carousel_layout.count() > 1:
            item = self.carousel_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()

        items = self._current_item_list()
        if not items:
            self.lbl_game_title.setText("No Games Found" if self.active_tab == 0 else "Loading Store Games…")
            self.lbl_game_sub.setText("Your library is currently empty." if self.active_tab == 0 else "Fetching catalog...")
            self.btn_act_primary.setVisible(False)
            self.btn_act_steamdb.setVisible(False)
            self.btn_act_details.setVisible(False)
            return

        self.btn_act_primary.setVisible(True)
        self.btn_act_steamdb.setVisible(True)
        self.btn_act_details.setVisible(True)

        dpr = self.devicePixelRatioF()
        for i, it in enumerate(items):
            # Load cover pixmap
            cov_url = it.get("cover_url", "")
            if cov_url:
                sz = QSize(int(170 * dpr), int(240 * dpr))
                pm = self.ctx.images.get(cov_url, sz)
                it["_pixmap"] = pm

            card = BpGameCard(it, is_console_style=self.is_console, parent=self)
            card.mousePressEvent = lambda ev, idx=i: self._on_card_clicked(idx)
            self.carousel_layout.insertWidget(i, card)
            self.cards.append(card)

        self.selected_game_index = min(self.selected_game_index, max(0, len(items) - 1))
        self._update_focus()

    def _on_card_clicked(self, idx: int):
        self.selected_game_index = idx
        self.focus_zone = "carousel"
        self._update_focus()

    def _update_focus(self):
        # Update tab button styles
        for i, btn in enumerate(self.tab_buttons):
            btn.setProperty("focused", self.focus_zone == "tabs" and self.active_tab == i)
            btn.setStyle(btn.style())

        # Update carousel cards focus
        for i, card in enumerate(self.cards):
            card.set_focused(self.focus_zone == "carousel" and i == self.selected_game_index)

        # Update action buttons focus
        for i, btn in enumerate(self.action_buttons):
            btn.setProperty("active", self.focus_zone == "actions" and i == self.selected_action_index)
            btn.setStyle(btn.style())

        # Update settings buttons focus
        for i, btn in enumerate(self.setting_buttons):
            btn.setProperty("active", self.focus_zone == "settings" and i == self.selected_setting_index)
            btn.setStyle(btn.style())

        # Scroll carousel to ensure focused card is visible
        if self.focus_zone == "carousel" and 0 <= self.selected_game_index < len(self.cards):
            target_card = self.cards[self.selected_game_index]
            self.carousel_scroll.ensureWidgetVisible(target_card, 150, 0)

        # Update game metadata panel
        self._update_metadata_panel()

    def _update_metadata_panel(self):
        items = self.library_items
        if not items or self.selected_game_index >= len(items):
            self.lbl_game_title.setText("No Games Found" if self.active_tab == 0 else "Loading Games…")
            self.lbl_game_sub.setText("Your library is currently empty." if self.active_tab == 0 else "Fetching catalog...")
            self.lbl_badge_src.setText("")
            self.lbl_badge_status.setText("")
            self.lbl_badge_size.setText("")
            self.btn_act_primary.setVisible(False)
            self.btn_act_steamdb.setVisible(False)
            self.btn_act_details.setVisible(False)
            return

        self.btn_act_primary.setVisible(True)
        self.btn_act_steamdb.setVisible(True)
        self.btn_act_details.setVisible(True)

        it = items[self.selected_game_index]
        title = it.get("title", "")
        self.lbl_game_title.setText(title)

        genres = it.get("genres", [])
        genre_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
        dev = it.get("developer") or it.get("publisher") or ""
        sub = f"{dev} • {genre_str}" if dev and genre_str else (dev or genre_str)
        self.lbl_game_sub.setText(sub)

        src = it.get("source", "mist").upper()
        self.lbl_badge_src.setText(src)

        installed = bool(it.get("installed", False))
        if installed:
            self.lbl_badge_status.setText("INSTALLED")
            self.lbl_badge_status.setStyleSheet("color: #22c55e;")
            if self.is_console:
                self.btn_act_primary.setText("✕  Play Game")
            else:
                self.btn_act_primary.setText("▶  PLAY GAME")
        else:
            self.lbl_badge_status.setText("AVAILABLE")
            self.lbl_badge_status.setStyleSheet("color: #66c0f4;" if not self.is_console else "color: #38bdf8;")
            if self.is_console:
                self.btn_act_primary.setText("✕  Download Game")
            else:
                self.btn_act_primary.setText("⤓  INSTALL GAME")

        if self.is_console:
            self.btn_act_steamdb.setText("□  SteamDB")
            self.btn_act_details.setText("△  Game Details")
        else:
            self.btn_act_steamdb.setText("↗  STEAMDB")
            self.btn_act_details.setText("ℹ  DETAILS")

        sz = it.get("size_bytes", 0)
        self.lbl_badge_size.setText(fmt_size(sz) if sz else "")
        self.lbl_badge_size.setVisible(bool(sz))

        # Update background hero wallpaper
        hero_url = it.get("hero_url") or it.get("cover_url", "")
        if hero_url and hero_url != self._hero_url:
            self._hero_url = hero_url
            dpr = self.devicePixelRatioF()
            pm = self.ctx.images.get(hero_url, QSize(int(1920 * dpr), int(1080 * dpr)))
            if pm and not pm.isNull():
                self._hero_pixmap = pm
                self.update()

    # -----------------------------------------------------------------------
    # PS STORE SHELVES & INTERACTION
    # -----------------------------------------------------------------------

    def _populate_store_shelves(self, items: list[dict[str, Any]]):
        while self.store_shelves_layout.count() > 1:
            item = self.store_shelves_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.store_shelves_data.clear()
        self.store_card_indices.clear()

        if not items:
            lbl_empty = QLabel("Loading PlayStation Store Catalog…")
            lbl_empty.setObjectName("BpGameSub")
            self.store_shelves_layout.insertWidget(0, lbl_empty)
            return

        featured_items = items[:8]
        latest_items = items[8:16] if len(items) > 8 else items[:6]
        anker_items = [it for it in items if it.get("source") == "ankergames"]

        shelf_defs = [
            ("FEATURED & TRENDING", featured_items),
            ("NEW RELEASES", latest_items if latest_items else featured_items),
        ]
        if anker_items:
            shelf_defs.append(("ANKER GAMES ARCHIVE", anker_items))

        valid_shelf_defs = [(title, s_items) for title, s_items in shelf_defs if s_items]

        dpr = self.devicePixelRatioF()
        for shelf_idx, (shelf_title, shelf_items) in enumerate(valid_shelf_defs):
            shelf_widget = QWidget()
            sw_layout = QVBoxLayout(shelf_widget)
            sw_layout.setContentsMargins(0, 0, 0, 0)
            sw_layout.setSpacing(10)

            lbl_title = QLabel(shelf_title)
            lbl_title.setObjectName("BpShelfTitle")
            sw_layout.addWidget(lbl_title)

            h_scroll = QScrollArea()
            h_scroll.setFixedHeight(260)
            h_scroll.setWidgetResizable(True)
            h_scroll.setFrameShape(QFrame.NoFrame)
            h_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            h_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            cards_container = QWidget()
            cards_layout = QHBoxLayout(cards_container)
            cards_layout.setContentsMargins(6, 6, 6, 6)
            cards_layout.setSpacing(16)

            shelf_cards: list[BpGameCard] = []
            for card_idx, it in enumerate(shelf_items):
                cov_url = it.get("cover_url", "")
                if cov_url and not it.get("_pixmap"):
                    sz = QSize(int(170 * dpr), int(240 * dpr))
                    pm = self.ctx.images.get(cov_url, sz)
                    if pm and not pm.isNull():
                        it["_pixmap"] = pm
                card = BpGameCard(it, is_console_style=self.is_console, parent=self)
                card.mousePressEvent = lambda ev, s=shelf_idx, c=card_idx: self._on_store_card_clicked(s, c)
                cards_layout.addWidget(card)
                shelf_cards.append(card)

            cards_layout.addStretch(1)
            h_scroll.setWidget(cards_container)
            sw_layout.addWidget(h_scroll)

            self.store_shelves_layout.insertWidget(shelf_idx, shelf_widget)
            self.store_shelves_data.append({
                "title": shelf_title,
                "widget": shelf_widget,
                "scroll": h_scroll,
                "cards": shelf_cards,
                "items": shelf_items,
            })
            self.store_card_indices.append(0)

        self.store_shelf_index = 0
        if self.active_tab == 1:
            self._update_store_focus()

    def _get_current_store_item(self) -> dict[str, Any] | None:
        if not self.store_shelves_data or self.store_shelf_index >= len(self.store_shelves_data):
            return self.store_items[0] if self.store_items else None
        shelf = self.store_shelves_data[self.store_shelf_index]
        cards = shelf["cards"]
        if not cards:
            return None
        c_idx = self.store_card_indices[self.store_shelf_index]
        if c_idx >= len(cards):
            c_idx = 0
        return cards[c_idx].item_data

    def _update_store_hero(self, it: dict[str, Any]):
        title = it.get("title", "")
        self.lbl_store_title.setText(title)
        genres = it.get("genres", [])
        genre_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
        dev = it.get("developer") or it.get("publisher") or ""
        sub = f"{dev} • {genre_str}" if dev and genre_str else (dev or genre_str)
        self.lbl_store_sub.setText(sub)

        src = it.get("source", "mist").upper()
        self.lbl_store_src.setText(src)
        self.lbl_store_status.setText("FREE TO DOWNLOAD")

        sz = it.get("size_bytes", 0)
        self.lbl_store_size.setText(fmt_size(sz) if sz else "")
        self.lbl_store_size.setVisible(bool(sz))

        hero_url = it.get("hero_url") or it.get("cover_url", "")
        if hero_url and hero_url != self._hero_url:
            self._hero_url = hero_url
            dpr = self.devicePixelRatioF()
            pm = self.ctx.images.get(hero_url, QSize(int(1920 * dpr), int(1080 * dpr)))
            if pm and not pm.isNull():
                self._hero_pixmap = pm
                self.update()

    def _update_store_focus(self):
        if not self.store_shelves_data:
            return

        self.store_shelf_index = max(0, min(self.store_shelf_index, len(self.store_shelves_data) - 1))

        for s_idx, shelf in enumerate(self.store_shelves_data):
            c_idx = self.store_card_indices[s_idx]
            for i, card in enumerate(shelf["cards"]):
                card.set_focused(self.focus_zone == "store" and s_idx == self.store_shelf_index and i == c_idx)

        # Tab button styles
        for i, btn in enumerate(self.tab_buttons):
            btn.setProperty("focused", self.focus_zone == "tabs" and self.active_tab == i)
            btn.setStyle(btn.style())

        cur_shelf = self.store_shelves_data[self.store_shelf_index]
        cur_c_idx = self.store_card_indices[self.store_shelf_index]
        if cur_shelf["cards"] and 0 <= cur_c_idx < len(cur_shelf["cards"]):
            target_card = cur_shelf["cards"][cur_c_idx]
            cur_shelf["scroll"].ensureWidgetVisible(target_card, 150, 0)
            self.store_scroll.ensureWidgetVisible(cur_shelf["widget"], 0, 80)
            self._update_store_hero(target_card.item_data)

    def _on_store_card_clicked(self, shelf_idx: int, card_idx: int):
        is_already_focused = (
            self.focus_zone == "store"
            and self.store_shelf_index == shelf_idx
            and self.store_card_indices[shelf_idx] == card_idx
        )
        self.store_shelf_index = shelf_idx
        self.store_card_indices[shelf_idx] = card_idx
        self.focus_zone = "store"
        self._update_store_focus()
        if is_already_focused:
            self._trigger_store_install()

    def _trigger_store_install(self):
        it = self._get_current_store_item()
        if not it:
            return
        cat_item = it.get("_catalog_item")
        if not cat_item:
            cat_item = CatalogItem(
                source=it.get("source", "ankergames"),
                id=str(it.get("source_id") or it.get("id")),
                title=it.get("title", ""),
                cover_url=it.get("cover_url", ""),
                size_bytes=it.get("size_bytes", 0),
            )
        dlg = InstallDialog(self.ctx, cat_item, self)
        if dlg.exec() == QDialog.Accepted:
            src_id, dl_item, dest_dir = dlg.get_result()
            try:
                self.ctx.downloads.enqueue(src_id, dl_item, install_dir=dest_dir)
                self.ctx.toast(f"Starting installation of {dl_item.title}…")
            except Exception as exc:
                self.ctx.toast(f"Download error: {exc}")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        # Draw fullscreen background
        w, h = self.width(), self.height()
        if self._hero_pixmap and not self._hero_pixmap.isNull():
            draw_pixmap_cover(p, self.rect(), self._hero_pixmap)

            # Draw moody gradient vignette overlay
            grad = QLinearGradient(0, 0, 0, h)
            if self.is_console:
                grad.setColorAt(0.0, QColor(8, 9, 13, 210))
                grad.setColorAt(0.5, QColor(8, 9, 13, 230))
                grad.setColorAt(1.0, QColor(8, 9, 13, 255))
            else:
                grad.setColorAt(0.0, QColor(11, 17, 24, 210))
                grad.setColorAt(0.4, QColor(16, 26, 38, 225))
                grad.setColorAt(1.0, QColor(12, 18, 25, 250))
            p.fillRect(self.rect(), grad)
        else:
            p.fillRect(self.rect(), QColor("#08090d" if self.is_console else "#0e141b"))

    # -----------------------------------------------------------------------
    # ACTIONS
    # -----------------------------------------------------------------------

    def _trigger_primary_action(self):
        if self.active_tab == 1:
            self._trigger_store_install()
            return

        items = self.library_items
        if not items or self.selected_game_index >= len(items):
            return

        it = items[self.selected_game_index]
        if it.get("installed") and it.get("id"):
            gid = it["id"]
            actions.launch_game(self.ctx, gid, self)
            self.ctx.toast(f"Launching {it.get('title')}…")
        else:
            cat_item = it.get("_catalog_item")
            if not cat_item:
                cat_item = CatalogItem(
                    source=it.get("source", "ankergames"),
                    id=str(it.get("source_id") or it.get("id")),
                    title=it.get("title", ""),
                    cover_url=it.get("cover_url", ""),
                    size_bytes=it.get("size_bytes", 0),
                )
            dlg = InstallDialog(self.ctx, cat_item, self)
            if dlg.exec() == QDialog.Accepted:
                src_id, dl_item, dest_dir = dlg.get_result()
                try:
                    self.ctx.downloads.enqueue(src_id, dl_item, install_dir=dest_dir)
                    self.ctx.toast(f"Starting installation of {dl_item.title}…")
                except Exception as exc:
                    self.ctx.toast(f"Download error: {exc}")

    def _open_steamdb_action(self):
        if self.active_tab == 1:
            it = self._get_current_store_item()
        else:
            items = self.library_items
            it = items[self.selected_game_index] if items and self.selected_game_index < len(items) else None
        if not it:
            return
        title = it.get("title", "")
        appid = ""
        if it.get("source") == "steam" and it.get("source_id"):
            appid = str(it.get("source_id")).strip()
        elif "steam://rungameid/" in it.get("launch_uri", ""):
            m = re.search(r"steam://rungameid/(\d+)", it["launch_uri"])
            if m:
                appid = m.group(1)

        if appid and appid.isdigit():
            url = f"https://steamdb.info/app/{appid}/"
        elif title:
            clean = re.sub(r"\[.*?\]", "", title)
            clean = re.sub(r"\s*\(.*?\)", "", clean)
            clean = re.sub(r"\s*Free Download.*$", "", clean, flags=re.I)
            clean = re.sub(r"\s*[-:]\s*(Complete|Deluxe|Ultimate|Standard|GOTY|Game of the Year)\s+Edition.*$", "", clean, flags=re.I).strip()
            query = urllib.parse.quote_plus(clean or title)
            url = f"https://steamdb.info/search/?a=app&q={query}"
        else:
            url = "https://steamdb.info/"

        webbrowser.open(url)
        self.ctx.toast(f"Opening SteamDB for {title}…")

    def _open_details_action(self):
        if self.active_tab == 1:
            it = self._get_current_store_item()
        else:
            items = self.library_items
            it = items[self.selected_game_index] if items and self.selected_game_index < len(items) else None
        if not it:
            return
        # Open details in desktop window and close BP mode
        if self.ctx.window:
            if it.get("installed") and it.get("id"):
                self.ctx.window.open_game(it["id"])
            elif it.get("_catalog_item"):
                self.ctx.window.open_catalog_item(it["_catalog_item"])
        self.close()

    # -----------------------------------------------------------------------
    # NAVIGATION & INPUT HANDLING (Gamepad + Keyboard)
    # -----------------------------------------------------------------------

    def _connect_controller(self):
        cm = ControllerManager.get_instance()
        cm.signals.nav_left.connect(self._on_nav_left)
        cm.signals.nav_right.connect(self._on_nav_right)
        cm.signals.nav_up.connect(self._on_nav_up)
        cm.signals.nav_down.connect(self._on_nav_down)
        cm.signals.nav_select.connect(self._on_nav_select)
        cm.signals.nav_back.connect(self._on_nav_back)
        cm.signals.nav_action.connect(self._open_steamdb_action)
        cm.signals.nav_extra.connect(self._open_details_action)
        cm.signals.nav_tab_prev.connect(self._on_prev_tab)
        cm.signals.nav_tab_next.connect(self._on_next_tab)

    def _connect_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Left), self, self._on_nav_left)
        QShortcut(QKeySequence(Qt.Key_Right), self, self._on_nav_right)
        QShortcut(QKeySequence(Qt.Key_Up), self, self._on_nav_up)
        QShortcut(QKeySequence(Qt.Key_Down), self, self._on_nav_down)
        QShortcut(QKeySequence(Qt.Key_Return), self, self._on_nav_select)
        QShortcut(QKeySequence(Qt.Key_Space), self, self._on_nav_select)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, self._on_nav_back)
        QShortcut(QKeySequence(Qt.Key_Tab), self, self._on_next_tab)
        QShortcut(QKeySequence("Shift+Tab"), self, self._on_prev_tab)
        QShortcut(QKeySequence(Qt.Key_X), self, self._open_steamdb_action)
        QShortcut(QKeySequence(Qt.Key_D), self, self._open_details_action)
        QShortcut(QKeySequence(Qt.Key_I), self, self._open_details_action)
        QShortcut(QKeySequence(Qt.Key_F11), self, self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_nav_left(self):
        if self.active_tab == 1 and self.focus_zone == "store":
            if self.store_shelves_data:
                c_idx = self.store_card_indices[self.store_shelf_index]
                if c_idx > 0:
                    self.store_card_indices[self.store_shelf_index] = c_idx - 1
                    self._update_store_focus()
            return

        if self.focus_zone == "carousel":
            if self.selected_game_index > 0:
                self.selected_game_index -= 1
                self._update_focus()
        elif self.focus_zone == "actions":
            if self.selected_action_index > 0:
                self.selected_action_index -= 1
                self._update_focus()
        elif self.focus_zone == "tabs":
            self._on_prev_tab()
        elif self.focus_zone == "settings":
            if self.selected_setting_index > 0:
                self.selected_setting_index -= 1
                self._update_focus()

    def _on_nav_right(self):
        if self.active_tab == 1 and self.focus_zone == "store":
            if self.store_shelves_data:
                shelf = self.store_shelves_data[self.store_shelf_index]
                c_idx = self.store_card_indices[self.store_shelf_index]
                if c_idx < len(shelf["cards"]) - 1:
                    self.store_card_indices[self.store_shelf_index] = c_idx + 1
                    self._update_store_focus()
            return

        if self.focus_zone == "carousel":
            items = self.library_items
            if self.selected_game_index < len(items) - 1:
                self.selected_game_index += 1
                self._update_focus()
        elif self.focus_zone == "actions":
            if self.selected_action_index < len(self.action_buttons) - 1:
                self.selected_action_index += 1
                self._update_focus()
        elif self.focus_zone == "tabs":
            self._on_next_tab()
        elif self.focus_zone == "settings":
            if self.selected_setting_index < len(self.setting_buttons) - 1:
                self.selected_setting_index += 1
                self._update_focus()

    def _on_nav_up(self):
        if self.active_tab == 1:
            if self.focus_zone == "store":
                if self.store_shelf_index > 0:
                    self.store_shelf_index -= 1
                    self._update_store_focus()
                else:
                    self.focus_zone = "tabs"
                    self._update_store_focus()
            return

        if self.focus_zone == "actions":
            self.focus_zone = "carousel"
            self._update_focus()
        elif self.focus_zone == "carousel":
            self.focus_zone = "tabs"
            self._update_focus()
        elif self.focus_zone == "settings":
            self.focus_zone = "tabs"
            self._update_focus()

    def _on_nav_down(self):
        if self.focus_zone == "tabs":
            if self.active_tab == 0:
                if self.cards:
                    self.focus_zone = "carousel"
                self._update_focus()
            elif self.active_tab == 1:
                self.focus_zone = "store"
                self._update_store_focus()
            else:
                self.focus_zone = "settings"
                self._update_focus()
            return

        if self.active_tab == 1 and self.focus_zone == "store":
            if self.store_shelf_index < len(self.store_shelves_data) - 1:
                self.store_shelf_index += 1
                self._update_store_focus()
            return

        if self.focus_zone == "carousel":
            if self.btn_act_primary.isVisible():
                self.focus_zone = "actions"
                self.selected_action_index = 0
            self._update_focus()

    def _on_prev_tab(self):
        idx = (self.active_tab - 1) % len(self.tab_buttons)
        self._switch_tab(idx)

    def _on_next_tab(self):
        idx = (self.active_tab + 1) % len(self.tab_buttons)
        self._switch_tab(idx)

    def _on_nav_select(self):
        if self.active_tab == 1 and self.focus_zone == "store":
            self._trigger_store_install()
            return
        if self.focus_zone == "carousel":
            self._trigger_primary_action()
        elif self.focus_zone == "actions":
            btn = self.action_buttons[self.selected_action_index]
            btn.click()
        elif self.focus_zone == "tabs":
            btn = self.tab_buttons[self.active_tab]
            btn.click()
        elif self.focus_zone == "settings":
            btn = self.setting_buttons[self.selected_setting_index]
            btn.click()

    def _on_nav_back(self):
        if self.active_tab == 1:
            if self.focus_zone == "store":
                if self.store_shelf_index > 0:
                    self.store_shelf_index = 0
                    self._update_store_focus()
                else:
                    self.focus_zone = "tabs"
                    self._update_store_focus()
                return
            else:
                self._switch_tab(0)
                return

        if self.focus_zone in ("actions", "tabs"):
            if self.active_tab == 0:
                self.focus_zone = "carousel"
            else:
                self.focus_zone = "settings"
            self._update_focus()
        else:
            self.close()

    def closeEvent(self, event):
        # Disconnect controller signals to avoid duplicate events on reopen
        cm = ControllerManager.get_instance()
        try:
            cm.signals.nav_left.disconnect(self._on_nav_left)
            cm.signals.nav_right.disconnect(self._on_nav_right)
            cm.signals.nav_up.disconnect(self._on_nav_up)
            cm.signals.nav_down.disconnect(self._on_nav_down)
            cm.signals.nav_select.disconnect(self._on_nav_select)
            cm.signals.nav_back.disconnect(self._on_nav_back)
            cm.signals.nav_action.disconnect(self._open_steamdb_action)
            cm.signals.nav_extra.disconnect(self._open_details_action)
            cm.signals.nav_tab_prev.disconnect(self._on_prev_tab)
            cm.signals.nav_tab_next.disconnect(self._on_next_tab)
        except Exception:
            pass

        if hasattr(self.ctx, "images") and self.ctx.images:
            try:
                self.ctx.images.image_ready.disconnect(self._on_image_ready)
            except Exception:
                pass

        self.closed.emit()
        super().closeEvent(event)
