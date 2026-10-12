"""Mist desktop application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure App directory is in sys.path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from Core import paths, steam_scanner
from Core.config import Config
from Core.database import Database
from Core.downloader import DownloadManager
from Core.images import ImageLoader
from Core.library import LibraryManager
from Core.logger import get_logger, setup_logging
from Core.sources import SourceRegistry
from UI.common import app_icon, run_async
from UI.context import AppContext
from UI.main_window import MainWindow
from UI.theme import apply_theme
from UI.wizard import SetupWizardDialog

log = get_logger("mist")


def main() -> int:
    paths.ensure_dirs()
    setup_logging()
    log.info("Starting Mist game library manager...")

    app = QApplication(sys.argv)
    app.setApplicationName("Mist")
    app.setOrganizationName("Mist")
    app.setWindowIcon(app_icon())

    # Core services
    config = Config()
    database = Database()
    sources = SourceRegistry(config)
    sources.load()
    library = LibraryManager(database)
    downloader = DownloadManager(config, sources, library)
    images = ImageLoader()

    ctx = AppContext(
        config=config,
        db=database,
        sources=sources,
        library=library,
        downloads=downloader,
        images=images,
    )

    # Apply configured theme preset
    apply_theme(app, config.get_theme_preset())

    # First launch wizard if not yet configured
    if not config.get("first_run_complete", False):
        wizard = SetupWizardDialog(ctx)
        if wizard.exec() != SetupWizardDialog.Accepted:
            log.info("Setup wizard was cancelled by user; continuing with defaults.")
            config.set("first_run_complete", True)

    # Initial auto-scan for Steam if enabled
    if config.get("auto_scan_steam", True):
        def scan_steam_task():
            return steam_scanner.scan_steam()

        def on_steam_scanned(games):
            added, stale = library.import_steam(games)
            log.info("Startup Steam scan synced %d games", added)

        run_async(scan_steam_task, on_steam_scanned)

    window = MainWindow(ctx)
    window.show()

    ret = app.exec()
    downloader.shutdown()
    database.close()
    return ret


if __name__ == "__main__":
    sys.exit(main())
