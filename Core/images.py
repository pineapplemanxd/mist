"""Asynchronous, cached image loading.

* Images are fetched/decoded on a small thread pool and scaled down to the
  size actually displayed before being turned into pixmaps (keeps RAM low).
* Remote images are cached on disk (``cache/images``) so they're downloaded once.
* An LRU of pixmaps (bounded by approximate byte size) keeps scrolling smooth.
"""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap

from .logger import get_logger
from .paths import IMAGE_CACHE_DIR
from .sources import USER_AGENT

log = get_logger(__name__)


def _cache_file(url: str) -> Path:
    return IMAGE_CACHE_DIR / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".img")


class _Signals(QObject):
    loaded = Signal(str, QImage)   # key, image
    failed = Signal(str)


class _LoadJob(QRunnable):
    def __init__(self, key: str, url: str, size: QSize, crop: bool, signals: _Signals):
        super().__init__()
        self.key, self.url, self.size, self.crop, self.signals = key, url, size, crop, signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            path = self._local_path()
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            src = reader.size()
            if src.isValid() and self.size.isValid():
                # Decode directly at a reduced size: far less memory than full decode + scale.
                mode = Qt.KeepAspectRatioByExpanding if self.crop else Qt.KeepAspectRatio
                reader.setScaledSize(src.scaled(self.size, mode))
            img = reader.read()
            if img.isNull():
                raise ValueError(reader.errorString())
            if self.crop and self.size.isValid():
                x = max(0, (img.width() - self.size.width()) // 2)
                y = max(0, (img.height() - self.size.height()) // 2)
                img = img.copy(x, y, min(img.width(), self.size.width()), min(img.height(), self.size.height()))
            self.signals.loaded.emit(self.key, img)
        except Exception as exc:  # noqa: BLE001
            log.debug("Image load failed for %s: %s", self.url, exc)
            self.signals.failed.emit(self.key)

    def _local_path(self) -> Path:
        if not self.url.lower().startswith(("http://", "https://")):
            return Path(self.url)
        cached = _cache_file(self.url)
        if cached.exists():
            return cached
        req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT})
        tmp = cached.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=20) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out, 64 * 1024)
        tmp.replace(cached)
        return cached


class ImageLoader(QObject):
    """Shared loader. ``get()`` returns a pixmap immediately if cached, else None and
    emits ``image_ready(key)`` once loaded."""

    image_ready = Signal(str)

    def __init__(self, max_bytes: int = 48 * 1024 * 1024, threads: int = 4):
        super().__init__()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(threads)
        self._signals = _Signals()
        self._signals.loaded.connect(self._on_loaded)
        self._signals.failed.connect(self._on_failed)
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._bytes = 0
        self._max_bytes = max_bytes
        self._pending: set[str] = set()
        self._failed: set[str] = set()

    @staticmethod
    def key(url: str, size: QSize, crop: bool = True) -> str:
        return f"{size.width()}x{size.height()}{'c' if crop else ''}|{url}"

    def get(self, url: str, size: QSize, crop: bool = True) -> QPixmap | None:
        if not url:
            return None
        k = self.key(url, size, crop)
        pm = self._cache.get(k)
        if pm is not None:
            self._cache.move_to_end(k)
            return pm
        if k not in self._pending and k not in self._failed:
            self._pending.add(k)
            self._pool.start(_LoadJob(k, url, size, crop, self._signals))
        return None

    def has_failed(self, url: str, size: QSize, crop: bool = True) -> bool:
        return self.key(url, size, crop) in self._failed

    def _on_loaded(self, key: str, img: QImage) -> None:
        self._pending.discard(key)
        pm = QPixmap.fromImage(img)
        self._cache[key] = pm
        self._bytes += pm.width() * pm.height() * 4
        while self._bytes > self._max_bytes and len(self._cache) > 1:
            _, old = self._cache.popitem(last=False)
            self._bytes -= old.width() * old.height() * 4
        self.image_ready.emit(key)

    def _on_failed(self, key: str) -> None:
        self._pending.discard(key)
        self._failed.add(key)
        self.image_ready.emit(key)

    def clear_memory(self) -> None:
        self._cache.clear()
        self._bytes = 0
        self._failed.clear()

    def clear_disk_cache(self) -> int:
        self.clear_memory()
        removed = 0
        if IMAGE_CACHE_DIR.exists():
            for f in IMAGE_CACHE_DIR.iterdir():
                try:
                    removed += f.stat().st_size
                    f.unlink()
                except OSError:
                    pass
        return removed

    def shutdown(self, wait_ms: int = 1500) -> None:
        """Clear queued image tasks and wait for active jobs to complete."""
        try:
            self._pool.clear()
            self._pool.waitForDone(wait_ms)
        except Exception:
            pass
