"""Main application window: responsive top/sidebar navigation, stacked views, toasts, and window lifecycle."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QApplication, QBoxLayout, QButtonGroup, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMenuBar, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from Core import steam_scanner
from Core.controller import ControllerManager
from Core.downloader import ACTIVE
from Core.sources import CatalogItem
from .big_picture import BigPictureWindow
from .common import Toast, app_icon, shutdown_async
from .detail_view import GameDetailView
from .downloads_view import DownloadsView
from .library_view import LibraryView
from .settings_view import SettingsView
from .store_view import StoreView
from . import theme


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.ctx.window = self
        self.setWindowTitle("Mist — Unified Game Library")
        self.resize(1260, 820)
        self.setMinimumSize(960, 600)
        self.setWindowIcon(app_icon())

        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # ----------------------------------------------------------- RETRO 2003 MENU BAR
        self.retro_menu_bar = QMenuBar(self)
        self.retro_menu_bar.setObjectName("RetroMenuBar")
        self._setup_retro_menu()
        self._root_layout.addWidget(self.retro_menu_bar)
        self.retro_menu_bar.setVisible(False)

        # ----------------------------------------------------------- TOP NAV BAR
        self.top_bar = QWidget()
        self.top_bar.setObjectName("TopNavBar")
        self.top_layout = QHBoxLayout(self.top_bar)
        self.top_layout.setContentsMargins(18, 6, 18, 6)
        self.top_layout.setSpacing(10)
        self._root_layout.addWidget(self.top_bar)

        # ----------------------------------------------------------- BODY CONTAINER
        self.body_container = QWidget()
        self.body_layout = QHBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self._root_layout.addWidget(self.body_container, 1)

        # ----------------------------------------------------------- SIDEBAR
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        self._sidebar_collapsed = False
        self.sb_layout = QVBoxLayout(self.sidebar)
        self.sb_layout.setContentsMargins(14, 18, 14, 16)
        self.sb_layout.setSpacing(6)
        self.body_layout.addWidget(self.sidebar)

        # Brand / App logo
        self.brand_widget = QWidget()
        self.brand_layout = QHBoxLayout(self.brand_widget)
        self.brand_layout.setContentsMargins(0, 0, 0, 0)
        self.brand_layout.setSpacing(8)
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(app_icon().pixmap(28, 28))
        self.app_title = QLabel("Mist")
        self.app_title.setObjectName("AppName")
        self.btn_collapse = QPushButton("◀")
        self.btn_collapse.setObjectName("CollapseBtn")
        self.btn_collapse.setToolTip("Collapse navigation drawer")
        self.btn_collapse.clicked.connect(self.toggle_sidebar_collapse)
        self.brand_layout.addWidget(self.icon_lbl)
        self.brand_layout.addWidget(self.app_title)
        self.brand_layout.addStretch(1)
        self.brand_layout.addWidget(self.btn_collapse)

        # Nav Buttons (Steam uppercase styling)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_store = QPushButton("  STORE")
        self.btn_store.setObjectName("NavButton")
        self.btn_store.setCheckable(True)
        self.btn_store.setToolTip("Browse and acquire new games")

        self.btn_lib = QPushButton("  LIBRARY")
        self.btn_lib.setObjectName("NavButton")
        self.btn_lib.setCheckable(True)
        self.btn_lib.setChecked(True)
        self.btn_lib.setToolTip("Your installed and available game library")

        self.btn_dl = QPushButton("  DOWNLOADS")
        self.btn_dl.setObjectName("NavButton")
        self.btn_dl.setCheckable(True)
        self.btn_dl.setToolTip("Active downloads and extraction queue")

        self.btn_settings = QPushButton("  SETTINGS")
        self.btn_settings.setObjectName("NavButton")
        self.btn_settings.setCheckable(True)
        self.btn_settings.setToolTip("App preferences, themes and directories")

        self.nav_group.addButton(self.btn_store, 1)
        self.nav_group.addButton(self.btn_lib, 0)
        self.nav_group.addButton(self.btn_dl, 2)
        self.nav_group.addButton(self.btn_settings, 3)

        # Top integrated quick search (GOG Galaxy / Cyber slim nav)
        self.top_search = QLineEdit()
        self.top_search.setObjectName("TopQuickSearch")
        self.top_search.setPlaceholderText("Search store…")
        self.top_search.setClearButtonEnabled(True)
        self.top_search.returnPressed.connect(self._on_top_search_submitted)

        # Quick theme switcher button
        self.btn_quick_theme = QPushButton("🎨  Themes")
        self.btn_quick_theme.setObjectName("QuickThemeBtn")
        self.btn_quick_theme.setToolTip("Quickly preview and switch themes")
        self._rebuild_theme_menu()

        self.btn_bp = QPushButton("  ⛶  BIG PICTURE")
        self.btn_bp.setObjectName("BpNavBtn")
        self.btn_bp.setToolTip("Enter Big Picture Mode (or press Guide / Xbox / PS button on controller)")
        self.btn_bp.clicked.connect(self.open_big_picture)

        # Active downloads & running games footer / status badge
        self.status_box = QFrame()
        self.status_box.setObjectName("Card")
        self.sb_foot = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.status_box)
        self.sb_foot.setContentsMargins(10, 8, 10, 8)
        self.sb_foot.setSpacing(4)

        self.dl_badge = QLabel("0 active downloads")
        self.dl_badge.setObjectName("Muted")
        f_b = self.dl_badge.font()
        f_b.setPixelSize(11)
        self.dl_badge.setFont(f_b)

        self.running_badge = QLabel("")
        self.running_badge.setStyleSheet("color: #22c55e; font-weight: bold;")
        f_r = self.running_badge.font()
        f_r.setPixelSize(11)
        self.running_badge.setFont(f_r)
        self.running_badge.setVisible(False)

        self.sb_foot.addWidget(self.dl_badge)
        self.sb_foot.addWidget(self.running_badge)

        # ---------------------------------------------------- MAIN STACK
        self.stack = QStackedWidget()
        self.view_library = LibraryView(ctx, self)
        self.view_store = StoreView(ctx, self)
        self.view_downloads = DownloadsView(ctx, self)
        self.view_settings = SettingsView(ctx, self)
        self.view_detail = GameDetailView(ctx, self)

        self.stack.addWidget(self.view_library)    # 0
        self.stack.addWidget(self.view_store)      # 1
        self.stack.addWidget(self.view_downloads)  # 2
        self.stack.addWidget(self.view_settings)   # 3
        self.stack.addWidget(self.view_detail)     # 4

        self.body_layout.addWidget(self.stack, 1)

        # Determine and apply initial layout mode
        preset_id = self.ctx.config.get_theme_preset()
        preset = theme.get_preset(preset_id)
        cfg_layout = self.ctx.config.get("layout_mode", "preset")
        if cfg_layout == "preset" or not cfg_layout:
            initial_layout = preset.get("layout_mode", "top_nav")
        else:
            initial_layout = cfg_layout
        self.current_layout_mode = initial_layout
        self.apply_layout_mode(initial_layout)

        # Nav connections
        self.nav_group.idClicked.connect(self._on_nav_clicked)
        self.view_store.open_detail.connect(self.open_catalog_item)
        self.view_detail.back_requested.connect(self._go_back)

        # Download and running tracker signals
        ctx.downloads.task_added.connect(lambda *_: self._update_sidebar_badges())
        ctx.downloads.task_updated.connect(lambda *_: self._update_sidebar_badges())
        ctx.downloads.task_removed.connect(lambda *_: self._update_sidebar_badges())
        ctx.downloads.task_finished.connect(lambda *_: self._update_sidebar_badges())
        ctx.library.running_changed.connect(lambda *_: self._update_sidebar_badges())

        self._previous_page = 0
        self._update_sidebar_badges()

        # Big Picture Mode & Controller Support
        self.bp_window: BigPictureWindow | None = None
        self.cm = ControllerManager.get_instance()
        self.cm.signals.guide_pressed.connect(self.toggle_big_picture)
        self.cm.signals.connected.connect(
            lambda idx, name: self.toast(f"🎮 {name} connected! Press Guide button for Big Picture.")
        )
        if self.ctx.config.get("controller_enabled", True):
            self.cm.start()

    def _setup_retro_menu(self) -> None:
        """Create authentic Valve 2003 vintage menu bar."""
        self.retro_menu_bar.clear()

        # Steam Menu
        m_steam = self.retro_menu_bar.addMenu("Steam")
        act_sett = m_steam.addAction("Settings…")
        act_sett.triggered.connect(lambda: self.btn_settings.click())
        act_bp = m_steam.addAction("Big Picture Mode")
        act_bp.triggered.connect(self.open_big_picture)
        m_steam.addSeparator()
        act_exit = m_steam.addAction("Exit")
        act_exit.triggered.connect(self.close)

        # View Menu
        m_view = self.retro_menu_bar.addMenu("View")
        act_lib = m_view.addAction("Library")
        act_lib.triggered.connect(lambda: self.btn_lib.click())
        act_store = m_view.addAction("Store")
        act_store.triggered.connect(lambda: self.btn_store.click())
        act_dl = m_view.addAction("Downloads")
        act_dl.triggered.connect(lambda: self.btn_dl.click())
        m_view.addSeparator()
        m_themes = m_view.addMenu("Themes")
        for p in theme.list_presets():
            act_p = m_themes.addAction(f"{p['name']}")
            act_p.triggered.connect(lambda _, pid=p["id"]: self.set_theme(pid))

        # Friends Menu
        m_friends = self.retro_menu_bar.addMenu("Friends")
        act_stat = m_friends.addAction("Status: Online")
        act_stat.setEnabled(False)

        # Games Menu
        m_games = self.retro_menu_bar.addMenu("Games")
        act_g_lib = m_games.addAction("View Games")
        act_g_lib.triggered.connect(lambda: self.btn_lib.click())
        act_g_scan = m_games.addAction("Scan Steam Library…")
        act_g_scan.triggered.connect(self._scan_steam_silent)

        # Help Menu
        m_help = self.retro_menu_bar.addMenu("Help")
        act_about = m_help.addAction("About Mist")
        act_about.triggered.connect(self._show_about_dialog)

    def _scan_steam_silent(self) -> None:
        try:
            games = steam_scanner.scan_steam()
            added, _ = self.ctx.library.import_steam(games)
            self.toast(f"Steam scan complete: {len(games)} games detected ({added} synced)")
        except Exception as exc:
            self.toast(f"Steam scan error: {exc}")

    def _show_about_dialog(self) -> None:
        p = theme.get_preset(theme.get_current_preset_id())
        QMessageBox.about(
            self,
            "About Mist",
            f"Mist — Unified Game Library Manager\n\n"
            f"Current Theme: {p['name']}\n"
            f"{p['description']}\n\n"
            f"Layout Mode: {self.current_layout_mode}"
        )

    def _rebuild_theme_menu(self) -> None:
        """Populate the quick theme switcher menu with all available presets."""
        menu = QMenu(self)
        cur_id = theme.get_current_preset_id()
        for p in theme.list_presets():
            prefix = "✓  " if p["id"] == cur_id else "     "
            act = menu.addAction(f"{prefix}{p['name']}")
            act.triggered.connect(lambda _, pid=p["id"]: self.set_theme(pid))
        self.btn_quick_theme.setMenu(menu)

    def _on_top_search_submitted(self) -> None:
        """Trigger store search when user enters query in top quick search."""
        txt = self.top_search.text().strip()
        if txt:
            self.btn_store.setChecked(True)
            self.stack.setCurrentIndex(1)
            if hasattr(self.view_store, "search_box"):
                self.view_store.search_box.setText(txt)
                self.view_store._do_search()

    def toggle_sidebar_collapse(self) -> None:
        """Collapse or expand the left vertical navigation drawer."""
        self._sidebar_collapsed = not self._sidebar_collapsed
        if self._sidebar_collapsed:
            self.sidebar.setFixedWidth(64)
            self.btn_collapse.setText("▶")
            self.btn_collapse.setToolTip("Expand navigation drawer")
            self.app_title.setVisible(False)
            self.btn_store.setText("  🏪")
            self.btn_lib.setText("  📚")
            self.btn_dl.setText("  ⬇")
            self.btn_settings.setText("  ⚙")
            self.btn_bp.setText("  ⛶")
            self.btn_quick_theme.setText("🎨")
            self.status_box.setVisible(False)
        else:
            self.sidebar.setFixedWidth(220)
            self.btn_collapse.setText("◀")
            self.btn_collapse.setToolTip("Collapse navigation drawer")
            self.app_title.setVisible(True)
            self.btn_store.setText("  STORE")
            self.btn_lib.setText("  LIBRARY")
            active_dl = self.ctx.downloads.active_count()
            self.btn_dl.setText(f"  DOWNLOADS ({active_dl})" if active_dl > 0 else "  DOWNLOADS")
            self.btn_settings.setText("  SETTINGS")
            self.btn_bp.setText("  ⛶  BIG PICTURE")
            self.btn_quick_theme.setText("🎨  Themes")
            self.status_box.setVisible(True)

    def apply_layout_mode(self, mode: str) -> None:
        """Dynamically adapt window layout to top navigation bar or left sidebar navigation."""
        if mode not in ("top_nav", "sidebar"):
            mode = "top_nav"
        self.current_layout_mode = mode

        # Helper to take items from layout
        def _clear_layout(layout):
            while layout.count():
                layout.takeAt(0)

        _clear_layout(self.top_layout)
        _clear_layout(self.sb_layout)

        # Show retro menu bar exclusively for classic 2003 theme
        is_retro = (theme.current_variant() == "steam_2003")
        self.retro_menu_bar.setVisible(is_retro)

        nav_buttons = [self.btn_store, self.btn_lib, self.btn_dl, self.btn_settings]

        if mode == "top_nav":
            self.sidebar.setVisible(False)
            self.top_bar.setVisible(True)
            self.btn_collapse.setVisible(False)
            self.top_search.setVisible(True)
            self.btn_quick_theme.setText("🎨  Themes")

            for btn in nav_buttons:
                btn.setProperty("nav_layout", "top")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self.btn_bp.setProperty("nav_layout", "top")
            self.btn_bp.style().unpolish(self.btn_bp)
            self.btn_bp.style().polish(self.btn_bp)

            self.sb_foot.setDirection(QBoxLayout.Direction.LeftToRight)
            self.sb_foot.setContentsMargins(10, 4, 10, 4)
            self.status_box.setFixedHeight(34)

            self.top_layout.addWidget(self.brand_widget)
            self.top_layout.addSpacing(14)
            for btn in nav_buttons:
                self.top_layout.addWidget(btn)
            self.top_layout.addSpacing(10)
            self.top_layout.addWidget(self.top_search)
            self.top_layout.addStretch(1)
            self.top_layout.addWidget(self.status_box)
            self.top_layout.addSpacing(6)
            self.top_layout.addWidget(self.btn_quick_theme)
            self.top_layout.addSpacing(4)
            self.top_layout.addWidget(self.btn_bp)

        else:  # sidebar
            self.top_bar.setVisible(False)
            self.sidebar.setVisible(True)
            self.btn_collapse.setVisible(True)
            self.top_search.setVisible(False)
            self.btn_quick_theme.setText("🎨" if self._sidebar_collapsed else "🎨  Themes")

            for btn in nav_buttons:
                btn.setProperty("nav_layout", "sidebar")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self.btn_bp.setProperty("nav_layout", "sidebar")
            self.btn_bp.style().unpolish(self.btn_bp)
            self.btn_bp.style().polish(self.btn_bp)

            self.sb_foot.setDirection(QBoxLayout.Direction.TopToBottom)
            self.sb_foot.setContentsMargins(10, 8, 10, 8)
            self.status_box.setFixedHeight(58)

            self.sb_layout.addWidget(self.brand_widget)
            self.sb_layout.addSpacing(12)
            for btn in nav_buttons:
                self.sb_layout.addWidget(btn)
            self.sb_layout.addSpacing(6)
            self.sb_layout.addWidget(self.btn_bp)
            self.sb_layout.addSpacing(4)
            self.sb_layout.addWidget(self.btn_quick_theme)
            self.sb_layout.addStretch(1)
            self.sb_layout.addWidget(self.status_box)

    def set_theme(self, preset_id: str, layout_mode: str | None = None) -> None:
        """Switch theme preset and layout dynamically without restarting application."""
        resolved_id = theme.get_preset(preset_id)["id"]
        update_dict = {"theme_preset": resolved_id, "theme": resolved_id}
        if layout_mode is not None:
            update_dict["layout_mode"] = layout_mode
        self.ctx.config.update(update_dict)

        app = QApplication.instance()
        if app:
            theme.apply_theme(app, resolved_id)

        # Dynamic layout adaptation
        preset = theme.get_preset(resolved_id)
        chosen_mode = self.ctx.config.get("layout_mode", "preset")
        if chosen_mode == "preset" or not chosen_mode:
            target_layout = preset.get("layout_mode", "top_nav")
        else:
            target_layout = chosen_mode

        self.apply_layout_mode(target_layout)
        self._rebuild_theme_menu()
        self._update_sidebar_badges()
        self._refresh_themed_views()

    def _refresh_themed_views(self) -> None:
        """Request immediate repainting on views using custom delegate drawings."""
        try:
            if hasattr(self, "view_library") and self.view_library:
                if hasattr(self.view_library, "game_list"):
                    self.view_library.game_list.viewport().update()
            if hasattr(self, "view_store") and self.view_store:
                if hasattr(self.view_store, "store_view"):
                    self.view_store.store_view.viewport().update()
            if hasattr(self, "view_downloads") and self.view_downloads:
                self.view_downloads.update()
            if hasattr(self, "view_settings") and self.view_settings:
                if hasattr(self.view_settings, "on_theme_updated"):
                    self.view_settings.on_theme_updated()
            self.update()
        except Exception:
            pass

    def toast(self, text: str):
        Toast(self, text)

    def _on_nav_clicked(self, page_id: int):
        self._previous_page = self.stack.currentIndex()
        self.stack.setCurrentIndex(page_id)

    def open_game(self, game_id: int):
        self._previous_page = self.stack.currentIndex()
        self.view_detail.load_library_game(game_id)
        self.stack.setCurrentWidget(self.view_detail)

    def open_catalog_item(self, item: CatalogItem):
        self._previous_page = self.stack.currentIndex()
        self.view_detail.load_catalog_item(item)
        self.stack.setCurrentWidget(self.view_detail)

    def _go_back(self):
        dest = self._previous_page if self._previous_page in (0, 1, 2, 3) else 0
        btn = self.nav_group.button(dest)
        if btn:
            btn.setChecked(True)
        self.stack.setCurrentIndex(dest)

    def _update_sidebar_badges(self):
        active_dl = self.ctx.downloads.active_count()
        if active_dl > 0:
            self.btn_dl.setText(f"  DOWNLOADS ({active_dl})")
            self.dl_badge.setText(f"{active_dl} downloading…")
            self.dl_badge.setStyleSheet(f"color: {theme.C.get('accent', '#66c0f4')}; font-weight: bold;")
        else:
            self.btn_dl.setText("  DOWNLOADS")
            tot = len(self.ctx.downloads.tasks())
            self.dl_badge.setText(f"{tot} tasks" if tot else "No downloads")
            self.dl_badge.setStyleSheet("")

        # Check running games
        running_count = sum(1 for g in self.ctx.library.games() if self.ctx.library.is_running(g["id"]))
        if running_count > 0:
            self.running_badge.setText(f"● {running_count} running")
            self.running_badge.setVisible(True)
        else:
            self.running_badge.setVisible(False)

    def toggle_big_picture(self):
        if self.bp_window and self.bp_window.isVisible():
            self.bp_window.close()
        else:
            self.open_big_picture()

    def open_big_picture(self):
        if self.bp_window and self.bp_window.isVisible():
            self.bp_window.raise_()
            self.bp_window.activateWindow()
            return
        self.bp_window = BigPictureWindow(self.ctx, None)
        self.bp_window.closed.connect(self._on_bp_closed)
        self.bp_window.showFullScreen()

    def _on_bp_closed(self):
        self.bp_window = None

    def closeEvent(self, e):
        if self.bp_window:
            try:
                self.bp_window.close()
            except Exception:
                pass
        self.cm.stop()
        self.ctx.downloads.shutdown()
        if hasattr(self.ctx, "images") and self.ctx.images:
            self.ctx.images.shutdown()
        shutdown_async()
        self.ctx.config.save()
        super().closeEvent(e)
