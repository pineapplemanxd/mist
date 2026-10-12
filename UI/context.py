"""Shared application services passed to every view."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from Core.config import Config
    from Core.database import Database
    from Core.downloader import DownloadManager
    from Core.images import ImageLoader
    from Core.library import LibraryManager
    from Core.sources import SourceRegistry


@dataclass
class AppContext:
    config: "Config"
    db: "Database"
    sources: "SourceRegistry"
    library: "LibraryManager"
    downloads: "DownloadManager"
    images: "ImageLoader"
    window: object = None        # MainWindow (navigation, toasts)

    def toast(self, text: str) -> None:
        if self.window is not None:
            if hasattr(self.window, "bp_window") and self.window.bp_window and self.window.bp_window.isVisible():
                self.window.bp_window.toast(text)
            else:
                self.window.toast(text)
