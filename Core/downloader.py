"""Download & install pipeline.

resolve (source script) -> download to temp (resumable, throttled) ->
verify -> extract into a staging folder -> move into games dir ->
delete archive -> register in library.

Each active task runs in its own daemon thread; the UI is notified through
Qt signals (delivered on the GUI thread via queued connections).
"""
from __future__ import annotations

import hashlib
import itertools
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import extractor, launcher
from .logger import get_logger
from .sources import USER_AGENT, CatalogItem, SourceError

log = get_logger(__name__)

CHUNK = 256 * 1024


class Status(str, Enum):
    QUEUED = "Queued"
    RESOLVING = "Preparing"
    DOWNLOADING = "Downloading"
    PAUSED = "Paused"
    VERIFYING = "Verifying"
    EXTRACTING = "Installing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


ACTIVE = {Status.RESOLVING, Status.DOWNLOADING, Status.VERIFYING, Status.EXTRACTING}
FINISHED = {Status.COMPLETED, Status.FAILED, Status.CANCELLED}


class _Stop(Exception):
    """Internal: worker interrupted by pause/cancel."""


@dataclass
class DownloadTask:
    id: int
    source_id: str
    item: CatalogItem
    status: Status = Status.QUEUED
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0                 # bytes/s
    extract_progress: float = 0.0      # 0..1
    error: str = ""
    archive_path: str = ""
    install_dir: str = ""
    target_install_dir: str = ""
    game_id: int = 0
    created: float = field(default_factory=time.time)
    _pause: threading.Event = field(default_factory=threading.Event, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def progress(self) -> float:
        if self.status == Status.EXTRACTING:
            return self.extract_progress
        return self.downloaded / self.total if self.total else 0.0

    @property
    def eta(self) -> float:
        if self.speed <= 0 or not self.total:
            return -1
        return max(0.0, (self.total - self.downloaded) / self.speed)


class RateLimiter:
    """Global token bucket shared by all downloads (KiB/s; 0 = unlimited)."""

    def __init__(self, kbps: int = 0):
        self._lock = threading.Lock()
        self.set_limit(kbps)

    def set_limit(self, kbps: int) -> None:
        with self._lock:
            self.rate = max(0, int(kbps)) * 1024
            self._allowance = float(self.rate)
            self._last = time.monotonic()

    def consume(self, n: int) -> None:
        if not self.rate:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._allowance = min(self.rate, self._allowance + (now - self._last) * self.rate)
                self._last = now
                if self._allowance >= n or self._allowance >= self.rate:
                    self._allowance -= n
                    return
                wait = (n - self._allowance) / self.rate
            time.sleep(min(wait, 0.25))


def safe_folder_name(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip(" .")
    return name[:120] or "Game"


class DownloadManager(QObject):
    task_added = Signal(int)
    task_updated = Signal(int)
    task_removed = Signal(int)
    task_finished = Signal(int, bool)      # id, success

    def __init__(self, config, sources, library):
        super().__init__()
        self.config = config
        self.sources = sources
        self.library = library
        self.limiter = RateLimiter(config.get("bandwidth_limit_kbps", 0))
        self._tasks: dict[int, DownloadTask] = {}
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ public
    def tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def task(self, task_id: int) -> DownloadTask | None:
        return self._tasks.get(task_id)

    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status in ACTIVE)

    def find_active(self, source_id: str, item_id: str) -> DownloadTask | None:
        for t in self._tasks.values():
            if t.source_id == source_id and t.item.id == item_id and t.status not in FINISHED:
                return t
        return None

    def enqueue(self, source_id: str, item: CatalogItem, install_dir: str | Path | None = None) -> int:
        existing = self.find_active(source_id, item.id)
        if existing:
            return existing.id
        custom_dir = str(install_dir) if install_dir else ""
        task = DownloadTask(id=next(self._ids), source_id=source_id, item=item, total=item.size_bytes, target_install_dir=custom_dir)
        with self._lock:
            self._tasks[task.id] = task
        log.info("Queued download %s from %s (install_dir=%s)", item.title, source_id, custom_dir or "default")
        self.task_added.emit(task.id)
        self._schedule()
        return task.id

    def pause(self, task_id: int) -> None:
        t = self._tasks.get(task_id)
        if not t:
            return
        if t.status == Status.QUEUED:
            t.status = Status.PAUSED
            self.task_updated.emit(t.id)
        elif t.status in (Status.DOWNLOADING, Status.RESOLVING):
            t._pause.set()

    def resume(self, task_id: int) -> None:
        t = self._tasks.get(task_id)
        if t and t.status in (Status.PAUSED, Status.FAILED):
            t.status = Status.QUEUED
            t.error = ""
            t._pause.clear()
            t._cancel.clear()
            self.task_updated.emit(t.id)
            self._schedule()

    def cancel(self, task_id: int) -> None:
        t = self._tasks.get(task_id)
        if not t or t.status in FINISHED:
            return
        if t._thread and t._thread.is_alive():
            t._cancel.set()
        else:
            self._cleanup_partial(t)
            t.status = Status.CANCELLED
            self.task_updated.emit(t.id)
            self.task_finished.emit(t.id, False)
            self._schedule()

    def remove(self, task_id: int) -> None:
        t = self._tasks.get(task_id)
        if t and t.status in FINISHED:
            with self._lock:
                self._tasks.pop(task_id, None)
            self.task_removed.emit(task_id)

    def clear_finished(self) -> None:
        for t in list(self._tasks.values()):
            if t.status in FINISHED:
                self.remove(t.id)

    def set_bandwidth_limit(self, kbps: int) -> None:
        self.limiter.set_limit(kbps)

    def shutdown(self) -> None:
        for t in self._tasks.values():
            if t.status in ACTIVE:
                t._pause.set()

    # ---------------------------------------------------------------- scheduler
    def _schedule(self) -> None:
        with self._lock:
            limit = max(1, int(self.config.get("max_concurrent_downloads", 2)))
            active = self.active_count()
            for t in sorted(self._tasks.values(), key=lambda x: x.id):
                if active >= limit:
                    break
                if t.status == Status.QUEUED:
                    t.status = Status.RESOLVING
                    t._thread = threading.Thread(target=self._run, args=(t,), name=f"download-{t.id}", daemon=True)
                    t._thread.start()
                    active += 1

    # ------------------------------------------------------------------ worker
    def _set(self, t: DownloadTask, status: Status) -> None:
        t.status = status
        self.task_updated.emit(t.id)

    def _check_stop(self, t: DownloadTask) -> None:
        if t._cancel.is_set() or t._pause.is_set():
            raise _Stop()

    def _run(self, t: DownloadTask) -> None:
        success = False
        try:
            source = self.sources.get(t.source_id)
            if source is None:
                raise SourceError(f"Source '{t.source_id}' is not available")
            temp_dir = Path(self.config.get("temp_dir"))
            games_dir = Path(t.target_install_dir) if t.target_install_dir else Path(self.config.get("games_dir"))
            temp_dir.mkdir(parents=True, exist_ok=True)
            games_dir.mkdir(parents=True, exist_ok=True)

            self._set(t, Status.RESOLVING)
            spec = source.resolve_download(t.item, temp_dir)
            self._check_stop(t)
            archive = temp_dir / safe_folder_name(spec.filename or f"{t.item.id}.zip")
            t.archive_path = str(archive)
            if spec.size_bytes:
                t.total = spec.size_bytes

            if not archive.exists():
                self._download(t, spec, archive)
            else:
                log.info("Archive already present, skipping download: %s", archive)
                t.downloaded = t.total = archive.stat().st_size

            self._set(t, Status.VERIFYING)
            if spec.sha256:
                digest = hashlib.sha256()
                with open(archive, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest().lower() != spec.sha256.lower():
                    archive.unlink(missing_ok=True)
                    raise RuntimeError("Checksum mismatch — the download is corrupted. Please retry.")

            need = extractor.uncompressed_size(archive)
            free = shutil.disk_usage(games_dir).free
            if need and free < need:
                raise RuntimeError(
                    f"Insufficient disk space in games folder: need {need / 2**30:.2f} GB, "
                    f"have {free / 2**30:.2f} GB")

            # Extract into a staging folder so a failed extraction never leaves a half-installed game.
            self._set(t, Status.EXTRACTING)
            final_dir = games_dir / safe_folder_name(t.item.title)
            staging = games_dir / f".staging_{t.id}_{int(time.time())}"
            last_emit = [0.0]

            def on_progress(done: int, total: int) -> None:
                t.extract_progress = done / total if total else 0
                now = time.monotonic()
                if now - last_emit[0] > 0.25:
                    last_emit[0] = now
                    self.task_updated.emit(t.id)

            try:
                extractor.extract(archive, staging, spec.archive_password, on_progress, t._cancel.is_set)
                content = extractor.flatten_single_folder(staging)
                old = None
                if final_dir.exists():
                    old = final_dir.with_name(final_dir.name + f".old_{int(time.time())}")
                    final_dir.rename(old)
                content.rename(final_dir)
                if old:
                    shutil.rmtree(old, ignore_errors=True)
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
            t.install_dir = str(final_dir)

            if self.config.get("delete_archive_after_install", True):
                try:
                    archive.unlink()
                except OSError as exc:
                    log.warning("Could not delete archive %s: %s", archive, exc)

            exe = source.find_executable(t.item, final_dir) or launcher.guess_executable(final_dir, t.item.title)
            record = t.item.to_library_record()
            record.update({
                "installed": 1, "install_dir": str(final_dir), "executable": exe or "",
                "size_bytes": _dir_size(final_dir),
            })
            existing = self.library.find(t.source_id, t.item.id)
            if existing and exe:
                self.library.db.update_game(existing["id"], executable=exe)
            t.game_id = self.library.add_or_update(record)
            self._set(t, Status.COMPLETED)
            success = True
            log.info("Installed %s into %s", t.item.title, final_dir)
        except _Stop:
            if t._cancel.is_set():
                self._cleanup_partial(t)
                self._set(t, Status.CANCELLED)
            else:
                t.speed = 0
                self._set(t, Status.PAUSED)
        except extractor.ExtractionCancelled:
            self._set(t, Status.CANCELLED)
        except Exception as exc:  # noqa: BLE001 - every failure should land in the UI
            log.exception("Download %s failed", t.item.title)
            t.error = _friendly_error(exc)
            t.speed = 0
            if isinstance(exc, extractor.ExtractionError) and t.archive_path and "Corrupted" in str(exc):
                Path(t.archive_path).unlink(missing_ok=True)  # force fresh download on retry
                t.downloaded = 0
            self._set(t, Status.FAILED)
        finally:
            t._pause.clear()
            if t.status in FINISHED:
                self.task_finished.emit(t.id, success)
            self._schedule()

    def _download(self, t: DownloadTask, spec, archive: Path) -> None:
        part = archive.with_name(archive.name + ".part")
        temp_dir = archive.parent
        offset = part.stat().st_size if part.exists() else 0

        if spec.size_bytes:
            free = shutil.disk_usage(temp_dir).free
            if free < spec.size_bytes - offset:
                raise RuntimeError(
                    f"Insufficient disk space in temp folder: need {(spec.size_bytes - offset) / 2**30:.2f} GB, "
                    f"have {free / 2**30:.2f} GB")

        self._set(t, Status.DOWNLOADING)
        parsed = urllib.parse.urlparse(spec.url)
        if parsed.scheme == "file":
            src_path = Path(urllib.request.url2pathname(parsed.path))
            if parsed.netloc and os.name == "nt":
                src_path = Path(f"//{parsed.netloc}{urllib.request.url2pathname(parsed.path)}")
            t.total = src_path.stat().st_size
            fh_in = open(src_path, "rb")
            fh_in.seek(offset)
            resp_close = fh_in.close
            reader = fh_in.read
        else:
            headers = {"User-Agent": USER_AGENT, **spec.headers}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            req = urllib.request.Request(spec.url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            if offset and resp.status != 206:
                offset = 0  # server ignored Range: start over
            length = int(resp.headers.get("Content-Length") or 0)
            if length:
                t.total = offset + length
            resp_close = resp.close
            reader = resp.read

        t.downloaded = offset
        mode = "ab" if offset else "wb"
        window_start, window_bytes, last_emit = time.monotonic(), 0, 0.0
        try:
            with open(part, mode) as out:
                while True:
                    self._check_stop(t)
                    chunk = reader(CHUNK)
                    if not chunk:
                        break
                    self.limiter.consume(len(chunk))
                    out.write(chunk)
                    t.downloaded += len(chunk)
                    window_bytes += len(chunk)
                    now = time.monotonic()
                    dt = now - window_start
                    if dt >= 0.5:
                        inst = window_bytes / dt
                        t.speed = inst if t.speed == 0 else t.speed * 0.6 + inst * 0.4
                        window_start, window_bytes = now, 0
                    if now - last_emit >= 0.25:
                        last_emit = now
                        self.task_updated.emit(t.id)
        finally:
            resp_close()

        if t.total and t.downloaded < t.total:
            raise RuntimeError("Download incomplete (connection closed early). Retry to resume.")
        t.total = t.total or t.downloaded
        t.speed = 0
        part.replace(archive)

    def _cleanup_partial(self, t: DownloadTask) -> None:
        if t.archive_path:
            for p in (Path(t.archive_path + ".part"), Path(t.archive_path)):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        t.downloaded = 0
        t.speed = 0


def _dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"Server returned HTTP {exc.code} ({exc.reason})"
    if isinstance(exc, urllib.error.URLError):
        return f"Network error: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "Connection timed out"
    if isinstance(exc, PermissionError):
        return f"Permission denied: {exc.filename or exc}"
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "Disk full"
    return str(exc) or exc.__class__.__name__
