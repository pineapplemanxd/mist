"""Library manager: the single entry point the UI uses for game records."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from . import launcher, steam_scanner
from .database import Database
from .logger import get_logger

log = get_logger(__name__)


class LibraryManager(QObject):
    changed = Signal()                    # library content changed (add/remove/bulk)
    game_updated = Signal(int)            # a single game row changed
    running_changed = Signal(int, bool)   # game_id, running

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.tracker = launcher.PlaytimeTracker()
        self.tracker.game_started.connect(lambda gid: self.running_changed.emit(gid, True))
        self.tracker.game_stopped.connect(self._on_game_stopped)

    # ----------------------------------------------------------------- queries
    def games(self) -> list[dict[str, Any]]:
        return self.db.all_games()

    def game(self, game_id: int) -> dict[str, Any] | None:
        return self.db.get_game(game_id)

    def find(self, source: str, source_id: str) -> dict[str, Any] | None:
        return self.db.find_game(source, source_id)

    # ------------------------------------------------------------------ edits
    def add_or_update(self, record: dict[str, Any]) -> int:
        gid = self.db.upsert_game(record)
        self.changed.emit()
        return gid

    def add_manual(self, exe_path: str, title: str = "") -> int:
        p = Path(exe_path)
        title = title or p.parent.name or p.stem
        gid = self.db.upsert_game({
            "title": title, "source": "manual", "source_id": os.path.normcase(str(p)),
            "install_dir": str(p.parent), "executable": str(p), "installed": 1,
        })
        self.changed.emit()
        return gid

    def set_favorite(self, game_id: int, fav: bool) -> None:
        self.db.update_game(game_id, favorite=int(fav))
        self.game_updated.emit(game_id)

    def set_executable(self, game_id: int, exe: str) -> None:
        self.db.update_game(game_id, executable=exe)
        self.game_updated.emit(game_id)

    def remove(self, game_id: int) -> None:
        """Remove from library only (files untouched)."""
        self.db.delete_game(game_id)
        self.changed.emit()

    def uninstall(self, game_id: int, games_root: Path) -> None:
        """Delete game files — only for games installed by this app inside the games folder."""
        g = self.db.get_game(game_id)
        if not g:
            return
        if g["source"] in ("steam", "manual"):
            raise PermissionError("This game is managed externally. Use its own launcher to uninstall.")
        install_dir = Path(g["install_dir"] or "")
        if install_dir and install_dir.exists():
            root = games_root.resolve()
            target = install_dir.resolve()
            if target == root or os.path.commonpath([str(root), str(target)]) != str(root):
                raise PermissionError(f"Refusing to delete a folder outside the games directory:\n{target}")
            shutil.rmtree(target, ignore_errors=False)
        self.db.update_game(game_id, installed=0, executable="", install_dir="")
        self.changed.emit()

    # ------------------------------------------------------------------ launch
    def launch(self, game_id: int) -> None:
        g = self.db.get_game(game_id)
        if not g:
            raise launcher.LaunchError("Game not found")
        if self.tracker.is_running(game_id):
            raise launcher.LaunchError(f"{g['title']} is already running")
        if not g.get("executable") and not g.get("launch_uri") and g.get("install_dir"):
            exe = launcher.guess_executable(Path(g["install_dir"]), g["title"])
            if exe:
                self.db.update_game(game_id, executable=exe)
                g["executable"] = exe
        popen = launcher.launch(g)
        self.db.update_game(game_id, last_played=int(time.time()))
        self.game_updated.emit(game_id)
        self.tracker.track(game_id, g.get("install_dir") or "", popen)
        log.info("Launched %s", g["title"])

    def is_running(self, game_id: int) -> bool:
        return self.tracker.is_running(game_id)

    def _on_game_stopped(self, game_id: int, seconds: int) -> None:
        if seconds > 0:
            self.db.add_playtime(game_id, seconds)
        self.game_updated.emit(game_id)
        self.running_changed.emit(game_id, False)

    # ------------------------------------------------------------------- steam
    def import_steam(self, games: list[steam_scanner.SteamGame]) -> tuple[int, int]:
        """Sync Steam games into the library. Returns (added_or_updated, removed)."""
        seen = set()
        for sg in games:
            seen.add(sg.appid)
            existing = self.db.find_game("steam", sg.appid)
            record = {
                "title": sg.name, "source": "steam", "source_id": sg.appid, "installed": 1,
                "install_dir": str(sg.install_dir), "launch_uri": f"steam://rungameid/{sg.appid}",
                "size_bytes": sg.size_bytes, "cover_url": sg.cover_path, "hero_url": sg.hero_path,
            }
            gid = self.db.upsert_game(record)
            # Seed last_played from Steam the first time only.
            if not existing and sg.last_played:
                self.db.update_game(gid, last_played=sg.last_played)
        stale = [g["id"] for g in self.db.all_games()
                 if g["source"] == "steam" and g["source_id"] not in seen and g["installed"]]
        for gid in stale:  # keep history (playtime/favorite), just flag as not installed
            self.db.update_game(gid, installed=0)
        self.changed.emit()
        return len(games), len(stale)
