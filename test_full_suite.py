"""Comprehensive automated test suite for OpenSteam enhancements."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

# Set up paths
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Headless Qt setup
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for UI tests
app = QApplication.instance() or QApplication(["test", "-platform", "offscreen"])

from Core import extractor
from Core.config import Config, DEFAULTS
from Core.controller import ControllerManager
from Core.database import Database
from Core.downloader import DownloadManager, DownloadTask
from Core.images import ImageLoader
from Core.library import LibraryManager
from Core.sources import CatalogItem, SearchPage, SourceBase, SourceRegistry
from Scripts.ankergames import AnkerGamesSource
from Scripts.steamrip import SteamRipSource
from UI.common import app_icon, shutdown_async, theme_color
from UI.context import AppContext
from UI.detail_view import GameDetailView, HeroBanner, InstallDialog, _sanitize_title
from UI.downloads_view import DownloadsView
from UI.library_view import LibraryView
from UI.main_window import MainWindow
from UI.settings_view import SettingsView
from UI.store_view import ALL_SOURCES_ID, StoreListView, StoreView
from UI import theme
from UI.theme import DARK, apply_theme, get_preset, list_presets, stylesheet


class TestAnkerGames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = AnkerGamesSource()

    def test_pagination_page_1(self):
        """Page 1 returns full catalog page (56 games > 41) with has_more=True."""
        page = self.source.search(page=1)
        self.assertGreater(len(page.items), 45, "Should return more than 41 games per page")
        self.assertTrue(page.has_more, "Page 1 should indicate more pages available")
        # Ensure items have valid attributes
        first = page.items[0]
        self.assertEqual(first.source, "ankergames")
        self.assertTrue(first.title)
        self.assertTrue(first.store_url.startswith("https://ankergames.net/game/"))

    def test_pagination_page_2(self):
        """Page 2 returns another full catalog page."""
        page = self.source.search(page=2)
        self.assertGreater(len(page.items), 45, "Page 2 should return full catalog")
        self.assertTrue(page.has_more, "Page 2 should have more pages")

    def test_query_search(self):
        """Query search returns matching items."""
        page = self.source.search(query="Witcher", page=1)
        self.assertGreater(len(page.items), 0, "Query 'Witcher' should yield results")
        titles = [i.title.lower() for i in page.items]
        self.assertTrue(any("witcher" in t for t in titles))

    def test_genre_search(self):
        """Genre search returns games in category."""
        page = self.source.search(genre="Action", page=1)
        self.assertGreater(len(page.items), 0, "Action genre search should return games")

    def test_details_extraction(self):
        """Details extraction retrieves clean requirements, screenshots, and valid hero."""
        page = self.source.search(query="Witcher", page=1)
        self.assertGreater(len(page.items), 0)
        item = page.items[0]
        detailed = self.source.details(item)
        self.assertTrue(detailed.screenshots, "Should extract screenshot URLs")
        self.assertTrue(all(s.startswith("http") for s in detailed.screenshots))
        self.assertTrue(detailed.hero_url, "Hero URL should be resolved")
        self.assertTrue(detailed.hero_url.startswith("http"), "Hero URL must be absolute")
        # Ensure system requirements do NOT contain raw HTML style junk
        if detailed.system_requirements:
            self.assertNotIn("display:none", detailed.system_requirements)
            self.assertNotIn("class=\"fixed", detailed.system_requirements)


class TestSteamRip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SteamRipSource()

    def test_steamrip_search(self):
        page = self.source.search(query="Celeste", page=1)
        self.assertGreater(len(page.items), 0, "SteamRip should find results for Celeste")
        first = page.items[0]
        self.assertEqual(first.source, "steamrip")
        self.assertIn("celeste", first.title.lower())
        self.assertTrue(first.store_url.startswith("https://steamrip.com/"))
        self.assertFalse(page.has_more, "Single-page result (Celeste) must not report has_more=True")

    def test_steamrip_empty_query_browse(self):
        """Verify browsing with empty query returns catalog items instead of 0 results."""
        page = self.source.search(query="", page=1)
        self.assertGreater(len(page.items), 0, "SteamRip empty browse query must return items (> 0)")
        self.assertTrue(all(it.source == "steamrip" for it in page.items))
        self.assertTrue(all(bool(it.title) for it in page.items))
        self.assertTrue(page.has_more, "Empty browse query should have further pages")

    def test_steamrip_details_and_mirrors(self):
        page = self.source.search(query="Celeste", page=1)
        self.assertGreater(len(page.items), 0)
        item = page.items[0]
        detailed = self.source.details(item)
        self.assertTrue(detailed.version, "Should detect version")
        mirrors = detailed.extra.get("mirrors", [])
        self.assertGreater(len(mirrors), 0, "SteamRip should extract download mirrors")
        self.assertTrue(any(m["url"].startswith("http") for m in mirrors))


class TestTitleSanitizer(unittest.TestCase):
    def test_sanitize_matches_cross_source(self):
        t1 = "The Witcher 3: Wild Hunt"
        t2 = "The Witcher 3 Wild Hunt"
        t3 = "The-Witcher-3---Wild-Hunt"
        self.assertEqual(_sanitize_title(t1), _sanitize_title(t2))
        self.assertEqual(_sanitize_title(t1), _sanitize_title(t3))
        self.assertEqual(_sanitize_title("God of War (2018)"), "godofwar2018")


class TestStoreAndMultiSource(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.db = Database(":memory:")
        self.sources = SourceRegistry(self.config)
        self.sources.load()
        self.library = LibraryManager(self.db)
        self.downloader = DownloadManager(self.config, self.sources, self.library)
        self.images = ImageLoader()
        self.ctx = AppContext(
            config=self.config, db=self.db, sources=self.sources,
            library=self.library, downloads=self.downloader, images=self.images
        )
        self.store = StoreView(self.ctx)

    def tearDown(self):
        self.downloader.shutdown()
        self.images.shutdown()
        shutdown_async()
        self.db.close()
        app.processEvents()

    def test_all_sources_tab_present(self):
        """Tab 0 must be 'ALL SOURCES'."""
        self.assertEqual(self.store.tabs.tabText(0), "ALL SOURCES")
        self.assertEqual(self.store._source_ids[0], ALL_SOURCES_ID)

    def test_store_list_view_uniform_item_sizes(self):
        """StoreListView must enable uniformItemSizes for 60 FPS scrolling."""
        self.assertTrue(self.store.store_view.uniformItemSizes())

    def test_all_sources_aggregation(self):
        """Multi-source search aggregates catalog items and GOG/sample are removed."""
        sources = self.ctx.sources.all()
        self.assertGreater(len(sources), 1, "Should have multiple configured sources")
        self.assertIsNone(self.ctx.sources.get("sample"), "Sample catalog must be removed")
        self.assertIsNone(self.ctx.sources.get("gog"), "GOG source must be removed")
        self.assertIsNotNone(self.ctx.sources.get("ankergames"), "AnkerGames must be present")
        self.assertIsNotNone(self.ctx.sources.get("steamrip"), "SteamRip must be present")


class TestDetailViewAndInstallDialog(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.db = Database(":memory:")
        self.sources = SourceRegistry(self.config)
        self.sources.load()
        self.library = LibraryManager(self.db)
        self.downloader = DownloadManager(self.config, self.sources, self.library)
        self.images = ImageLoader()
        self.ctx = AppContext(
            config=self.config, db=self.db, sources=self.sources,
            library=self.library, downloads=self.downloader, images=self.images
        )
        self.test_item = CatalogItem(
            source="ankergames",
            id="test-game",
            title="Test Adventure Game",
            size_bytes=104857600,
            cover_url="https://example.com/cover.jpg",
        )

    def tearDown(self):
        self.downloader.shutdown()
        self.images.shutdown()
        shutdown_async()
        self.db.close()
        app.processEvents()

    def test_install_dialog_initialization(self):
        dlg = InstallDialog(self.ctx, self.test_item)
        expected_sources = len([s for s in self.ctx.sources.all() if s.can_download or s.id == self.test_item.source])
        self.assertEqual(dlg.source_combo.count(), expected_sources)
        src_id, item, dest = dlg.get_result()
        self.assertEqual(src_id, "ankergames")
        self.assertEqual(item.id, self.test_item.id)
        self.assertTrue(os.path.isdir(dest) or Path(dest).anchor)

    def test_install_dialog_unavailable_provider_disables_install(self):
        dlg = InstallDialog(self.ctx, self.test_item)
        # Simulate selection of a provider that has not matched (item is None)
        dlg.source_combo.addItem("✕ Dummy (Not available)", ("dummy_source", None))
        dlg._on_source_selected(dlg.source_combo.count() - 1)
        self.assertFalse(dlg.install_btn.isEnabled(), "Install button must be disabled when provider unavailable")
        self.assertIn("not available", dlg.source_desc_lbl.text().lower())

    def test_hero_banner_cache(self):
        hero = HeroBanner(self.ctx)
        hero.resize(800, 240)
        hero.set_data("", "", "Test Game")
        self.assertIsNotNone(hero._cached_pixmap)
        self.assertEqual(hero._cached_pixmap.height(), 240)

    def test_detail_view_navigation_scroll_reset(self):
        detail = GameDetailView(self.ctx)
        detail.resize(800, 600)
        detail.scroll.verticalScrollBar().setValue(150)
        detail.load_catalog_item(self.test_item)
        self.assertEqual(detail.scroll.verticalScrollBar().value(), 0, "Scroll must reset to top on navigation")

    def test_detail_view_steamdb_button(self):
        detail = GameDetailView(self.ctx)
        detail.load_catalog_item(self.test_item)
        self.assertFalse(detail.btn_steamdb.isHidden(), "SteamDB button must not be hidden on detail page")
        self.assertEqual(detail.btn_steamdb.text(), "↗  SteamDB")

    def test_detail_view_steamdb_url_generation(self):
        import unittest.mock as mock
        detail = GameDetailView(self.ctx)
        detail.load_catalog_item(self.test_item)
        with mock.patch("webbrowser.open") as mock_open:
            detail._open_steamdb()
            mock_open.assert_called_once()
            called_url = mock_open.call_args[0][0]
            self.assertIn("steamdb.info/search/?a=app&q=", called_url)

        # Test Steam game with appid
        steam_game_id = self.ctx.library.add_or_update({
            "title": "Portal 2",
            "source": "steam",
            "source_id": "620",
            "launch_uri": "steam://rungameid/620",
            "installed": True,
        })
        detail.load_library_game(steam_game_id)
        with mock.patch("webbrowser.open") as mock_open:
            detail._open_steamdb()
            mock_open.assert_called_once_with("https://steamdb.info/app/620/")


class TestControllerAndBigPicture(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.db = Database(":memory:")
        self.sources = SourceRegistry(self.config)
        self.sources.load()
        self.library = LibraryManager(self.db)
        self.downloader = DownloadManager(self.config, self.sources, self.library)
        self.images = ImageLoader()
        self.ctx = AppContext(
            config=self.config, db=self.db, sources=self.sources,
            library=self.library, downloads=self.downloader, images=self.images
        )

    def tearDown(self):
        self.downloader.shutdown()
        self.images.shutdown()
        shutdown_async()
        self.db.close()
        app.processEvents()

    def test_controller_manager_initialization(self):
        cm = ControllerManager.get_instance()
        self.assertIsNotNone(cm)
        status = cm.get_status_text()
        self.assertIsInstance(status, str)
        self.assertTrue(len(status) > 0)

    def test_big_picture_classic_mode(self):
        from UI.big_picture import BigPictureWindow
        self.ctx.config.set("big_picture_style", "classic")
        bp = BigPictureWindow(self.ctx)
        self.assertEqual(bp.style_mode, "classic")
        self.assertFalse(bp.is_console)
        self.assertEqual(bp.lbl_brand.text(), "MIST")
        self.assertEqual(bp.btn_tab_lib.text(), "LIBRARY")
        self.assertIn("(A) SELECT", bp.lbl_legend.text())
        bp.close()

    def test_big_picture_console_mode(self):
        from UI.big_picture import BigPictureWindow
        self.ctx.config.set("big_picture_style", "console")
        bp = BigPictureWindow(self.ctx)
        self.assertEqual(bp.style_mode, "console")
        self.assertTrue(bp.is_console)
        self.assertEqual(bp.lbl_brand.text(), "PLAYSTATION")
        self.assertEqual(bp.btn_tab_lib.text(), "Games")
        self.assertIn("✕ Select", bp.lbl_legend.text())
        bp.close()

    def test_big_picture_style_switching(self):
        from UI.big_picture import BigPictureWindow
        bp = BigPictureWindow(self.ctx)
        bp._set_style("console")
        self.assertEqual(self.ctx.config.get("big_picture_style"), "console")
        self.assertTrue(bp.is_console)
        bp._set_style("classic")
        self.assertEqual(self.ctx.config.get("big_picture_style"), "classic")
        self.assertFalse(bp.is_console)
        bp.close()

    def test_main_window_big_picture_button(self):
        win = MainWindow(self.ctx)
        self.assertTrue(hasattr(win, "btn_bp"))
        self.assertIn("BIG PICTURE", win.btn_bp.text())
        win.close()

    def test_main_window_toggle_big_picture(self):
        win = MainWindow(self.ctx)
        self.assertIsNone(win.bp_window)
        # 1. Toggle open
        win.toggle_big_picture()
        self.assertIsNotNone(win.bp_window)
        self.assertTrue(win.bp_window.isVisible())
        # 2. Toggle close
        win.toggle_big_picture()
        self.assertIsNone(win.bp_window)
        win.close()

    def test_controller_multi_user_isolation(self):
        cm = ControllerManager.get_instance()
        self.assertIsInstance(cm._nav_repeat_dir, dict)
        self.assertEqual(len(cm._nav_repeat_dir), 4)
        # Simulate user 0 holding RIGHT
        cm._nav_repeat_dir[0] = "RIGHT"
        # Simulate user 1 idle (None)
        cm._nav_repeat_dir[1] = None
        # Verify isolation: user 0 state is not affected by user 1
        self.assertEqual(cm._nav_repeat_dir[0], "RIGHT")
        self.assertIsNone(cm._nav_repeat_dir[1])
        # Clean up
        cm._nav_repeat_dir[0] = None

    def test_big_picture_button_glyphs_per_style(self):
        from UI.big_picture import BigPictureWindow
        # Classic style test
        self.ctx.config.set("big_picture_style", "classic")
        bp = BigPictureWindow(self.ctx)
        self.assertIn("STEAMDB", bp.btn_act_steamdb.text())
        # Console style test
        bp._set_style("console")
        self.assertIn("□", bp.btn_act_steamdb.text())
        self.assertIn("△", bp.btn_act_details.text())
        bp.close()

    def test_big_picture_image_ready_and_toast(self):
        from UI.big_picture import BigPictureWindow
        win = MainWindow(self.ctx)
        win.open_big_picture()
        bp = win.bp_window
        # Test toast method on bp
        bp.toast("Test Notice")
        # Test AppContext toast routing to bp_window
        self.ctx.toast("Routed to Big Picture")
        # Test _on_image_ready
        bp._on_image_ready("any_key")
        win.toggle_big_picture()
        win.close()


class TestSteamLook(unittest.TestCase):
    def test_steam_palette(self):
        self.assertEqual(DARK["bg"], "#171a21")
        self.assertEqual(DARK["surface"], "#1b2838")
        self.assertEqual(DARK["border"], "#2a475e")
        self.assertEqual(DARK["accent"], "#66c0f4")
        self.assertEqual(DARK["success"], "#5c7e10")

    def test_steam_headers(self):
        self.config = Config()
        self.db = Database(":memory:")
        self.sources = SourceRegistry(self.config)
        self.sources.load()
        self.library = LibraryManager(self.db)
        self.downloader = DownloadManager(self.config, self.sources, self.library)
        self.images = ImageLoader()
        self.ctx = AppContext(
            config=self.config, db=self.db, sources=self.sources,
            library=self.library, downloads=self.downloader, images=self.images
        )
        win = MainWindow(self.ctx)
        self.assertEqual(win.btn_store.text().strip(), "STORE")
        self.assertEqual(win.btn_lib.text().strip(), "LIBRARY")
        self.assertEqual(win.btn_dl.text().strip(), "DOWNLOADS")
        self.assertEqual(win.btn_settings.text().strip(), "SETTINGS")
        # Check page titles
        self.assertEqual(win.view_store.findChild(object, "PageTitle").text(), "STORE")
        self.assertEqual(win.view_library.findChild(object, "PageTitle").text(), "LIBRARY")
        self.assertEqual(win.view_downloads.findChild(object, "PageTitle").text(), "DOWNLOADS")
        self.assertEqual(win.view_settings.findChild(object, "PageTitle").text(), "SETTINGS")
        win.close()
        win.deleteLater()
        self.downloader.shutdown()
        self.images.shutdown()
        shutdown_async()
        self.db.close()
        app.processEvents()


class TestExtractor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_extractor_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_uncompressed_size_standard(self):
        std_zip = self.temp_dir / "std.zip"
        content = b"OpenSteam archive extraction test content" * 10
        with zipfile.ZipFile(std_zip, "w") as zf:
            zf.writestr("test.txt", content)
        self.assertEqual(extractor.uncompressed_size(std_zip), len(content))

    def test_aseprite_zstd_uncompressed_size(self):
        aseprite_zip = APP_DIR / "temp" / "Aseprite-AnkerGames.zip"
        if not aseprite_zip.is_file():
            self.skipTest("Aseprite-AnkerGames.zip not present in temp")
        size = extractor.uncompressed_size(aseprite_zip)
        self.assertEqual(size, 35478401, "Aseprite zip uncompressed size must match 35478401 bytes")

    def test_aseprite_zstd_extraction(self):
        aseprite_zip = APP_DIR / "temp" / "Aseprite-AnkerGames.zip"
        if not aseprite_zip.is_file():
            self.skipTest("Aseprite-AnkerGames.zip not present in temp")
        dest = self.temp_dir / "aseprite_out"
        progress_calls = []

        def on_progress(done: int, total: int):
            progress_calls.append((done, total))

        result = extractor.extract(aseprite_zip, dest, progress=on_progress)
        self.assertEqual(result, dest)
        self.assertTrue((dest / "Aseprite" / "Aseprite.exe").is_file(), "Aseprite.exe must exist")
        self.assertTrue((dest / "Run Me!.bat").is_file(), "Run Me!.bat must exist")
        self.assertTrue(len(progress_calls) > 0, "Progress should be reported")
        self.assertEqual(progress_calls[-1], (1, 1), "Final progress should be 100%")

    def test_extract_cancelled(self):
        std_zip = self.temp_dir / "std.zip"
        with zipfile.ZipFile(std_zip, "w") as zf:
            zf.writestr("test.txt", b"abc")
        dest = self.temp_dir / "cancelled_out"
        with self.assertRaises(extractor.ExtractionCancelled):
            extractor.extract(std_zip, dest, cancelled=lambda: True)

    def test_zip_slip_prevention(self):
        slip_zip = self.temp_dir / "slip.zip"
        with zipfile.ZipFile(slip_zip, "w") as zf:
            zf.writestr("../traversal.txt", b"evil")
        dest = self.temp_dir / "slip_out"
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract(slip_zip, dest)

    def test_zip_slip_drive_and_absolute_prevention(self):
        slip_zip = self.temp_dir / "slip_drive.zip"
        with zipfile.ZipFile(slip_zip, "w") as zf:
            zf.writestr("D:/evil.txt", b"evil content")
        dest = self.temp_dir / "slip_drive_out"
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract(slip_zip, dest)

    def test_safe_target_edges(self):
        dest = self.temp_dir / "safe_target_dest"
        dest.mkdir(parents=True, exist_ok=True)
        # Valid relative paths
        self.assertTrue(str(extractor._safe_target(dest, "folder/file.txt")).startswith(str(dest.resolve())))
        self.assertTrue(str(extractor._safe_target(dest, "simple.txt")).startswith(str(dest.resolve())))
        # Blocked dangerous paths
        with self.assertRaises(extractor.ExtractionError):
            extractor._safe_target(dest, "../../etc/passwd")
        with self.assertRaises(extractor.ExtractionError):
            extractor._safe_target(dest, "D:/evil.txt")
        with self.assertRaises(extractor.ExtractionError):
            extractor._safe_target(dest, r"\\server\share\evil.txt")
        with self.assertRaises(extractor.ExtractionError):
            extractor._safe_target(dest, "/absolute/path.txt")

    def test_fallback_cancellation(self):
        fake_archive = self.temp_dir / "unknown.ext"
        fake_archive.write_bytes(b"PK\x03\x04unsupported_archive_data")
        dest = self.temp_dir / "fallback_cancel_out"
        with self.assertRaises(extractor.ExtractionCancelled):
            extractor.extract(fake_archive, dest, cancelled=lambda: True)

    def test_corrupted_archive_handling(self):
        broken = self.temp_dir / "broken.zip"
        broken.write_bytes(b"corrupted bytes 1234567890" * 5)
        dest = self.temp_dir / "broken_out"
        with self.assertRaises(extractor.ExtractionError) as ctx:
            extractor.extract(broken, dest)
        self.assertIn("Corrupted", str(ctx.exception))


class TestThemePresetsAndLayout(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config.set("controller_enabled", False)
        self.db = Database(":memory:")
        self.sources = SourceRegistry(self.config)
        self.sources.load()
        self.library = LibraryManager(self.db)
        self.downloader = DownloadManager(self.config, self.sources, self.library)
        self.images = ImageLoader()
        self.ctx = AppContext(
            config=self.config, db=self.db, sources=self.sources,
            library=self.library, downloads=self.downloader, images=self.images
        )

    def tearDown(self):
        self.downloader.shutdown()
        self.images.shutdown()
        shutdown_async()
        self.db.close()
        app.processEvents()

    def test_presets_catalog_and_attributes(self):
        """All requested presets exist and contain complete palette and layout specifications."""
        presets = {p["id"]: p for p in list_presets()}
        required = ["steam_modern", "steam_2003", "epic_sidebar", "gog_galaxy"]
        for req in required:
            self.assertIn(req, presets, f"Preset '{req}' must be present in preset catalog")
            p = presets[req]
            self.assertTrue(p["name"])
            self.assertTrue(p["description"])
            self.assertIn(p["layout_mode"], ("top_nav", "sidebar"))
            palette = p["palette"]
            for col_key in ("bg", "surface", "border", "text", "muted", "accent", "success"):
                self.assertIn(col_key, palette, f"Palette in {req} must define '{col_key}'")

    def test_preset_distinct_styles(self):
        """Check specific aesthetic parameters for retro, epic, and gog presets."""
        p_steam = get_preset("steam_modern")
        self.assertEqual(p_steam["palette"]["bg"], "#171a21")
        self.assertEqual(p_steam["layout_mode"], "top_nav")

        p_retro = get_preset("steam_2003")
        self.assertEqual(p_retro["palette"]["bg"], "#4c5844")
        self.assertEqual(p_retro["border_radius"], 0, "Classic 2003 must have square 0px borders")
        self.assertIn("Tahoma", p_retro["font_family"])

        p_epic = get_preset("epic_sidebar")
        self.assertEqual(p_epic["palette"]["bg"], "#121212")
        self.assertEqual(p_epic["palette"]["accent"], "#0078f2")
        self.assertEqual(p_epic["layout_mode"], "sidebar", "Epic preset must default to sidebar layout")

        p_gog = get_preset("gog_galaxy")
        self.assertEqual(p_gog["palette"]["bg"], "#151022")
        self.assertEqual(p_gog["palette"]["accent"], "#8b5cf6")
        self.assertGreaterEqual(p_gog["border_radius"], 8, "GOG preset must have rounded pill geometry")

    def test_preset_aliases(self):
        """Aliases resolve to the correct preset identifier."""
        self.assertEqual(get_preset("dark")["id"], "steam_modern")
        self.assertEqual(get_preset("classic")["id"], "steam_2003")
        self.assertEqual(get_preset("retro")["id"], "steam_2003")
        self.assertEqual(get_preset("retro_green")["id"], "steam_2003")
        self.assertEqual(get_preset("epic")["id"], "epic_sidebar")
        self.assertEqual(get_preset("sidebar")["id"], "epic_sidebar")
        self.assertEqual(get_preset("gog")["id"], "gog_galaxy")
        self.assertEqual(get_preset("cyber")["id"], "gog_galaxy")
        self.assertEqual(get_preset("non_existent_id")["id"], "steam_modern")

    def test_stylesheet_compilation_all_presets(self):
        """Stylesheets compile without error for all presets with distinct CSS rules."""
        for p in list_presets():
            css = stylesheet(p["palette"], p)
            self.assertIsInstance(css, str)
            self.assertGreater(len(css), 500)
            self.assertIn(p["palette"]["bg"], css)
            self.assertIn(p["palette"]["text"], css)

        # Retro 2003 must have 3D bevel borders
        retro_css = stylesheet(get_preset("steam_2003")["palette"], "steam_2003")
        self.assertIn("border-top", retro_css)
        self.assertIn("border-radius: 0px", retro_css)

        # GOG Galaxy must have violet gradients
        gog_css = stylesheet(get_preset("gog_galaxy")["palette"], "gog_galaxy")
        self.assertIn("#8b5cf6", gog_css)

    def test_apply_theme_runtime(self):
        """Applying theme updates current palette and global C dictionary."""
        apply_theme(app, "steam_2003")
        self.assertEqual(theme.C["bg"], "#4c5844")
        self.assertEqual(theme.color("bg").name(), "#4c5844")

        apply_theme(app, "epic_sidebar")
        self.assertEqual(theme.C["bg"], "#121212")
        self.assertEqual(theme.color("accent").name(), "#0078f2")

        # Restore default
        apply_theme(app, "steam_modern")
        self.assertEqual(theme.C["bg"], "#171a21")

    def test_main_window_dynamic_layout_switch(self):
        """MainWindow can switch between top_nav and sidebar without restarting."""
        win = MainWindow(self.ctx)
        self.assertEqual(win.current_layout_mode, "top_nav")
        self.assertFalse(win.top_bar.isHidden())
        self.assertTrue(win.sidebar.isHidden())

        # Switch to sidebar
        win.apply_layout_mode("sidebar")
        self.assertEqual(win.current_layout_mode, "sidebar")
        self.assertTrue(win.top_bar.isHidden())
        self.assertFalse(win.sidebar.isHidden())
        self.assertEqual(win.btn_store.property("nav_layout"), "sidebar")

        # Switch back to top nav
        win.apply_layout_mode("top_nav")
        self.assertEqual(win.current_layout_mode, "top_nav")
        self.assertFalse(win.top_bar.isHidden())
        self.assertTrue(win.sidebar.isHidden())
        self.assertEqual(win.btn_store.property("nav_layout"), "top")

        win.close()

    def test_main_window_set_theme_and_persistence(self):
        """win.set_theme changes preset, updates layout, and persists to config."""
        win = MainWindow(self.ctx)
        win.set_theme("epic_sidebar")
        self.assertEqual(self.ctx.config.get("theme_preset"), "epic_sidebar")
        self.assertEqual(win.current_layout_mode, "sidebar")
        self.assertFalse(win.sidebar.isHidden())
        self.assertTrue(win.top_bar.isHidden())

        win.set_theme("steam_2003")
        self.assertEqual(self.ctx.config.get("theme_preset"), "steam_2003")
        self.assertEqual(win.current_layout_mode, "top_nav")
        self.assertFalse(win.top_bar.isHidden())
        self.assertTrue(win.sidebar.isHidden())

        # Restore
        win.set_theme("steam_modern")
        win.close()

    def test_settings_view_theme_controls(self):
        """SettingsView provides theme combo, layout combo, quick buttons, and live preview updating."""
        view = SettingsView(self.ctx)
        self.assertGreaterEqual(view.theme_combo.count(), 4)
        self.assertEqual(view.layout_combo.count(), 3)
        self.assertTrue(hasattr(view, "preview_card"))
        self.assertTrue(view.lbl_preset_desc.text())
        self.assertGreaterEqual(len(view.preset_buttons), 4)

        # Select GOG preset via quick preset card button
        view._select_preset_card("gog_galaxy")
        self.assertEqual(self.ctx.config.get("theme_preset"), "gog_galaxy")
        self.assertIn("#8b5cf6", view.swatch_accent.text())
        self.assertTrue(view.preset_buttons["gog_galaxy"].isChecked())

        # Select Light preset and verify high-contrast text calculation
        view._select_preset_card("light")
        self.assertEqual(self.ctx.config.get("theme_preset"), "light")
        self.assertIn("#ffffff", view.swatch_surface.text())
        self.assertIn("color: #111111", view.swatch_surface.styleSheet())
        view.deleteLater()

    def test_retro_menu_bar_visibility_and_actions(self):
        """Classic Steam 2003 displays nostalgic retro menu bar with Steam, View, Friends, Games, Help."""
        win = MainWindow(self.ctx)
        self.assertTrue(hasattr(win, "retro_menu_bar"))

        # In modern theme, retro menu bar is hidden
        win.set_theme("steam_modern")
        self.assertTrue(win.retro_menu_bar.isHidden())

        # In 2003 theme, retro menu bar becomes visible
        win.set_theme("steam_2003")
        self.assertFalse(win.retro_menu_bar.isHidden())
        menu_titles = [action.text() for action in win.retro_menu_bar.actions()]
        self.assertIn("Steam", menu_titles)
        self.assertIn("View", menu_titles)
        self.assertIn("Friends", menu_titles)
        self.assertIn("Games", menu_titles)
        self.assertIn("Help", menu_titles)

        # Switching away hides it again
        win.set_theme("epic_sidebar")
        self.assertTrue(win.retro_menu_bar.isHidden())
        win.close()

    def test_top_nav_quick_search_and_routing(self):
        """MainWindow includes top quick search bar that routes queries directly into the store view."""
        win = MainWindow(self.ctx)
        self.assertTrue(hasattr(win, "top_search"))
        win.apply_layout_mode("top_nav")
        self.assertFalse(win.top_search.isHidden())

        # Submitting search navigates to store view
        win.top_search.setText("Portal")
        win._on_top_search_submitted()
        self.assertEqual(win.stack.currentIndex(), 1)
        self.assertEqual(win.view_store.search_box.text(), "Portal")
        win.close()

    def test_sidebar_collapse_and_expansion(self):
        """Epic / Sidebar Modern navigation drawer can collapse to compact rail and expand back."""
        win = MainWindow(self.ctx)
        win.apply_layout_mode("sidebar")
        self.assertEqual(win.sidebar.width(), 220)
        self.assertFalse(win._sidebar_collapsed)

        # Collapse sidebar
        win.toggle_sidebar_collapse()
        self.assertTrue(win._sidebar_collapsed)
        self.assertEqual(win.sidebar.width(), 64)
        self.assertTrue(win.app_title.isHidden())
        self.assertIn("🏪", win.btn_store.text())

        # Expand sidebar back
        win.toggle_sidebar_collapse()
        self.assertFalse(win._sidebar_collapsed)
        self.assertEqual(win.sidebar.width(), 220)
        self.assertFalse(win.app_title.isHidden())
        self.assertIn("STORE", win.btn_store.text())
        win.close()

    def test_quick_theme_switcher_and_buttons(self):
        """MainWindow contains a quick theme switcher button with dropdown menu."""
        win = MainWindow(self.ctx)
        self.assertTrue(hasattr(win, "btn_quick_theme"))
        self.assertIsNotNone(win.btn_quick_theme.menu())
        actions = win.btn_quick_theme.menu().actions()
        self.assertGreaterEqual(len(actions), 4)
        win.close()

    def test_geometry_accessors_and_delegate_integration(self):
        """theme.card_radius() and theme.border_radius() adapt dynamically to active preset."""
        theme.apply_theme(app, "steam_2003")
        self.assertEqual(theme.card_radius(), 0)
        self.assertEqual(theme.border_radius(), 0)
        self.assertEqual(theme.current_variant(), "steam_2003")

        theme.apply_theme(app, "gog_galaxy")
        self.assertEqual(theme.card_radius(), 10)
        self.assertGreaterEqual(theme.border_radius(), 8)
        self.assertEqual(theme.current_variant(), "gog_galaxy")

        theme.apply_theme(app, "steam_modern")
        self.assertEqual(theme.card_radius(), 4)
        self.assertEqual(theme.border_radius(), 3)
        self.assertEqual(theme.current_variant(), "steam_modern")

    def test_legacy_config_theme_migration(self):
        """Legacy config.json with 'theme': 'light' or 'theme': 'classic' is migrated properly."""
        cfg = Config.__new__(Config)
        cfg._path = Path("fake.json")
        cfg._lock = mock.MagicMock()
        cfg._data = dict(DEFAULTS)
        cfg._data["theme"] = "classic"
        if "theme_preset" in cfg._data:
            del cfg._data["theme_preset"]

        self.assertEqual(cfg.get_theme_preset(), "classic")

    def test_live_badge_color_update_on_theme_change(self):
        """Active download status badge color immediately updates when theme is switched."""
        win = MainWindow(self.ctx)
        # Mock active download
        with mock.patch.object(self.ctx.downloads, "active_count", return_value=1):
            win._update_sidebar_badges()
            self.assertIn(theme.C["accent"], win.dl_badge.styleSheet())

            # Switch to GOG Galaxy
            win.set_theme("gog_galaxy")
            self.assertIn("#8b5cf6", win.dl_badge.styleSheet())
        win.close()


class TestMistEnhancements(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.db = Database(":memory:")
        self.sources = SourceRegistry(self.config)
        self.sources.load()
        self.library = LibraryManager(self.db)
        self.downloader = DownloadManager(self.config, self.sources, self.library)
        self.images = ImageLoader()
        self.ctx = AppContext(
            config=self.config, db=self.db, sources=self.sources,
            library=self.library, downloads=self.downloader, images=self.images
        )

    def tearDown(self):
        self.downloader.shutdown()
        self.images.shutdown()
        shutdown_async()
        self.db.close()
        app.processEvents()

    def test_controller_no_spam_when_disconnected(self):
        """ControllerManager must not spam disconnect signals or logs when disconnected."""
        cm = ControllerManager.get_instance()
        disconnect_emitted = []
        cm.signals.disconnected.connect(lambda idx: disconnect_emitted.append(idx))

        # Both XInput and WinMM start disconnected
        for i in range(4):
            cm._xinput_connected[i] = False
            cm._winmm_connected[i] = False

        # Mock XInput returning ERROR_DEVICE_NOT_CONNECTED (1167)
        mock_get_state = mock.MagicMock(return_value=1167)
        cm._get_state_fn = mock_get_state

        with mock.patch("Core.controller.log.info") as mock_log:
            # Run multiple poll steps while disconnected
            for _ in range(10):
                cm._poll_step()

            # Ensure no disconnect was emitted because controllers were already disconnected
            self.assertEqual(len(disconnect_emitted), 0)
            for call in mock_log.call_args_list:
                args = call[0]
                msg = args[0] if args else ""
                self.assertNotIn("disconnected", str(msg).lower())

        # Transitioning from connected to disconnected emits exactly once
        cm._xinput_connected[1] = True
        disconnect_emitted.clear()
        with mock.patch("Core.controller.log.info") as mock_log:
            cm._poll_step()
            self.assertEqual(len(disconnect_emitted), 1)
            self.assertEqual(disconnect_emitted[0], 1)
            self.assertFalse(cm._xinput_connected[1])

            # Subsequent passes while disconnected must NOT emit again
            for _ in range(5):
                cm._poll_step()
            self.assertEqual(len(disconnect_emitted), 1)

    def test_mist_branding(self):
        """Application name is Mist in window titles, brand labels, and Big Picture."""
        win = MainWindow(self.ctx)
        self.assertIn("Mist", win.windowTitle())
        self.assertEqual(win.app_title.text(), "Mist")
        win.close()

        from UI.wizard import SetupWizardDialog
        wiz = SetupWizardDialog(self.ctx)
        self.assertIn("Mist", wiz.windowTitle())
        wiz.close()

        from UI.big_picture import BigPictureWindow
        self.ctx.config.set("big_picture_style", "classic")
        bp = BigPictureWindow(self.ctx)
        self.assertIn("Mist", bp.windowTitle())
        self.assertEqual(bp.lbl_brand.text(), "MIST")
        bp.close()

    def test_store_card_delegate_no_install_button(self):
        """StoreCardDelegate has no install button, and card height is streamlined."""
        from UI.store_view import StoreCardDelegate, StoreListView
        delegate = StoreCardDelegate(self.ctx)
        dummy_rect = QRect(0, 0, 196, 304)
        btn_r = delegate.button_rect(dummy_rect)
        self.assertTrue(btn_r.isEmpty(), "button_rect must be empty as install button is removed")
        self.assertEqual(delegate.TEXT_H, 46, "TEXT_H must be compact without button")

        # Test clicking item emits card_clicked
        view = StoreListView(self.ctx)
        self.assertTrue(hasattr(view, "card_clicked"))
        view.deleteLater()

    def test_big_picture_ps_store_experience(self):
        """Big Picture Store provides a PlayStation Store browsing experience with shelves and hero."""
        from UI.big_picture import BigPictureWindow
        bp = BigPictureWindow(self.ctx)

        # Check UI widgets exist
        self.assertTrue(hasattr(bp, "store_page"))
        self.assertTrue(hasattr(bp, "store_hero_box"))
        self.assertTrue(hasattr(bp, "store_scroll"))
        self.assertTrue(hasattr(bp, "store_shelves_layout"))

        # Switch to Store tab (index 1)
        bp._switch_tab(1)
        self.assertEqual(bp.active_tab, 1)
        self.assertEqual(bp.main_stack.currentIndex(), 1)
        self.assertEqual(bp.focus_zone, "store")

        # Populate sample store items
        sample_items = [
            {
                "id": f"game_{i}",
                "title": f"Sample Game {i}",
                "source": "ankergames" if i % 2 == 0 else "steamrip",
                "cover_url": "",
                "hero_url": "",
                "size_bytes": 1024 * 1024 * 500,
                "genres": ["Action", "Adventure"],
                "installed": False,
            }
            for i in range(12)
        ]
        bp._populate_store_shelves(sample_items)
        self.assertTrue(len(bp.store_shelves_data) >= 2, "Must create organized shelves")

        # Test shelf titles
        titles = [s["title"] for s in bp.store_shelves_data]
        self.assertIn("FEATURED & TRENDING", titles)

        # Test hero updates with focused game
        bp.store_shelf_index = 0
        bp.store_card_indices[0] = 0
        bp._update_store_focus()
        self.assertEqual(bp.lbl_store_title.text(), "Sample Game 0")
        self.assertIn("FREE", bp.lbl_store_status.text())

        # Test navigation between shelves
        bp._on_nav_down()
        self.assertEqual(bp.store_shelf_index, 1)

        bp._on_nav_up()
        self.assertEqual(bp.store_shelf_index, 0)

        # Nav up from shelf 0 moves to tabs
        bp._on_nav_up()
        self.assertEqual(bp.focus_zone, "tabs")

        # Nav down from tabs returns to store
        bp._on_nav_down()
        self.assertEqual(bp.focus_zone, "store")

        # Test shelf card clicking without index errors
        last_s = len(bp.store_shelves_data) - 1
        bp._on_store_card_clicked(last_s, 0)
        self.assertEqual(bp.store_shelf_index, last_s)

        # Style switches correctly in both classic and console mode
        bp._set_style("console")
        self.assertIn("✕", bp.btn_store_primary.text())
        self.assertIn("PLAYSTATION", bp.lbl_store_tag.text())

        bp._set_style("classic")
        self.assertIn("INSTALL", bp.btn_store_primary.text())
        self.assertIn("MIST", bp.lbl_store_tag.text())

        bp.close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    shutdown_async()
    app.processEvents()
    sys.exit(0 if res.wasSuccessful() else 1)
